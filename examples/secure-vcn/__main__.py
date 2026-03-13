"""Highly secure, monitored OCI VCN — production-ready reference deployment.

Architecture
============
This example deploys the complete OCIBlocks secure-network stack:

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────┐
    │  VCN  10.0.0.0/16                                               │
    │                                                                 │
    │  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
    │  │ Public /19      │  │ Private /17                          │  │
    │  │ (LB tier)       │  │ (App tier)                           │  │
    │  │ IGW route       │  │ NAT GW + Service GW routes           │  │
    │  │ public-nsg ──────┼──► private-nsg                         │  │
    │  └─────────────────┘  └──────────────────┬───────────────────┘  │
    │                                          │ TCP 1521             │
    │  ┌────────────────────────────────────────▼───────────────────┐  │
    │  │ Secure /18 (DB tier)                                       │  │
    │  │ Service GW route only — NO internet path                   │  │
    │  │ secure-nsg                                                 │  │
    │  └────────────────────────────────────────────────────────────┘  │
    │                                                                 │
    │  ┌────────────────────────────────────────────────────────────┐  │
    │  │ Management /19                                             │  │
    │  │ Service GW route only                                      │  │
    │  │ management-nsg ──► SSH to private + secure tiers           │  │
    │  └────────────────────────────────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────────┘

Security layers
---------------
1. **Subnet Security Lists** (OCI default): broad subnet-boundary controls
   managed by the ``Vcn`` block.
2. **NSGs** (resource-level): explicit-allow / implicit-deny-all rules per
   tier, managed by ``VcnNsgPolicy``.  Attach the relevant NSG OCID to each
   VNIC so only authorised traffic flows between tiers.
3. **VCN Flow Logs**: all-traffic capture per subnet, written to the
   ``{stack}-lab-network-audit`` Log Group for incident response and
   compliance.

Zero Trust tagging
------------------
Every NSG is tagged with ``ZprLabel=tier:<name>``.  Enable **Zero Trust
Packet Routing (ZPR)** in your tenancy and create a ZPR policy referencing
these labels to enforce identity-based traffic filtering at the OCI control
plane level — a guarantee that no misconfigured VNIC attachment can bypass
the NSG rules::

    Define policy "network-zpr-policy" as
      allow private-nsg to connect to secure-nsg on TCP port 1521
      where target.security-attribute.ZprLabel = 'tier:secure'

Configuration
-------------
Required Pulumi config values (set with ``pulumi config set``):

    ``compartment_ocid``
        OCID of the OCI compartment to deploy into.

Optional:

    ``vcn_cidr``
        VCN IPv4 CIDR block (default: ``10.0.0.0/16``).
    ``management_ingress_cidr``
        CIDR allowed to SSH into the management tier
        (default: ``0.0.0.0/0`` — **restrict before go-live**).
    ``app_port``
        TCP port the app-tier listens on (default: ``8080``).
    ``log_retention_days``
        Flow-log retention in days: 30/60/90/120/150/180 (default: ``90``).

Stack outputs
-------------
``vcn_id``                    VCN OCID
``public_subnet_id``          Public (LB) subnet OCID
``private_subnet_id``         Private (App) subnet OCID
``secure_subnet_id``          Secure (DB) subnet OCID
``management_subnet_id``      Management subnet OCID
``public_nsg_id``             Public NSG OCID — attach to LB VNICs
``private_nsg_id``            Private NSG OCID — attach to App VNICs
``secure_nsg_id``             Secure NSG OCID — attach to DB VNICs
``management_nsg_id``         Management NSG OCID — attach to Ops VNICs
``network_audit_log_group_id`` Log Group OCID for network audit logs
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi
from providers.oci.network import Vcn
from providers.oci.nsg import Nsg, TCP, ALL, SVC_CIDR, tcp_port, icmp_opts
from providers.oci.network_logging import VcnFlowLogs

# ── Configuration ────────────────────────────────────────────────────────────

config: pulumi.Config = pulumi.Config()

compartment_id: str = config.require("compartment_ocid")
vcn_cidr: str = config.get("vcn_cidr") or "10.0.0.0/16"
management_ingress_cidr: str = config.get("management_ingress_cidr") or "0.0.0.0/0"
app_port: int = config.get_int("app_port") or 8080
db_port: int = config.get_int("db_port") or 1521
log_retention_days: int = config.get_int("log_retention_days") or 90

# ── Step 1 — VCN with gateways and route tables ──────────────────────────────
#
# Vcn() creates the VCN, Internet GW, NAT GW, Service GW, and four route
# tables immediately.  Security lists and subnets are deferred until
# finalize_network() is called.

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr,
)

# ── Step 2 — NSGs (one per service role) ─────────────────────────────────────
#
# Each Nsg is a named policy for a class of resource — attach the right one
# to each VM's VNIC via nsg_ids.  All rules are explicit; no defaults.
#
# ⚠  Restrict management_ingress_cidr to your actual management network
#    before promoting to production.

lb_nsg:   Nsg = Nsg("load-balancer", vcn=vcn, compartment_id=compartment_id)
app_nsg:  Nsg = Nsg("app-server",    vcn=vcn, compartment_id=compartment_id)
db_nsg:   Nsg = Nsg("database",      vcn=vcn, compartment_id=compartment_id)
mgmt_nsg: Nsg = Nsg("management",    vcn=vcn, compartment_id=compartment_id)

# load-balancer NSG
lb_nsg.add_rule("https-in", direction="INGRESS", protocol=TCP,
                source="0.0.0.0/0", source_type="CIDR_BLOCK",
                tcp_options=tcp_port(443), description="HTTPS from internet")
lb_nsg.add_rule("http-in", direction="INGRESS", protocol=TCP,
                source="0.0.0.0/0", source_type="CIDR_BLOCK",
                tcp_options=tcp_port(80), description="HTTP from internet")
lb_nsg.add_rule("icmp-in", direction="INGRESS", protocol="1",
                source="0.0.0.0/0", source_type="CIDR_BLOCK",
                icmp_options=icmp_opts(3, 4), description="ICMP Path-MTU inbound")
lb_nsg.add_rule("ssh-mgmt-in", direction="INGRESS", protocol=TCP,
                source=mgmt_nsg.id, source_type="NETWORK_SECURITY_GROUP",
                tcp_options=tcp_port(22), description="SSH from management NSG")
lb_nsg.add_rule("app-out", direction="EGRESS", protocol=TCP,
                destination=app_nsg.id, destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=tcp_port(app_port),
                description=f"TCP {app_port} to app-server NSG")
lb_nsg.add_rule("icmp-out", direction="EGRESS", protocol="1",
                destination="0.0.0.0/0", destination_type="CIDR_BLOCK",
                icmp_options=icmp_opts(3, 4), description="ICMP Path-MTU outbound")

# app-server NSG
app_nsg.add_rule("app-in", direction="INGRESS", protocol=TCP,
                 source=lb_nsg.id, source_type="NETWORK_SECURITY_GROUP",
                 tcp_options=tcp_port(app_port),
                 description=f"TCP {app_port} from load-balancer NSG")
app_nsg.add_rule("ssh-mgmt-in", direction="INGRESS", protocol=TCP,
                 source=mgmt_nsg.id, source_type="NETWORK_SECURITY_GROUP",
                 tcp_options=tcp_port(22), description="SSH from management NSG")
app_nsg.add_rule("icmp-in", direction="INGRESS", protocol="1",
                 source="0.0.0.0/0", source_type="CIDR_BLOCK",
                 icmp_options=icmp_opts(3, 4), description="ICMP Path-MTU inbound")
app_nsg.add_rule("svc-out", direction="EGRESS", protocol=ALL,
                 destination=SVC_CIDR, destination_type="SERVICE_CIDR_BLOCK",
                 description="Oracle Services (Service GW)")
app_nsg.add_rule("inet-out", direction="EGRESS", protocol=ALL,
                 destination="0.0.0.0/0", destination_type="CIDR_BLOCK",
                 description="Internet egress via NAT GW")
app_nsg.add_rule("db-out", direction="EGRESS", protocol=TCP,
                 destination=db_nsg.id, destination_type="NETWORK_SECURITY_GROUP",
                 tcp_options=tcp_port(db_port),
                 description=f"DB port {db_port} to database NSG")

# database NSG
db_nsg.add_rule("db-in", direction="INGRESS", protocol=TCP,
                source=app_nsg.id, source_type="NETWORK_SECURITY_GROUP",
                tcp_options=tcp_port(db_port),
                description=f"DB port {db_port} from app-server NSG")
db_nsg.add_rule("ssh-mgmt-in", direction="INGRESS", protocol=TCP,
                source=mgmt_nsg.id, source_type="NETWORK_SECURITY_GROUP",
                tcp_options=tcp_port(22), description="SSH from management NSG")
db_nsg.add_rule("svc-out", direction="EGRESS", protocol=ALL,
                destination=SVC_CIDR, destination_type="SERVICE_CIDR_BLOCK",
                description="Oracle Services only — no internet")

# management NSG
mgmt_nsg.add_rule("ssh-in", direction="INGRESS", protocol=TCP,
                  source=management_ingress_cidr, source_type="CIDR_BLOCK",
                  tcp_options=tcp_port(22),
                  description="SSH from ops network ⚠ restrict in prod")
mgmt_nsg.add_rule("ssh-app-out", direction="EGRESS", protocol=TCP,
                  destination=app_nsg.id, destination_type="NETWORK_SECURITY_GROUP",
                  tcp_options=tcp_port(22), description="SSH to app-server NSG")
mgmt_nsg.add_rule("ssh-db-out", direction="EGRESS", protocol=TCP,
                  destination=db_nsg.id, destination_type="NETWORK_SECURITY_GROUP",
                  tcp_options=tcp_port(22), description="SSH to database NSG")
mgmt_nsg.add_rule("svc-out", direction="EGRESS", protocol=ALL,
                  destination=SVC_CIDR, destination_type="SERVICE_CIDR_BLOCK",
                  description="Oracle Services for OCI API calls")

# ── Step 3 — Finalize subnets and security lists ─────────────────────────────
#
# This is the only manual call required when no other service block (OKE,
# ComputeInstance, ScalableWorkload) is used.  It creates the four security
# lists and four subnets from the accumulated rules.  Subsequent calls are
# no-ops.

vcn.finalize_network()

# ── Step 4 — VCN Flow Logs (observability) ───────────────────────────────────
#
# VcnFlowLogs must come after finalize_network() because it needs the subnet
# OCIDs that are created by that call.

flow_logs: VcnFlowLogs = VcnFlowLogs(
    name="lab",
    vcn=vcn,
    retention_duration=log_retention_days,
)

# ── Stack outputs ─────────────────────────────────────────────────────────────
#
# All relevant OCIDs are exported so downstream stacks can consume them via
# VcnRef.from_stack_reference() or pulumi.StackReference().

vcn.export()  # publishes the 14 canonical VCN outputs expected by VcnRef

pulumi.export("lb_nsg_id",   lb_nsg.id)
pulumi.export("app_nsg_id",  app_nsg.id)
pulumi.export("db_nsg_id",   db_nsg.id)
pulumi.export("mgmt_nsg_id", mgmt_nsg.id)
pulumi.export("network_audit_log_group_id", flow_logs.log_group_id)
