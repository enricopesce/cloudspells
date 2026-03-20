"""Highly secure, monitored OCI VCN — production-ready reference deployment.

## Architecture

This example deploys the complete CloudSpells secure-network stack:

```
┌─────────────────────────────────────────────────────────────────┐
│  VCN  10.0.0.0/18  (default)                                    │
│                                                                 │
│  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Public /21      │  │ Private /19                          │  │
│  │ (LB tier)       │  │ (App tier)                           │  │
│  │ IGW route       │  │ NAT GW + Service GW routes           │  │
│  │ lb-nsg ──────────┼──► app-nsg                             │  │
│  └─────────────────┘  └──────────────────┬───────────────────┘  │
│                                          │ TCP {db_port}        │
│  ┌────────────────────────────────────────▼───────────────────┐  │
│  │ Secure /20 (DB tier)                                       │  │
│  │ Service GW route only — NO internet path                   │  │
│  │ db-nsg                                                     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Management /21                                             │  │
│  │ Service GW route only                                      │  │
│  │ mgmt-nsg ──► SSH to LB + app + DB tiers                   │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Security model

Each NSG is assigned a **role** that declares its security posture.  The
role auto-generates:

- Ambient NSG rules (service / internet egress) for the VNIC.
- The matching subnet Security List rules so OCI's two enforcement layers
  align — no manual `add_rule` boilerplate needed.

`lb_nsg.serves(app_nsg, port=app_port)` generates four rules in one line:

- lb-nsg  → EGRESS  → app-nsg on {app_port}  (NSG-to-NSG)
- app-nsg ← INGRESS ← lb-nsg  on {app_port}  (NSG-to-NSG)
- lb-nsg  → EGRESS  → app-nsg on 22 (SSH management)
- app-nsg ← INGRESS ← lb-nsg  on 22 (SSH management)

…plus the corresponding cross-subnet Security List rules.

## Zero Trust tagging

Every NSG is tagged with `ZprLabel=tier:<name>`.  Enable **Zero Trust
Packet Routing (ZPR)** in your tenancy and create a ZPR policy referencing
these labels to enforce identity-based traffic filtering at the OCI control
plane level — a guarantee that no misconfigured VNIC attachment can bypass
the NSG rules:

```
Define policy "network-zpr-policy" as
  allow private-nsg to connect to secure-nsg on TCP port 1521
  where target.security-attribute.ZprLabel = 'tier:secure'
```

## Configuration

Required Pulumi config values (set with `pulumi config set`):

- `compartment_ocid` — OCID of the OCI compartment to deploy into.

Optional:

- `vcn_cidr` — VCN IPv4 CIDR block (default: `10.0.0.0/18`).
- `management_ingress_cidr` — CIDR allowed to SSH into the management tier
  (default: `0.0.0.0/0` — **restrict before go-live**).
- `app_port` — TCP port the app-tier listens on (default: `8080`).
- `db_port` — Database TCP port (default: `1521`).
- `log_retention_days` — Flow-log retention in days: 30/60/90/120/150/180 (default: `90`).

## Stack outputs

- `vcn_id` — VCN OCID
- `public_subnet_id` — Public (LB) subnet OCID
- `private_subnet_id` — Private (App) subnet OCID
- `secure_subnet_id` — Secure (DB) subnet OCID
- `management_subnet_id` — Management subnet OCID
- `network_audit_log_group_id` — Log Group OCID for network audit logs
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE, MANAGEMENT

# ── Configuration ─────────────────────────────────────────────────────────────

config = Config()

compartment_id: str = config.require("compartment_ocid")
vcn_cidr: str = config.get("vcn_cidr") or "10.0.0.0/18"
management_ingress_cidr: str = config.get("management_ingress_cidr") or "0.0.0.0/0"
app_port: int = config.get_int("app_port") or 8080
db_port: int = config.get_int("db_port") or 1521
log_retention_days: int = config.get_int("log_retention_days") or 90

# ── Step 1 — VCN ──────────────────────────────────────────────────────────────
#
# Vcn() creates the VCN, Internet GW, NAT GW, Service GW, and four route
# tables immediately.  Security lists and subnets are deferred until
# finalize_network() is called.

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr,
    flow_logs=True,
    flow_logs_retention=log_retention_days,
)

# ── Step 2 — NSG roles ────────────────────────────────────────────────────────
#
# Each NSG declares what it IS (its role / security posture).  Ambient rules
# are generated automatically — no add_rule() boilerplate needed.
#
#   INTERNET_EDGE  → public subnet, accepts HTTP/HTTPS from 0.0.0.0/0
#   APP_SERVER     → private subnet, egresses to services + internet (NAT)
#   DATABASE       → secure subnet, egresses to Oracle Services only
#   MANAGEMENT     → management subnet, egresses to Oracle Services only

lb_nsg: Nsg = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS], vcn=vcn, compartment_id=compartment_id)
app_nsg: Nsg = Nsg("app-server", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)
db_nsg: Nsg = Nsg("database", role=DATABASE, vcn=vcn, compartment_id=compartment_id)
mgmt_nsg: Nsg = Nsg("management", role=MANAGEMENT, vcn=vcn, compartment_id=compartment_id)

# Management tier accepts SSH from the ops network.
# ⚠ Restrict management_ingress_cidr to your actual management CIDR before go-live.
mgmt_nsg.allow_from_cidr("ssh-in", SSH, management_ingress_cidr, description="SSH from ops network ⚠ restrict in prod")

# ── Step 3 — Traffic relationships ────────────────────────────────────────────
#
# One call per hop.  Each generates bilateral NSG rules (app port + SSH
# management channel) and the matching cross-subnet Security List rules.

lb_nsg.serves(app_nsg, port=app_port)  # LB → app: app port + SSH mgmt
app_nsg.serves(db_nsg, port=db_port)  # app → DB: db port + SSH mgmt

# Management tier manages all other tiers directly over SSH.
# with_ssh=False because the declared port IS SSH — no extra channel needed.
mgmt_nsg.serves(lb_nsg, port=SSH, with_ssh=False)  # mgmt → LB: SSH only
mgmt_nsg.serves(app_nsg, port=SSH, with_ssh=False)  # mgmt → app: SSH only
mgmt_nsg.serves(db_nsg, port=SSH, with_ssh=False)  # mgmt → DB: SSH only

# ── Stack outputs ──────────────────────────────────────────────────────────────
#
# vcn.export() also publishes network_audit_log_group_id when flow_logs=True.
vcn.export()
