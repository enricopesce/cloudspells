r"""Landing zone spell for CloudSpells.

Provides `LandingZone`, the foundation spell of the CloudSpells layered
model: deploy the reusable foundation first, then create real services
(`ComputeInstance`, `OkeCluster`, `ScalableWorkload`, ...) inside it — in
the same stack or from separate stacks via `VcnRef`.

A landing zone is a complete, opinionated OCI foundation:

- **Network** — one `Vcn` with the fixed four-tier architecture
  (public/private/secure/management), all gateways and route tables.
- **Audit** — VCN flow logs on every subnet tier, always enabled.
- **Access** — one OCI `Bastion` in the private subnet for session-based
  SSH; no public jump hosts.
- **IAM baseline** — one `CompartmentAdminGroup` delegating compartment
  administration to a human operator group.

None of these components is optional — they are the architecture. The
caller names the landing zone, picks a compartment, and states who may
open bastion sessions. Everything else is fixed by design.

### Ordering contract

`LandingZone` extends the CloudSpells lazy-init builder pattern one level
up. Construction registers the foundation's security requirements but does
not materialise subnets; workload spells declared afterwards accumulate
their own rules; `export()` (or `finalize()`) materialises the network and
creates the Bastion:

```python
lz = LandingZone(
    name="prod",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
    allowed_client_cidrs=["203.0.113.0/24"],
)

# Services deployed INSIDE the foundation — same stack:
app_nsg = Nsg("app", role=APP_SERVER, vcn=lz.vcn, compartment_id=compartment_id)
app = ComputeInstance(name="app-1", compartment_id=compartment_id,
                      image_id=image_id, nsg=app_nsg)

lz.export()   # materialises the network, creates the Bastion,
              # publishes the full VcnRef contract
```

For the cross-stack layout, deploy the landing zone alone, register the
network profiles your workloads need, and consume it elsewhere:

```python
# foundation stack
lz = LandingZone(name="prod", ...)
lz.vcn.enable_oke_profile(kubectl_allowed_cidrs=["203.0.113.0/24"])
lz.export()

# workload stack
vcn = VcnRef.from_stack_reference("acme/foundation/prod")
cluster = OkeCluster(name="app", vcn=vcn, compartment_id=comp_id, ...)
```
"""

from __future__ import annotations

from collections.abc import Sequence

import pulumi
from cloudspells.core.base import BaseResource

from .bastion import Bastion
from .iam import CompartmentAdminGroup
from .network import Vcn


