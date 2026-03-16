"""VCN Flow Log observability block for the CloudSpells framework.

Provides `VcnFlowLogs`, which provisions an OCI Logging Log Group
dedicated to network audit traffic and one VCN Flow Log per subnet tier.

**Architecture**

A single `oci.logging.LogGroup` named `{stack}-{name}-network-audit` is
created as the common container.  Four `oci.logging.Log` resources — one
per subnet tier (public, private, secure, management) — are created as
SERVICE logs against the `flowlogs` OCI service.  Each log captures all
accepted and rejected traffic on its subnet.

**Retention**

Log retention is configurable via retention_duration (default 90 days).

Exports:
    VcnFlowLogs
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci

from core.base import BaseResource
from providers.oci.network import Vcn


class VcnFlowLogs(BaseResource):
    """VCN Flow Logs for all four subnet tiers collected under one Log Group.

    Creates:

    - One `oci.logging.LogGroup` (`{stack}-{name}-network-audit`).
    - Four `oci.logging.Log` resources — one per subnet tier — configured
      as SERVICE logs against the OCI `flowlogs` service.

    The Log Group OCID is exported as a Pulumi stack output so it can be used
    as an audit-trail reference by other stacks or compliance tooling.

    Attributes:
        log_group: The `oci.logging.LogGroup` resource.
        log_group_id: `pulumi.Output[str]` OCID of the log group.
        public_flow_log: Flow log for the public (LB) subnet.
        private_flow_log: Flow log for the private (App) subnet.
        secure_flow_log: Flow log for the secure (DB) subnet.
        management_flow_log: Flow log for the management subnet.

    Example:
        ```python
        vcn = Vcn(name="lab", compartment_id=compartment_id)
        flow_logs = VcnFlowLogs(name="lab", vcn=vcn)  # finalize_network() called automatically
        pulumi.export("log_group_id", flow_logs.log_group_id)
        ```
    """

    log_group: oci.logging.LogGroup
    log_group_id: pulumi.Output[str]
    public_flow_log: oci.logging.Log
    private_flow_log: oci.logging.Log
    secure_flow_log: oci.logging.Log
    management_flow_log: oci.logging.Log

    def __init__(
        self,
        name: str,
        vcn: Vcn,
        retention_duration: int = 90,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Provision the network-audit Log Group and per-subnet flow logs.

        Args:
            name: Logical name for this logging component (e.g. `"lab"`).
            vcn: The `Vcn` whose subnets will be monitored.
                `Vcn.finalize_network` is called automatically if needed.
                Compartment OCID is derived from vcn automatically.
            retention_duration: Log retention in days.  Accepted values are
                `30`, `60`, `90`, `120`, `150`, `180`.
                Defaults to `90`.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            opts: Pulumi resource options forwarded to the component.

        """
        super().__init__(
            "custom:network:VcnFlowLogs",
            name,
            vcn.compartment_id,
            stack_name,
            opts,
        )
        self._vcn = vcn
        self._retention_duration = retention_duration

        self._create_log_group()
        self._create_flow_logs()

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
                {"LogPurpose": "network-audit", "Compliance": "true"},
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.log_group_id = self.log_group.id

    def _flow_log(self, tier: str, subnet: oci.core.Subnet) -> oci.logging.Log:
        """Create a VCN Flow Log `oci.logging.Log` for a single subnet.

        Args:
            tier: Short tier label (`"public"`, `"private"`, etc.)
                used in the resource name.
            subnet: The `oci.core.Subnet` resource to attach the flow log
                to.  Its `id` is used as the log source resource OCID.

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
                    resource=subnet.id,
                    service="flowlogs",
                    source_type="OCISERVICE",
                ),
                compartment_id=self.compartment_id,
            ),
            is_enabled=True,
            retention_duration=self._retention_duration,
            freeform_tags=self.create_freeform_tags(
                log_name,
                "flow-log",
                {"SubnetTier": tier, "LogPurpose": "network-audit"},
            ),
            opts=pulumi.ResourceOptions(parent=self, depends_on=[self.log_group]),
        )

    def export(self) -> None:
        """Export the network-audit log group OCID as a Pulumi stack output.

        Registers `network_audit_log_group_id` so other stacks and compliance
        tooling can reference the log group without duplicating its OCID.

        Example:
            ```python
            flow_logs = VcnFlowLogs(name="lab", vcn=vcn)
            flow_logs.export()
            # Stack output: network_audit_log_group_id = ocid1.loggroup...
            ```
        """
        pulumi.export("network_audit_log_group_id", self.log_group_id)

    def _create_flow_logs(self) -> None:
        """Create one flow log resource per subnet tier.

        Calls `Vcn.finalize_network` automatically to ensure subnets exist.
        """
        self._vcn.finalize_network()
        assert self._vcn.public_subnet is not None
        assert self._vcn.private_subnet is not None
        assert self._vcn.secure_subnet is not None
        assert self._vcn.management_subnet is not None

        self.public_flow_log = self._flow_log("public", self._vcn.public_subnet)
        self.private_flow_log = self._flow_log("private", self._vcn.private_subnet)
        self.secure_flow_log = self._flow_log("secure", self._vcn.secure_subnet)
        self.management_flow_log = self._flow_log("management", self._vcn.management_subnet)
