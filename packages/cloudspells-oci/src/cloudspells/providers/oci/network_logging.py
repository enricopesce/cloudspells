"""VCN Flow Log observability block for the CloudSpells framework.

Provides `VcnFlowLogs`, which provisions an OCI Logging Log Group
dedicated to network audit traffic and one VCN Flow Log per subnet tier.

**Architecture**

A single `oci.logging.LogGroup` named `{stack}-{name}-network-audit` is
created as the common container.  Up to four `oci.logging.Log` resources —
one per subnet tier (public, private, secure, management) — are created as
SERVICE logs against the `flowlogs` OCI service.  Each log captures all
accepted and rejected traffic on its subnet.

Secure and management flow logs are created only when those subnets are
present — they may be absent when `VcnRef` is used and the upstream stack
did not export those subnet IDs.

**Retention**

Log retention is configurable via `retention_duration` (default 90 days).
OCI accepts only the discrete values `30`, `60`, `90`, `120`, `150`, `180`;
any other value raises `ValueError` at construction time.

Exports:
    VcnFlowLogs
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from cloudspells.core.base import BaseResource

from .network import Vcn, VcnRef

# OCI accepts only these discrete log-retention periods (days).
_VALID_RETENTION: frozenset[int] = frozenset({30, 60, 90, 120, 150, 180})


class VcnFlowLogs(BaseResource):
    """VCN Flow Logs for all four subnet tiers collected under one Log Group.

    Accepts both a live `Vcn` and a cross-stack `VcnRef`.  When a `Vcn` is
    supplied, `finalize_network` is called automatically to materialise
    subnets before attaching the flow logs.  For a `VcnRef` the call is a
    no-op (the remote stack owns that lifecycle).

    Secure and management flow logs are created only when those subnets
    exist — they are always present for a `Vcn`, but may be absent on a
    `VcnRef` if the upstream stack did not export those subnet IDs.

    Creates:

    - One `oci.logging.LogGroup` (`{stack}-{name}-network-audit`).
    - Two to four `oci.logging.Log` resources (one per existing subnet tier)
      configured as SERVICE logs against the OCI `flowlogs` service.

    To expose the Log Group OCID as a Pulumi stack output for cross-stack
    references or compliance tooling, call `export()` after construction.

    Attributes:
        log_group: The `oci.logging.LogGroup` resource.
        log_group_id: `pulumi.Output[str]` OCID of the log group.
        public_flow_log: Flow log for the public (LB) subnet.
        private_flow_log: Flow log for the private (App) subnet.
        secure_flow_log: Flow log for the secure (DB) subnet, or `None`
            if that subnet was not exported by the upstream stack.
        management_flow_log: Flow log for the management subnet, or `None`
            if that subnet was not exported by the upstream stack.

    Example:
        ```python
        vcn = Vcn(name="lab", compartment_id=compartment_id)
        flow_logs = VcnFlowLogs(
            name="lab", compartment_id=compartment_id, vcn=vcn
        )  # finalize_network() called automatically

        # Optionally publish the log group OCID as a stack output
        flow_logs.export()
        ```
    """

    log_group: oci.logging.LogGroup
    log_group_id: pulumi.Output[str]
    public_flow_log: oci.logging.Log
    private_flow_log: oci.logging.Log
    secure_flow_log: oci.logging.Log | None
    management_flow_log: oci.logging.Log | None

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        retention_duration: int = 90,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Provision the network-audit Log Group and per-subnet flow logs.

        Args:
            name: Logical name for this logging component (e.g. `"lab"`).
            compartment_id: OCID of the OCI compartment to deploy into.
                Required explicitly because `VcnRef` does not carry a
                compartment ID — only live `Vcn` objects do.
            vcn: The `Vcn` or `VcnRef` whose subnets will be monitored.
                `Vcn.finalize_network` is called automatically when a live
                `Vcn` is passed; the call is a no-op for `VcnRef`.
            retention_duration: Log retention in days.  Accepted values are
                `30`, `60`, `90`, `120`, `150`, `180`.
                Defaults to `90`.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `retention_duration` is not one of the discrete
                values accepted by OCI (`30`, `60`, `90`, `120`, `150`,
                `180`).
        """
        # Bridge gap: validate against OCI-accepted discrete retention values.
        if retention_duration not in _VALID_RETENTION:
            raise ValueError(f"retention_duration must be one of {sorted(_VALID_RETENTION)}, got {retention_duration}")

        super().__init__(
            "custom:network:VcnFlowLogs",
            name,
            compartment_id,
            stack_name,
            opts,
        )
        self._vcn = vcn
        self._retention_duration = retention_duration

        self._create_log_group()
        self._create_flow_logs()

        # Bridge gap: register component outputs so Pulumi records log_group_id
        # in state and `pulumi stack output` reflects it — consistent with every
        # other CloudSpells spell that calls register_outputs() at construction.
        self.register_outputs({"log_group_id": self.log_group_id})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_log_group(self) -> None:
        """Create the network-audit Log Group resource."""
        lg_name = self.create_resource_name("network-audit")
        self.log_group = oci.logging.LogGroup(
            lg_name,
            compartment_id=self.compartment_id,
            display_name=lg_name,
            description=(
                "Network audit log group for VCN flow logs. Captures accepted and rejected traffic on all subnet tiers."
            ),
            freeform_tags=self.create_freeform_tags(
                lg_name,
                "log-group",
                {"log-purpose": "network-audit", "compliance": "true"},
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.log_group_id = self.log_group.id

    def _flow_log(self, tier: str, subnet_id: pulumi.Input[str]) -> oci.logging.Log:
        """Create a VCN Flow Log `oci.logging.Log` for a single subnet.

        Accepts a plain `pulumi.Input[str]` subnet OCID so the method works
        identically for both `oci.core.Subnet.id` (live `Vcn`) and
        `_SubnetRef.id` (cross-stack `VcnRef`).

        Args:
            tier: Short tier label (`"public"`, `"private"`, etc.)
                used in the resource name.
            subnet_id: The subnet OCID to attach the flow log to.
                Pass `subnet.id` for both `oci.core.Subnet` and `_SubnetRef`.

        Returns:
            The newly created `oci.logging.Log` resource.
        """
        log_name = self.create_resource_name(f"flow-log-{tier}")
        return oci.logging.Log(
            log_name,
            display_name=log_name,
            log_group_id=self.log_group.id,
            log_type="SERVICE",
            configuration=oci.logging.LogConfigurationArgs(
                source=oci.logging.LogConfigurationSourceArgs(
                    category="all",
                    resource=subnet_id,
                    service="flowlogs",
                    source_type="OCISERVICE",
                ),
                # Explicit archiving compartment — defaults to log group
                # compartment when omitted, but set here for clarity.
                compartment_id=self.compartment_id,
            ),
            is_enabled=True,
            retention_duration=self._retention_duration,
            freeform_tags=self.create_freeform_tags(
                log_name,
                "flow-log",
                {"subnet-tier": tier, "log-purpose": "network-audit"},
            ),
            opts=pulumi.ResourceOptions(parent=self, depends_on=[self.log_group]),
        )

    def _create_flow_logs(self) -> None:
        """Create one flow log resource per existing subnet tier.

        Calls `finalize_network` so that subnets exist before attaching logs.
        For a `VcnRef` this call is a no-op (the remote stack owns subnets).
        Secure and management logs are skipped when those subnets are absent
        (possible for `VcnRef` when upstream did not export those IDs).
        """
        # Bridge gap: finalize_network() is a no-op for VcnRef — safe to call
        # unconditionally on both Vcn and VcnRef.
        self._vcn.finalize_network()

        pub = self._vcn.public_subnet
        priv = self._vcn.private_subnet
        sec = self._vcn.secure_subnet
        mgmt = self._vcn.management_subnet

        assert pub is not None, "public_subnet must exist after finalize_network"
        assert priv is not None, "private_subnet must exist after finalize_network"

        self.public_flow_log = self._flow_log("public", pub.id)
        self.private_flow_log = self._flow_log("private", priv.id)

        # Bridge gap: secure/management may be absent on a VcnRef — guard and
        # set attributes to None so callers can check before using them.
        self.secure_flow_log = self._flow_log("secure", sec.id) if sec else None
        self.management_flow_log = self._flow_log("management", mgmt.id) if mgmt else None

    def export(self) -> None:
        """Export the network-audit log group OCID as a Pulumi stack output.

        Registers `network_audit_log_group_id` so other stacks and compliance
        tooling can reference the log group without duplicating its OCID.

        Example:
            ```python
            flow_logs = VcnFlowLogs(
                name="lab", compartment_id=compartment_id, vcn=vcn
            )
            flow_logs.export()
            # Stack output: network_audit_log_group_id = ocid1.loggroup...
            ```
        """
        pulumi.export("network_audit_log_group_id", self.log_group_id)
