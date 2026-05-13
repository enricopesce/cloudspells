"""Load balancer + 2 web backends + 2 database VMs — role-based security.

## Architecture

```
Internet
   │  HTTP 80 / HTTPS 443 / SSH 22
   ▼
┌─────────────────────────────────────────────────────┐
│ Public subnet (/21)  — Internet GW route            │
│  load-balancer  [lb-nsg  · INTERNET_EDGE]           │
└──────────────────────┬──────────────────────────────┘
                       │ TCP {app_port} + SSH 22
                       ▼
┌─────────────────────────────────────────────────────┐
│ Private subnet (/19) — NAT GW + Service GW routes   │
│  web-backend-1  [web-nsg · APP_SERVER]              │
│  web-backend-2  [web-nsg · APP_SERVER]              │
└──────────────────────┬──────────────────────────────┘
                       │ TCP {db_port} + SSH 22
                       ▼
┌─────────────────────────────────────────────────────┐
│ Secure subnet (/20)  — Service GW only (no NAT)     │
│  db-1  [db-nsg · DATABASE]                          │
│  db-2  [db-nsg · DATABASE]                          │
└─────────────────────────────────────────────────────┘

## Security model

Each NSG is assigned a **role** that declares its security posture.  The
role auto-generates:

- Ambient NSG rules (service/internet egress) for the VNIC.
- The matching subnet Security List rules so OCI's two enforcement layers
  align — no manual `Vcn.add_security_rules` call is needed.

`lb_nsg.serves(web_nsg, port=app_port)` generates four rules in one line:

- lb-nsg  → EGRESS  → web-nsg  on {app_port}  (NSG-to-NSG)
- web-nsg ← INGRESS ← lb-nsg   on {app_port}  (NSG-to-NSG)
- lb-nsg  → EGRESS  → web-nsg  on 22 (SSH management)
- web-nsg ← INGRESS ← lb-nsg   on 22 (SSH management)

…plus the corresponding cross-subnet Security List rules.

Adding a third web backend requires **zero NSG changes** — just attach the
same `web_nsg.id` to the new `ComputeInstance`.

## Configuration

Required:

- `compartment_ocid` — OCID of the target compartment.

Optional:

- `ssh_key` — SSH public key installed on all VMs.
- `vcn_cidr` — VCN CIDR block (default: `10.0.0.0/18`).
- `app_port` — Backend app TCP port (default: `8080`).
- `db_port` — Database TCP port (default: `5432`).
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE
from cloudspells.providers.oci.volume import VolumeSpec

# ── Configuration ─────────────────────────────────────────────────────────────

config = Config()
compartment_id: str = config.require("compartment_ocid")
availability_domain: str = config.require("availability_domain")
ssh_key: str | None = config.get("ssh_key")
vcn_cidr: str = config.get("vcn_cidr") or "10.0.0.0/18"
app_port: int = config.get_int("app_port") or 8080
db_port: int = config.get_int("db_port") or 5432

# ── Step 1 — VCN ──────────────────────────────────────────────────────────────

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr,
)

# ── Step 2 — NSG roles ────────────────────────────────────────────────────────
#
# Each NSG declares what it IS (its role/posture).  Ambient rules are
# generated automatically — no boilerplate allow_* calls needed.
#
#   INTERNET_EDGE  → public subnet, accepts declared edge ports from 0.0.0.0/0
#   APP_SERVER     → private subnet, egresses to services + internet (NAT)
#   DATABASE       → secure subnet, egresses to Oracle Services only

lb_nsg: Nsg = Nsg(
    "load-balancer",
    role=INTERNET_EDGE,
    ports=[HTTP, HTTPS, SSH],
    vcn=vcn,
    compartment_id=compartment_id,
)
web_nsg: Nsg = Nsg("web-backend", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)
db_nsg: Nsg = Nsg("database", role=DATABASE, vcn=vcn, compartment_id=compartment_id)

# ── Step 3 — Traffic relationships ────────────────────────────────────────────
#
# One line per hop.  Each call generates bilateral NSG rules + cross-subnet
# Security List rules automatically.

lb_nsg.serves(web_nsg, port=app_port)  # LB → web: app port + SSH mgmt
web_nsg.serves(db_nsg, port=db_port)  # web → DB: db port + SSH mgmt

# ── Step 4 — Compute instances ────────────────────────────────────────────────
#
# nsg= carries both the VCN and the subnet tier role — no explicit vcn= or
# subnet= needed on ComputeInstance.
# Adding more VMs of the same role requires no NSG changes.

load_balancer: ComputeInstance = ComputeInstance(
    name="load-balancer",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    availability_domain=availability_domain,
    ssh_public_key=ssh_key,
    nsg=lb_nsg,  # VCN and public placement come from INTERNET_EDGE.
)

web_backend_1: ComputeInstance = ComputeInstance(
    name="web-backend-1",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    availability_domain=availability_domain,
    ssh_public_key=ssh_key,
    nsg=web_nsg,  # VCN and private placement come from APP_SERVER.
)

web_backend_2: ComputeInstance = ComputeInstance(
    name="web-backend-2",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    availability_domain=availability_domain,
    ssh_public_key=ssh_key,
    nsg=web_nsg,  # same NSG as web-backend-1
)

db_1: ComputeInstance = ComputeInstance(
    name="db-1",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    availability_domain=availability_domain,
    ssh_public_key=ssh_key,
    nsg=db_nsg,  # VCN and secure placement come from DATABASE.
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)

db_2: ComputeInstance = ComputeInstance(
    name="db-2",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    availability_domain=availability_domain,
    ssh_public_key=ssh_key,
    nsg=db_nsg,  # same NSG as db-1
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)

# ── Stack outputs ─────────────────────────────────────────────────────────────

vcn.export()
load_balancer.export()
web_backend_1.export()
web_backend_2.export()
db_1.export()
db_2.export()