class LandingZone(BaseResource):
    """Reusable OCI foundation: network, audit logging, bastion access, and IAM baseline.

    Composes the CloudSpells foundation spells into a single deployable
    architecture. Deploy one `LandingZone` per environment, then create
    workload spells inside it — either in the same stack (pass `lz.vcn`
    wherever a spell accepts `vcn=`) or from separate stacks via
    `VcnRef.from_stack_reference()` after `export()`.

    Resources created:

    - One `Vcn` with the fixed four-tier subnet architecture and flow logs
      enabled (`VcnFlowLogs`, 90-day retention).
    - One `Bastion` of type `STANDARD` attached to the private subnet,
      created by `finalize()` / `export()`.
    - One `CompartmentAdminGroup` (IAM group + `manage all-resources`
      policy scoped to `compartment_id`).

    The Bastion is created lazily so that workload spells declared between
    construction and `finalize()` can still register security rules — the
    same accumulate-then-materialise contract as `Vcn.finalize_network()`.
    The Bastion SSH ingress rule itself is registered eagerly at
    construction time, so a workload spell that finalises the network
    early (e.g. `ComputeInstance`) can never lock the Bastion out.

    **`export()` (or `finalize()`) must be called** — until then the
    network is not materialised and the Bastion does not exist. Every
    CloudSpells stack ends with `export()` as a matter of convention.

    Attributes:
        vcn: The foundation `Vcn`. Pass it to `Nsg`, `OkeCluster`,
            `ScalableWorkload`, and every other network-anchored spell.
        admin_group: The `CompartmentAdminGroup` IAM baseline.
        bastion: The `Bastion` component, or `None` before `finalize()`.

    Example:
        ```python
        lz = LandingZone(
            name="prod",
            compartment_id=compartment_id,
            tenancy_id=tenancy_id,
            allowed_client_cidrs=["203.0.113.0/24"],
        )

        web_nsg = Nsg("web", role=INTERNET_EDGE, ports=[HTTP, HTTPS],
                      vcn=lz.vcn, compartment_id=compartment_id)
        web = ComputeInstance(name="web-1", compartment_id=compartment_id,
                              image_id=image_id, nsg=web_nsg)

        lz.export()
        ```
    """

    vcn: Vcn
    admin_group: CompartmentAdminGroup
    bastion: Bastion | None

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        tenancy_id: pulumi.Input[str],
        allowed_client_cidrs: Sequence[pulumi.Input[str]] | None = None,
        cidr_block: str | None = None,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create the landing zone foundation.

        Args:
            name: Logical name for the landing zone (e.g. `"prod"`). Also
                used as the logical name of the underlying `Vcn` and
                `Bastion` components.
            compartment_id: OCID of the OCI compartment that will contain
                every foundation resource and, by convention, the workloads
                deployed inside it.
            tenancy_id: OCID of the tenancy root compartment. Required by
                the IAM baseline — OCI creates IAM groups at tenancy level.
            allowed_client_cidrs: IPv4 CIDR blocks from which Bastion
                session creation is permitted. Must be provided explicitly —
                passing `None` raises `ValueError`. To permit all source
                IPs pass `["0.0.0.0/0"]`; in production supply a specific
                CIDR (e.g. `["203.0.113.0/24"]`).
            cidr_block: IPv4 CIDR for the VCN in canonical form. Must be a
                plain `str` (subnet splitting runs at construction time).
                Defaults to `"10.0.0.0/18"`. Choose non-overlapping CIDRs
                when deploying multiple landing zones that may be peered.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `allowed_client_cidrs` is `None`, or if
                `cidr_block` has host bits set.
        """
        super().__init__("custom:landingzone:LandingZone", name, compartment_id, stack_name, opts)

        if allowed_client_cidrs is None:
            raise ValueError(
                f"LandingZone '{name}': allowed_client_cidrs must be provided explicitly. "
                "It controls who may create Bastion sessions. To permit all source IPs "
                "(not recommended for production), pass allowed_client_cidrs=['0.0.0.0/0']."
            )
        self._allowed_client_cidrs: list[pulumi.Input[str]] = list(allowed_client_cidrs)
        # BaseResource types compartment_id as optional; keep the required
        # value under its own name for child spells that demand Input[str].
        self._compartment_id: pulumi.Input[str] = compartment_id

        child_opts = pulumi.ResourceOptions(parent=self)

        # Foundation network with audit logging always on — flow logs are
        # part of the landing zone architecture, not an option.
        self.vcn = Vcn(
            name=name,
            compartment_id=compartment_id,
            stack_name=self.stack_name,
            opts=child_opts,
            cidr_block=cidr_block,
            flow_logs=True,
        )

        # Register the Bastion SSH ingress rule now, before any workload
        # spell can finalise the network. Bastion resource creation itself
        # is deferred to finalize() so workloads keep accumulating rules.
        self.vcn.enable_bastion_profile()

        self.admin_group = CompartmentAdminGroup(
            name=f"{name}-admins",
            compartment_id=compartment_id,
            tenancy_id=tenancy_id,
            stack_name=self.stack_name,
            opts=child_opts,
        )

        self.bastion = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def finalize(self) -> None:
        """Materialise the network and create the Bastion.

        Idempotent — only the first call has effect. Calls
        `Vcn.finalize_network()` (itself idempotent), so every security
        rule registered by workload spells declared before this call is
        included in the generated security lists.

        Called automatically by `export()`; call it directly only when a
        stack needs the Bastion without publishing stack outputs.
        """
        if self.bastion is not None:
            return

        self.bastion = Bastion(
            name=self.name,
            compartment_id=self._compartment_id,
            vcn=self.vcn,
            allowed_client_cidrs=self._allowed_client_cidrs,
            stack_name=self.stack_name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        outputs: dict[str, pulumi.Output[str]] = {
            "vcn_id": self.vcn.id,
            "bastion_id": self.bastion.bastion_id,
            "bastion_endpoint": self.bastion.bastion_endpoint,
            "admin_group_id": self.admin_group.group_id,
            "admin_policy_id": self.admin_group.policy_id,
        }
        if self.vcn.flow_logs is not None:
            outputs["network_audit_log_group_id"] = self.vcn.flow_logs.log_group_id
        self.register_outputs(outputs)

    def export(self) -> None:
        """Publish the landing zone contract as Pulumi stack outputs.

        Calls `finalize()` first, then exports the canonical `Vcn`
        contract (everything `VcnRef.from_stack_reference()` expects,
        including `cloudspells_network_schema` and
        `cloudspells_network_profiles`) plus the landing-zone keys:

        - `compartment_id` — compartment the foundation lives in.
        - `bastion_id` / `bastion_endpoint` — session-based SSH access.
        - `admin_group_id` / `admin_policy_id` — IAM baseline.

        The flow-log group OCID is published by the `Vcn` contract as
        `network_audit_log_group_id`.

        Example:
            ```python
            lz = LandingZone(name="prod", ...)
            lz.export()
            # Another stack: VcnRef.from_stack_reference("org/foundation/prod")
            ```
        """
        self.finalize()
        self.vcn.export()
        pulumi.export("compartment_id", self.compartment_id)
        pulumi.export("bastion_id", self.get_bastion_id())
        pulumi.export("bastion_endpoint", self.get_bastion_endpoint())
        pulumi.export("admin_group_id", self.admin_group.group_id)
        pulumi.export("admin_policy_id", self.admin_group.policy_id)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_bastion_id(self) -> pulumi.Output[str]:
        """Return the OCID of the Bastion resource.

        Returns:
            `pulumi.Output[str]` resolving to the Bastion OCID.

        Raises:
            RuntimeError: If called before `finalize()` / `export()`.
        """
        if self.bastion is None:
            raise RuntimeError(
                f"LandingZone '{self.name}': the Bastion does not exist yet. Call finalize() or export() first."
            )
        return self.bastion.get_bastion_id()

    def get_bastion_endpoint(self) -> pulumi.Output[str]:
        """Return the private endpoint IP of the Bastion.

        Use this address as a `ProxyJump` target in SSH client
        configuration to reach private-subnet instances.

        Returns:
            `pulumi.Output[str]` resolving to the Bastion endpoint IP.

        Raises:
            RuntimeError: If called before `finalize()` / `export()`.
        """
        if self.bastion is None:
            raise RuntimeError(
                f"LandingZone '{self.name}': the Bastion does not exist yet. Call finalize() or export() first."
            )
        return self.bastion.get_bastion_endpoint()

    def get_admin_group_id(self) -> pulumi.Output[str]:
        """Return the OCID of the compartment admin IAM group.

        Returns:
            `pulumi.Output[str]` resolving to the IAM group OCID.
        """
        return self.admin_group.get_group_id()


__all__ = ["LandingZone"]
