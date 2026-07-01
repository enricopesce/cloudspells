"""IAM spells for CloudSpells.

Provides purpose-built OCI IAM spells for common workload principal patterns.
Each spell creates either a dynamic group or an IAM group, plus the associated
IAM policy.

`ComputeInstancePrincipal` accepts explicit compute instance members, plus a
list of `IamGrant` objects. `IamGrant` provides named helpers for the common
CloudSpells access patterns while keeping arbitrary OCI IAM fragments behind
the explicit `IamGrant.raw(...)` escape hatch. The spell assembles the full
policy statement structure internally:

```
Allow dynamic-group id <dg_ocid> to <grant> in compartment id <cid>
```

The OCI IAM policy DSL cannot be fully enumerated into typed constants without
replicating Oracle's entire resource catalogue. `IamGrant.raw(...)` keeps that
provider-specific surface explicit, while the spell still owns the dynamic
group membership, compartment scoping, resource naming, and tagging.

`OkeNodePrincipal` and `CompartmentAdminGroup` have fixed grants because
their permission sets are well-defined by OCI. `OkeNodePrincipal` remains
compartment-scoped for membership; deploy OKE nodes in a dedicated compartment
until CloudSpells adds an internal worker-node tag boundary.

All IAM spells require `tenancy_id` because OCI creates dynamic groups and IAM
groups at the tenancy root compartment level. Workload policies remain scoped to
the specific workload compartment, either derived from the supplied compute
instances or passed directly for existing instance OCIDs.

Exports:
    CompartmentAdminGroup: IAM group and compartment-admin policy for human operators.
    ComputeInstancePrincipal: Instance principal for selected compute instances.
    OkeNodePrincipal: Instance principal for OKE node pool cluster operations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import pulumi
import pulumi_oci as oci
from cloudspells.core.base import BaseResource

# ── IAM grant helpers ─────────────────────────────────────────────────────────

_ALLOWED_GRANT_VERBS = frozenset({"inspect", "read", "use", "manage"})


def _validate_grant_fragment(fragment: str) -> str:
    """Validate and normalize an OCI IAM grant fragment.

    Args:
        fragment: OCI IAM policy grant fragment in the shape
            `"<verb> <resource-type>"`, optionally followed by an OCI `where`
            clause.

    Returns:
        Trimmed grant fragment.

    Raises:
        ValueError: If the value is empty, spans multiple lines, looks like a
            full policy statement, or does not start with a supported OCI IAM
            grant verb.
    """
    cleaned = fragment.strip()
    lowered = cleaned.lower()

    if not cleaned:
        raise ValueError("IAM grant fragment must not be empty")
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError("IAM grant fragment must be a single line")
    if lowered.startswith("allow "):
        raise ValueError("IAM grant fragment must not include the full Allow statement")
    if " in compartment" in lowered or " in tenancy" in lowered:
        raise ValueError("IAM grant fragment must not include the policy scope")

    verb, separator, resource = cleaned.partition(" ")
    if separator == "" or not resource.strip() or verb.lower() not in _ALLOWED_GRANT_VERBS:
        raise ValueError(f"IAM grant fragment must start with one of: {', '.join(sorted(_ALLOWED_GRANT_VERBS))}")

    return cleaned


@dataclass(frozen=True)
class IamGrant:
    """Explicit OCI IAM grant fragment for workload principals.

    `IamGrant` does not try to enumerate the full OCI IAM policy language.
    Use named helpers for common CloudSpells access patterns, and use
    `IamGrant.raw(...)` when the workload needs an OCI permission CloudSpells
    does not model.

    Attributes:
        fragment: OCI IAM grant fragment inserted into a generated policy
            statement.
    """

    fragment: str

    @classmethod
    def read_objects(cls) -> IamGrant:
        """Return a grant for read-only Object Storage access.

        Returns:
            `IamGrant` for `read object-family`.
        """
        return cls("read object-family")

    @classmethod
    def read_secrets(cls) -> IamGrant:
        """Return a grant for read-only Vault secret access.

        Returns:
            `IamGrant` for `read secret-family`.
        """
        return cls("read secret-family")

    @classmethod
    def raw(cls, fragment: str) -> IamGrant:
        """Return an explicit raw OCI IAM grant fragment.

        Args:
            fragment: OCI IAM grant fragment in the shape
                `"<verb> <resource-type>"`, optionally followed by an OCI
                `where` clause.

        Returns:
            `IamGrant` wrapping the validated fragment.

        Raises:
            ValueError: If `fragment` is empty, spans multiple lines, includes
                the full policy statement, includes the policy scope, or does
                not start with a supported OCI IAM grant verb.
        """
        return cls(_validate_grant_fragment(fragment))


class InstancePrincipalMember(Protocol):
    """Compute-like resource that can join an instance-principal dynamic group.

    Attributes:
        id: OCID output for the backing compute instance.
        compartment_id: Workload compartment used for IAM policy scope.
    """

    @property
    def id(self) -> pulumi.Input[str]:
        """Return the compute instance OCID."""
        ...

    @property
    def compartment_id(self) -> pulumi.Input[str]:
        """Return the compute instance workload compartment OCID."""
        ...


@dataclass(frozen=True)
class _InstancePrincipalMemberRef:
    """Exact instance OCID member for cross-stack principal membership."""

    id: pulumi.Input[str]
    compartment_id: pulumi.Input[str]


def _normalize_grants(grants: Sequence[object] | None) -> list[IamGrant]:
    """Return a validated grant list.

    Args:
        grants: Optional sequence of values that must be `IamGrant` objects.

    Returns:
        Grant list supplied by the caller.

    Raises:
        TypeError: If any entry is not an `IamGrant`.
        ValueError: If `grants` is omitted or explicitly empty.
    """
    if grants is None:
        raise ValueError("grants must be provided explicitly; no IAM grants are added by default")
    if len(grants) == 0:
        raise ValueError("grants must contain at least one IamGrant")

    grant_values = list(grants)
    grant_list: list[IamGrant] = []
    for grant in grant_values:
        if not isinstance(grant, IamGrant):
            raise TypeError("grants must contain IamGrant values; use IamGrant.raw(...) for custom OCI IAM")
        grant_list.append(grant)
    return grant_list


def _normalize_principal_members(
    instances: Sequence[InstancePrincipalMember] | None,
    instance_ids: Sequence[pulumi.Input[str]] | None,
    compartment_id: pulumi.Input[str] | None,
) -> list[InstancePrincipalMember]:
    """Return exact principal members from resources or existing instance OCIDs.

    Args:
        instances: Optional compute-like resources whose instance OCIDs should
            be dynamic-group members.
        instance_ids: Optional explicit instance OCIDs for members outside the
            current stack.
        compartment_id: Workload compartment that scopes policies for explicit
            `instance_ids`.

    Returns:
        Non-empty list of principal members.

    Raises:
        ValueError: If no members are supplied, both member styles are supplied,
            `instance_ids` is empty, or `instance_ids` is used without
            `compartment_id`.
    """
    if instances is not None and instance_ids is not None:
        raise ValueError("pass either instances or instance_ids, not both")

    if instances is not None:
        members = list(instances)
        if not members:
            raise ValueError("instances must contain at least one principal member")
        return members

    if instance_ids is not None:
        ids = list(instance_ids)
        if not ids:
            raise ValueError("instance_ids must contain at least one instance OCID")
        if compartment_id is None:
            raise ValueError("compartment_id is required when using instance_ids")
        members: list[InstancePrincipalMember] = []
        for instance_id in ids:
            members.append(_InstancePrincipalMemberRef(id=instance_id, compartment_id=compartment_id))
        return members

    raise ValueError("instances or instance_ids must contain at least one principal member")


def _member_compartment_id(instances: Sequence[InstancePrincipalMember]) -> pulumi.Input[str]:
    """Return the common workload compartment for principal members.

    Args:
        instances: Non-empty sequence of principal members.

    Returns:
        Compartment input from the first member.

    Raises:
        ValueError: If multiple plain-string compartment IDs differ.
    """
    compartment_id = instances[0].compartment_id
    for member in instances[1:]:
        if (
            not isinstance(compartment_id, pulumi.Output)
            and not isinstance(member.compartment_id, pulumi.Output)
            and member.compartment_id != compartment_id
        ):
            raise ValueError("all principal instances must be in the same compartment")
    return compartment_id


def _instance_matching_rule(instances: Sequence[InstancePrincipalMember]) -> pulumi.Output[str]:
    """Build a dynamic-group matching rule for exact compute instance OCIDs.

    Args:
        instances: Non-empty sequence of principal members.

    Returns:
        Pulumi output resolving to an OCI dynamic-group matching rule.
    """
    ids = [pulumi.Output.from_input(instance.id) for instance in instances]
    if len(ids) == 1:
        return ids[0].apply(lambda instance_id: f"instance.id = '{instance_id}'")
    return pulumi.Output.all(*ids).apply(
        lambda instance_ids: "any {" + ", ".join(f"instance.id = '{instance_id}'" for instance_id in instance_ids) + "}"
    )


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
    """Instance principal granting selected compute instances OCI service access.

    Creates an OCI Dynamic Group that matches only the supplied compute
    instance OCIDs, plus an IAM Policy whose statements are assembled from the
    `IamGrant` list. Each grant is wrapped into a full statement:

    ```
    Allow dynamic-group id <dg_ocid> to <grant> in compartment id <cid>
    ```

    The OCI IAM resource catalogue is too large to model exhaustively. Use
    named `IamGrant` helpers for common CloudSpells access patterns, and use
    `IamGrant.raw(...)` when the workload needs an OCI grant fragment that
    CloudSpells does not model.

    The dynamic group is created in the tenancy root compartment (as required
    by OCI) while the policy is scoped to the workload compartment.

    Resources created:

    - One `oci.identity.DynamicGroup` in the tenancy root compartment, matching
      only the supplied instance OCIDs.
    - One `oci.identity.Policy` in `compartment_id` with one statement per
      entry in `grants`.

    Attributes:
        dynamic_group: The underlying `oci.identity.DynamicGroup` resource.
        policy: The underlying `oci.identity.Policy` resource.
        dynamic_group_id: `pulumi.Output[str]` resolving to the dynamic group OCID.
        policy_id: `pulumi.Output[str]` resolving to the policy OCID.

    Example:
        ```python
        web = ComputeInstance(name="web", compartment_id=comp_id, image_id=image_id, nsg=app_nsg)
        principal = ComputeInstancePrincipal(
            name="app",
            tenancy_id=tenancy_id,
            instances=[web],
            grants=[
                IamGrant.read_secrets(),  # fetch DB password from Vault
                IamGrant.read_objects(),  # read app config from Object Storage
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
        tenancy_id: pulumi.Input[str],
        instances: Sequence[InstancePrincipalMember] | None = None,
        grants: Sequence[IamGrant] | None = None,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
        *,
        instance_ids: Sequence[pulumi.Input[str]] | None = None,
        compartment_id: pulumi.Input[str] | None = None,
    ) -> None:
        """Create a compute instance principal with exact instance membership.

        Args:
            name: Logical name for the principal (e.g. `"app"`). Combined with
                the stack name to form `"{stack}-{name}-dg"` and
                `"{stack}-{name}-policy"`.
            tenancy_id: OCID of the OCI tenancy root compartment. Required
                because OCI creates dynamic groups at the tenancy level, not
                within child compartments.
            instances: Compute-like resources whose instance OCIDs should be
                members of the dynamic group. The first instance's compartment
                scopes the IAM policy.
            grants: `IamGrant` values, one per desired permission. Use
                `IamGrant.raw(...)` for OCI IAM grant fragments not covered by
                named helpers. Must contain at least one entry and must be
                provided explicitly; CloudSpells does not add default IAM
                permissions.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            opts: Pulumi resource options forwarded to the component.
            instance_ids: Existing compute instance OCIDs to include when the
                principal is declared outside the stack that creates the
                instances. Mutually exclusive with `instances`.
            compartment_id: Workload compartment used to scope the policy when
                `instance_ids` is supplied.

        Raises:
            TypeError: If any grant is not an `IamGrant`.
            ValueError: If no members are supplied, both member styles are
                supplied, `grants` is explicitly empty, `instance_ids` is used
                without `compartment_id`, or if multiple plain-string instance
                compartments differ.
        """
        instances_copy = _normalize_principal_members(instances, instance_ids, compartment_id)
        compartment_id = _member_compartment_id(instances_copy)
        grants_copy = _normalize_grants(grants)

        super().__init__("custom:iam:ComputeInstancePrincipal", name, compartment_id, stack_name, opts)

        dg_name = self.create_resource_name("dg")
        policy_name = self.create_resource_name("policy")

        self.dynamic_group = oci.identity.DynamicGroup(
            dg_name,
            compartment_id=tenancy_id,
            description=f"Instance principal for {self.display_name}",
            matching_rule=_instance_matching_rule(instances_copy),
            name=dg_name,
            freeform_tags=self.create_freeform_tags(dg_name, "dynamic-group"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.policy = oci.identity.Policy(
            policy_name,
            compartment_id=compartment_id,
            description=f"Instance principal policy for {dg_name}",
            statements=pulumi.Output.all(compartment_id, self.dynamic_group.id).apply(
                lambda args: [
                    f"Allow dynamic-group id {args[1]} to {grant.fragment} in compartment id {args[0]}"
                    for grant in grants_copy
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
    principal pattern. Use a compartment dedicated to the cluster's worker nodes
    until CloudSpells adds an internal worker-node tag boundary.

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
            dedicated_node_compartment=True,
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
        dedicated_node_compartment: bool = False,
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
            dedicated_node_compartment: Must be `True` to confirm that
                `compartment_id` is dedicated to OKE node instances. OCI
                dynamic groups cannot reliably match autoscaled OKE worker
                nodes by exact instance OCID before they exist, so this spell
                intentionally requires an explicit compartment boundary.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `dedicated_node_compartment` is not `True`.
        """
        if not dedicated_node_compartment:
            raise ValueError(
                "OkeNodePrincipal requires dedicated_node_compartment=True because it matches all "
                "compute instances in compartment_id. Deploy OKE worker nodes in a dedicated compartment."
            )

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
            statements=pulumi.Output.all(compartment_id, self.dynamic_group.id).apply(
                lambda args: [
                    f"Allow dynamic-group id {args[1]} to manage instance-family in compartment id {args[0]}",
                    f"Allow dynamic-group id {args[1]} to use virtual-network-family in compartment id {args[0]}",
                    f"Allow dynamic-group id {args[1]} to manage load-balancers in compartment id {args[0]}",
                    f"Allow dynamic-group id {args[1]} to use volume-family in compartment id {args[0]}",
                    f"Allow dynamic-group id {args[1]} to read repos in compartment id {args[0]}",
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
    "IamGrant",
    "InstancePrincipalMember",
    "OkeNodePrincipal",
]
