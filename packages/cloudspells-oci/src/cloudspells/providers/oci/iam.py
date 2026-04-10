"""IAM spells for CloudSpells.

Provides purpose-built OCI IAM spells for common workload principal patterns.
Each spell creates either a dynamic group or an IAM group, plus the associated
IAM policy.

`ComputeInstancePrincipal` accepts a `grants` list — each entry is a
`"<verb> <resource-type>"` fragment in OCI's own policy language (e.g.
`"read object-family"`). The spell assembles the full policy statement
structure internally:

```
Allow dynamic-group <dg> to <grant> in compartment id <cid>
```

This is a deliberate CS-001 exception: the OCI IAM policy DSL cannot be
fully enumerated into typed constants without replicating Oracle's entire
resource catalogue. Accepting the verb+resource fragment keeps the interface
thin while the spell still owns the structural boilerplate (dynamic group
name, compartment scoping, resource naming, tagging).

`OkeNodePrincipal` and `CompartmentAdminGroup` have fixed grants because
their permission sets are well-defined by OCI.

All three spells require `tenancy_id` in addition to `compartment_id` because
OCI creates dynamic groups and IAM groups at the tenancy root compartment level,
while matching rules and policies are scoped to the specific workload compartment.

Exports:
    CompartmentAdminGroup: IAM group and compartment-admin policy for human operators.
    ComputeInstancePrincipal: Instance principal with caller-specified grants.
    OkeNodePrincipal: Instance principal for OKE node pool cluster operations.
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from cloudspells.core.base import BaseResource

# ── Private mixin ─────────────────────────────────────────────────────────────


class _PrincipalMixin:
    """Shared accessors for dynamic-group-based principal spells.

    Extracted to satisfy CS-011 (DRY via private mixin): `get_dynamic_group_id`,
    `get_policy_id`, and `export` are identical across `ComputeInstancePrincipal`
    and `OkeNodePrincipal`. Not exported; not part of the public API.

    Attributes:
        name: Logical resource name; provided by `BaseResource`.
        dynamic_group: The underlying `oci.identity.DynamicGroup`; set by each
            spell's `__init__`.
        policy: The underlying `oci.identity.Policy`; set by each spell's
            `__init__`.
    """

    name: str
    dynamic_group: oci.identity.DynamicGroup
    policy: oci.identity.Policy

    def get_dynamic_group_id(self) -> pulumi.Output[str]:
        """Return the OCID of the dynamic group.

        Returns:
            `pulumi.Output[str]` resolving to the dynamic group OCID.
        """
        return self.dynamic_group.id

    def get_policy_id(self) -> pulumi.Output[str]:
        """Return the OCID of the IAM policy.

        Returns:
            `pulumi.Output[str]` resolving to the policy OCID.
        """
        return self.policy.id

    def export(self) -> None:
        """Export the dynamic group and policy OCIDs as Pulumi stack outputs.

        Publishes `"{name}_dynamic_group_id"` and `"{name}_policy_id"` where
        `name` is the spell's logical name with hyphens replaced by underscores.

        Example:
            ```python
            principal = ComputeInstancePrincipal(name="app-server", ...)
            principal.export()
            # Exports: app_server_dynamic_group_id, app_server_policy_id
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_dynamic_group_id", self.get_dynamic_group_id())
        pulumi.export(f"{prefix}_policy_id", self.get_policy_id())


# ── Spell classes ─────────────────────────────────────────────────────────────


class ComputeInstancePrincipal(_PrincipalMixin, BaseResource):
    """Instance principal granting compute instances access to caller-specified OCI services.

    Creates an OCI Dynamic Group that matches all compute instances in the
    supplied compartment, plus an IAM Policy whose statements are assembled from
    the `grants` list. Each entry is a `"<verb> <resource-type>"` fragment in
    OCI's policy language; the spell wraps it into a full statement:

    ```
    Allow dynamic-group <dg> to <grant> in compartment id <cid>
    ```

    **CS-001 exception:** `grants` accepts raw OCI policy verb+resource
    fragments rather than typed constants because the OCI IAM resource
    catalogue is too large to enumerate. The spell still owns all structural
    boilerplate — naming, tagging, compartment scoping — so callers only
    supply the access intent, not provider-level resource options.

    The dynamic group is created in the tenancy root compartment (as required
    by OCI) while the policy is scoped to the workload compartment.

    Resources created:

    - One `oci.identity.DynamicGroup` in the tenancy root compartment, matching
      all instances in `compartment_id`.
    - One `oci.identity.Policy` in `compartment_id` with one statement per
      entry in `grants`.

    Attributes:
        dynamic_group: The underlying `oci.identity.DynamicGroup` resource.
        policy: The underlying `oci.identity.Policy` resource.
        dynamic_group_id: `pulumi.Output[str]` resolving to the dynamic group OCID.
        policy_id: `pulumi.Output[str]` resolving to the policy OCID.

    Example:
        ```python
        principal = ComputeInstancePrincipal(
            name="app",
            compartment_id=comp_id,
            tenancy_id=tenancy_id,
            grants=[
                "read secret-family",    # fetch DB password from Vault
                "read object-family",    # read app config from Object Storage
            ],
        )
        principal.export()
        ```
    """

    dynamic_group: oci.identity.DynamicGroup
    policy: oci.identity.Policy
    dynamic_group_id: pulumi.Output[str]
    policy_id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        tenancy_id: pulumi.Input[str],
        grants: list[str] = ["read object-family", "read secret-family"],  # noqa: B006
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a compute instance principal with caller-specified service access.

        Args:
            name: Logical name for the principal (e.g. `"app"`). Combined with
                the stack name to form `"{stack}-{name}-dg"` and
                `"{stack}-{name}-policy"`.
            compartment_id: OCID of the OCI compartment whose instances will be
                members of the dynamic group. Also used to scope the policy.
            tenancy_id: OCID of the OCI tenancy root compartment. Required
                because OCI creates dynamic groups at the tenancy level, not
                within child compartments.
            grants: OCI policy verb+resource fragments, one per desired
                permission. Each entry must follow OCI policy syntax:
                `"<verb> <resource-type>"` (e.g. `"read object-family"`,
                `"manage volume-family"`). The spell assembles the full
                statement around each entry. Must contain at least one entry.
                Defaults to `["read object-family", "read secret-family"]`.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `grants` is empty.
        """
        if not grants:
            raise ValueError("grants must contain at least one policy fragment")

        super().__init__("custom:iam:ComputeInstancePrincipal", name, compartment_id, stack_name, opts)

        dg_name = self.create_resource_name("dg")
        policy_name = self.create_resource_name("policy")
        # Copy grants into a local list so the apply() closure captures a
        # stable value rather than the caller's mutable list reference.
        grants_copy = list(grants)

        self.dynamic_group = oci.identity.DynamicGroup(
            dg_name,
            compartment_id=tenancy_id,
            description=f"Instance principal for {self.display_name}",
            matching_rule=pulumi.Output.format("instance.compartment.id = '{0}'", compartment_id),
            name=dg_name,
            freeform_tags=self.create_freeform_tags(dg_name, "dynamic-group"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.policy = oci.identity.Policy(
            policy_name,
            compartment_id=compartment_id,
            description=f"Instance principal policy for {dg_name}",
            statements=pulumi.Output.from_input(compartment_id).apply(
                lambda cid: [
                    f"Allow dynamic-group {dg_name} to {grant} in compartment id {cid}" for grant in grants_copy
                ]
            ),
            name=policy_name,
            freeform_tags=self.create_freeform_tags(policy_name, "policy"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.dynamic_group_id = self.dynamic_group.id
        self.policy_id = self.policy.id
        self.register_outputs({
            "dynamic_group_id": self.dynamic_group_id,
            "policy_id": self.policy_id,
        })


class OkeNodePrincipal(_PrincipalMixin, BaseResource):
    """Instance principal granting OKE node pool instances the full OKE permission set.

    Creates an OCI Dynamic Group matching all compute instances in the supplied
    compartment, plus an IAM Policy that grants the group the permissions required
    for OKE cluster operation: instance management, virtual networking, load
    balancers, block volumes, and container registry reads.

    The dynamic group is created in the tenancy root compartment (as required by
    OCI) while the policy is scoped to the workload compartment. The matching
    rule covers all instances in the compartment, which is the standard OKE node
    principal pattern — no per-node-pool configuration is required.

    Resources created:

    - One `oci.identity.DynamicGroup` in the tenancy root compartment, matching
      all instances in `compartment_id`.
    - One `oci.identity.Policy` in `compartment_id` with five statements covering
      the full OKE node permission set: manage `instance-family`, use
      `virtual-network-family`, manage `load-balancers`, use `volume-family`,
      and read `repos`.

    Attributes:
        dynamic_group: The underlying `oci.identity.DynamicGroup` resource.
        policy: The underlying `oci.identity.Policy` resource.
        dynamic_group_id: `pulumi.Output[str]` resolving to the dynamic group OCID.
        policy_id: `pulumi.Output[str]` resolving to the policy OCID.

    Example:
        ```python
        principal = OkeNodePrincipal(
            name="k8s",
            compartment_id=comp_id,
            tenancy_id=tenancy_id,
        )
        principal.export()
        ```
    """

    dynamic_group: oci.identity.DynamicGroup
    policy: oci.identity.Policy
    dynamic_group_id: pulumi.Output[str]
    policy_id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        tenancy_id: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create an OKE node principal with the full cluster operational permission set.

        Args:
            name: Logical name for the principal (e.g. `"k8s"`). Combined with
                the stack name to form `"{stack}-{name}-dg"` and
                `"{stack}-{name}-policy"`.
            compartment_id: OCID of the OCI compartment whose instances will be
                members of the dynamic group. Also used to scope the policy.
            tenancy_id: OCID of the OCI tenancy root compartment. Required
                because OCI creates dynamic groups at the tenancy level, not
                within child compartments.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:iam:OkeNodePrincipal", name, compartment_id, stack_name, opts)

        dg_name = self.create_resource_name("dg")
        policy_name = self.create_resource_name("policy")

        self.dynamic_group = oci.identity.DynamicGroup(
            dg_name,
            compartment_id=tenancy_id,
            description=f"OKE node principal for {self.display_name} — cluster operational permissions",
            matching_rule=pulumi.Output.format("instance.compartment.id = '{0}'", compartment_id),
            name=dg_name,
            freeform_tags=self.create_freeform_tags(dg_name, "dynamic-group"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.policy = oci.identity.Policy(
            policy_name,
            compartment_id=compartment_id,
            description=f"OKE node operational permissions for {dg_name}",
            statements=pulumi.Output.from_input(compartment_id).apply(
                lambda cid: [
                    f"Allow dynamic-group {dg_name} to manage instance-family in compartment id {cid}",
                    f"Allow dynamic-group {dg_name} to use virtual-network-family in compartment id {cid}",
                    f"Allow dynamic-group {dg_name} to manage load-balancers in compartment id {cid}",
                    f"Allow dynamic-group {dg_name} to use volume-family in compartment id {cid}",
                    f"Allow dynamic-group {dg_name} to read repos in compartment id {cid}",
                ]
            ),
            name=policy_name,
            freeform_tags=self.create_freeform_tags(policy_name, "policy"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.dynamic_group_id = self.dynamic_group.id
        self.policy_id = self.policy.id
        self.register_outputs({
            "dynamic_group_id": self.dynamic_group_id,
            "policy_id": self.policy_id,
        })


class CompartmentAdminGroup(BaseResource):
    """IAM group and policy granting human operators full management of a compartment.

    Creates an OCI IAM Group in the tenancy root compartment and an IAM Policy
    that grants all group members `manage all-resources` within the supplied
    compartment. This is the standard pattern for delegating a team's
    administrative responsibility over a compartment without granting
    tenancy-level access.

    The group is intentionally created empty — members are added via the OCI
    Console or CLI after deployment:

    ```text
    oci iam group add-user --group-id <group_id> --user-id <user_id>
    ```

    Resources created:

    - One `oci.identity.Group` in the tenancy root compartment.
    - One `oci.identity.Policy` in `compartment_id` with one statement:
      `manage all-resources` scoped to `compartment_id`.

    Attributes:
        group: The underlying `oci.identity.Group` resource.
        policy: The underlying `oci.identity.Policy` resource.
        group_id: `pulumi.Output[str]` resolving to the IAM group OCID.
        policy_id: `pulumi.Output[str]` resolving to the policy OCID.

    Example:
        ```python
        admin = CompartmentAdminGroup(
            name="ops-team",
            compartment_id=comp_id,
            tenancy_id=tenancy_id,
        )
        admin.export()
        ```
    """

    group: oci.identity.Group
    policy: oci.identity.Policy
    group_id: pulumi.Output[str]
    policy_id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        tenancy_id: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create an IAM group with full compartment admin access.

        Args:
            name: Logical name for the group (e.g. `"ops-team"`). Combined with
                the stack name to form `"{stack}-{name}-group"` and
                `"{stack}-{name}-policy"`.
            compartment_id: OCID of the OCI compartment the group will
                administrate. The policy is scoped to this compartment.
            tenancy_id: OCID of the OCI tenancy root compartment. Required
                because OCI creates IAM groups at the tenancy level, not within
                child compartments.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:iam:CompartmentAdminGroup", name, compartment_id, stack_name, opts)

        group_name = self.create_resource_name("group")
        policy_name = self.create_resource_name("policy")

        self.group = oci.identity.Group(
            group_name,
            compartment_id=tenancy_id,
            description=f"Compartment administrators for {self.display_name}",
            name=group_name,
            freeform_tags=self.create_freeform_tags(group_name, "group"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.policy = oci.identity.Policy(
            policy_name,
            compartment_id=compartment_id,
            description=f"Compartment admin policy for {group_name}",
            statements=pulumi.Output.from_input(compartment_id).apply(
                lambda cid: [
                    f"Allow group {group_name} to manage all-resources in compartment id {cid}",
                ]
            ),
            name=policy_name,
            freeform_tags=self.create_freeform_tags(policy_name, "policy"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.group_id = self.group.id
        self.policy_id = self.policy.id
        self.register_outputs({
            "group_id": self.group_id,
            "policy_id": self.policy_id,
        })

    def get_group_id(self) -> pulumi.Output[str]:
        """Return the OCID of the IAM group.

        Returns:
            `pulumi.Output[str]` resolving to the IAM group OCID.
        """
        return self.group.id

    def get_policy_id(self) -> pulumi.Output[str]:
        """Return the OCID of the IAM policy.

        Returns:
            `pulumi.Output[str]` resolving to the policy OCID.
        """
        return self.policy.id

    def export(self) -> None:
        """Export the group and policy OCIDs as Pulumi stack outputs.

        Publishes `"{name}_group_id"` and `"{name}_policy_id"` where `name`
        is the spell's logical name with hyphens replaced by underscores.

        Example:
            ```python
            admin = CompartmentAdminGroup(name="ops-team", ...)
            admin.export()
            # Exports: ops_team_group_id, ops_team_policy_id
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_group_id", self.get_group_id())
        pulumi.export(f"{prefix}_policy_id", self.get_policy_id())


__all__ = [
    "CompartmentAdminGroup",
    "ComputeInstancePrincipal",
    "OkeNodePrincipal",
]
