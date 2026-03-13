"""Load balancer + 2 web backends + 2 database VMs — role-based NSG security.

Architecture
============

.. code-block:: text

    Internet
       │  HTTP 80 / HTTPS 443 / SSH 22
       ▼
    ┌─────────────────────────────────────────────────────┐
    │ Public subnet (/19)  — Internet GW route            │
    │  load-balancer  [lb-nsg]                            │
    └──────────────────────┬──────────────────────────────┘
                           │ TCP {app_port}
                           ▼
    ┌─────────────────────────────────────────────────────┐
    │ Private subnet (/17) — NAT GW + Service GW routes   │
    │  web-backend-1  [web-nsg]                           │
    │  web-backend-2  [web-nsg]   ← same NSG, same policy │
    └──────────────────────┬──────────────────────────────┘
                           │ TCP {db_port}
                           ▼
    ┌─────────────────────────────────────────────────────┐
    │ Secure subnet (/18)  — Service GW only (no NAT)     │
    │  db-1  [db-nsg]                                     │
    │  db-2  [db-nsg]             ← same NSG, same policy │
    └─────────────────────────────────────────────────────┘

NSG design
----------
Each NSG represents a **service role**, not a subnet tier.  All VMs of the
same role share the same NSG.  Adding a third web backend requires no NSG
changes — just attach ``web_nsg.id`` to the new ``ComputeInstance``.

NSG rules (all NSG-to-NSG for east-west; CIDR only for internet edge):

lb-nsg   ingress  TCP 80/443/22  from 0.0.0.0/0
         ingress  ICMP 3/4       from 0.0.0.0/0
         egress   TCP {app_port} to web-nsg
         egress   ICMP 3/4       to 0.0.0.0/0

web-nsg  ingress  TCP {app_port} from lb-nsg
         ingress  TCP 22         from lb-nsg
         ingress  ICMP 3/4       from 0.0.0.0/0
         egress   TCP {db_port}  to db-nsg
         egress   TCP 22         to db-nsg
         egress   all            to Oracle Services
         egress   all            to 0.0.0.0/0  (NAT GW)

db-nsg   ingress  TCP {db_port}  from web-nsg
         ingress  TCP 22         from web-nsg
         egress   all            to Oracle Services only

Security Lists (subnet boundary) mirror the same rules so that both OCI
enforcement layers align.

Configuration
-------------
Required:

    ``compartment_ocid``   OCID of the target compartment.

Optional:

    ``ssh_key``            SSH public key installed on all VMs.
    ``vcn_cidr``           VCN CIDR block (default: ``10.0.0.0/16``).
    ``app_port``           Backend app TCP port (default: ``8080``).
    ``db_port``            Database TCP port (default: ``5432``).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi
from providers.oci.network import Vcn, SUBNET_PUBLIC, SUBNET_PRIVATE, SUBNET_SECURE
from providers.oci.compute import ComputeInstance
from providers.oci.nsg import Nsg, INTERNET, HTTP, HTTPS, SSH
from providers.oci.volume import VolumeSpec
from core.abstractions.network import (
    SecurityRules, CLOUD_SERVICES,
    tcp_ingress, icmp_path_mtu_ingress,
    all_egress, icmp_path_mtu_egress,
)

# ── Configuration ─────────────────────────────────────────────────────────────

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
ssh_key: str | None = config.get("ssh_key")
vcn_cidr: str = config.get("vcn_cidr") or "10.0.0.0/16"
app_port: int = config.get_int("app_port") or 8080
db_port: int = config.get_int("db_port") or 5432

# ── Step 1 — VCN ──────────────────────────────────────────────────────────────

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr,
)

# ── Step 2 — NSGs (one per service role) ──────────────────────────────────────
#
# Each NSG is a named policy for a class of resource.  The same NSG is
# attached to every VM of that role — no per-VM NSG is needed.
# NSG OCIDs are available immediately for use in NSG-to-NSG rules below.

lb_nsg:  Nsg = Nsg("load-balancer", vcn=vcn, compartment_id=compartment_id)
web_nsg: Nsg = Nsg("web-backend",   vcn=vcn, compartment_id=compartment_id)
db_nsg:  Nsg = Nsg("database",      vcn=vcn, compartment_id=compartment_id)

# ── Step 3 — NSG rules ────────────────────────────────────────────────────────
#
# East-west rules use NSG-to-NSG references (no CIDRs) — only the exact VMs
# carrying the source NSG can send traffic to the destination NSG.

# ── lb-nsg ────────────────────────────────────────────────────────────────────

lb_nsg.allow_from_cidr("https-in", HTTPS, INTERNET)
lb_nsg.allow_from_cidr("http-in",  HTTP,  INTERNET)
lb_nsg.allow_from_cidr("ssh-in",   SSH,   INTERNET)
lb_nsg.allow_icmp_path_mtu_in("icmp-in")
lb_nsg.allow_to_nsg("app-out", web_nsg, app_port)
lb_nsg.allow_icmp_path_mtu_out("icmp-out")

# ── web-nsg ───────────────────────────────────────────────────────────────────

web_nsg.allow_from_nsg("app-in",  lb_nsg, app_port)
web_nsg.allow_from_nsg("ssh-in",  lb_nsg, SSH)
web_nsg.allow_icmp_path_mtu_in("icmp-in")
web_nsg.allow_to_nsg("db-out",     db_nsg, db_port)
web_nsg.allow_to_nsg("ssh-db-out", db_nsg, SSH)
web_nsg.allow_to_services("svc-out")
web_nsg.allow_to_cidr("inet-out", INTERNET)

# ── db-nsg ────────────────────────────────────────────────────────────────────

db_nsg.allow_from_nsg("db-in",  web_nsg, db_port)
db_nsg.allow_from_nsg("ssh-in", web_nsg, SSH)
db_nsg.allow_to_services("svc-out")

# ── Step 4 — Security lists + subnets ─────────────────────────────────────────
#
# OCI enforces both the Security List (subnet level) and the NSG (VNIC level).
# The Security List is the outer boundary; the NSG is the inner enforcement.

vcn.add_security_rules(SecurityRules(
    public_ingress=[
        tcp_ingress(HTTPS, INTERNET),
        tcp_ingress(HTTP,  INTERNET),
        tcp_ingress(SSH,   INTERNET),
        icmp_path_mtu_ingress(),
    ],
    public_egress=[icmp_path_mtu_egress()],
    private_ingress=[
        tcp_ingress(app_port, vcn.get_public_subnet_cidr()),
        tcp_ingress(SSH,      vcn.get_public_subnet_cidr()),
    ],
    private_egress=[
        all_egress(CLOUD_SERVICES),
        all_egress(INTERNET),
    ],
    secure_ingress=[
        tcp_ingress(db_port, vcn.get_private_subnet_cidr()),
        tcp_ingress(SSH,     vcn.get_private_subnet_cidr()),
    ],
    secure_egress=[all_egress(CLOUD_SERVICES)],
))

vcn.finalize_network()

# ── Step 5 — Compute instances ────────────────────────────────────────────────
#
# Each VM receives the NSG that matches its role.  Adding more VMs of the
# same role requires no NSG changes — just pass the same nsg_ids.

load_balancer: ComputeInstance = ComputeInstance(
    name="load-balancer",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    subnet=SUBNET_PUBLIC,
    nsg_ids=[lb_nsg.id],
)

web_backend_1: ComputeInstance = ComputeInstance(
    name="web-backend-1",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    subnet=SUBNET_PRIVATE,
    nsg_ids=[web_nsg.id],
)

web_backend_2: ComputeInstance = ComputeInstance(
    name="web-backend-2",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    subnet=SUBNET_PRIVATE,
    nsg_ids=[web_nsg.id],  # same NSG as web-backend-1
)

db_1: ComputeInstance = ComputeInstance(
    name="db-1",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    subnet=SUBNET_SECURE,
    nsg_ids=[db_nsg.id],
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)

db_2: ComputeInstance = ComputeInstance(
    name="db-2",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    subnet=SUBNET_SECURE,
    nsg_ids=[db_nsg.id],  # same NSG as db-1
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)

# ── Stack outputs ─────────────────────────────────────────────────────────────

vcn.export()
pulumi.export("lb_nsg_id",  lb_nsg.id)
pulumi.export("web_nsg_id", web_nsg.id)
pulumi.export("db_nsg_id",  db_nsg.id)
load_balancer.export()
web_backend_1.export()
web_backend_2.export()
db_1.export()
db_2.export()
