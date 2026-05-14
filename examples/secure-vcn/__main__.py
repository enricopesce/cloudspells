"""Highly secure, monitored OCI VCN — production-ready reference deployment.

## Architecture

This example deploys the complete CloudSpells secure-network stack with IAM
principals so every workload authenticates by identity, not by stored credentials:

```
┌─────────────────────────────────────────────────────────────────┐
│  VCN  10.0.0.0/18  (default)                                    │
│                                                                 │
│  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Public /21      │  │ Private /19                          │  │
│  │ (LB tier)       │  │ (App tier)  ← ComputeInstancePrinci- │  │
│  │ IGW route       │  │ NAT GW + Service GW routes     pal   │  │
│  │ lb-nsg ──────────┼──► app-nsg    reads Vault Secrets      │  │
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

Tenancy (root compartment)
 ├── DynamicGroup: {stack}-app-dg   ← app_instance_ocid exactly
 └── Group:        {stack}-ops-group

Compartment
 ├── Policy: {stack}-app-policy  → read secret-family, read object-family
 └── Policy: {stack}-ops-policy  → manage all-resources
```

## Security model

### Network layer — NSG roles

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

### IAM layer — zero-credential workloads

`ComputeInstancePrincipal` creates a dynamic group matching the configured app
instance OCID and a policy granting `read secret-family` and
`read object-family`.  App-tier instances authenticate as **instance
principals** — the OCI SDK picks up the credential automatically from the
instance metadata endpoint.  No API keys, no passwords in user-data or
environment variables.

A typical usage pattern in the app tier:

```python
import oci
signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
secrets_client = oci.secrets.SecretsClient({}, signer=signer)
bundle = secrets_client.get_secret_bundle(secret_id="ocid1.vaultsecret...").data
db_password = base64.b64decode(bundle.secret_bundle_content.content).decode()
```

`CompartmentAdminGroup` creates an empty IAM group and a policy granting
`manage all-resources` within the compartment.  Ops team members are added
post-deploy — no credentials are deployed or rotated by Pulumi.

### Zero Trust tagging

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
- `tenancy_ocid` — OCID of the tenancy root compartment (Tenancy Details →
  OCID in the OCI Console).  Required to create the dynamic group and ops
  group at the tenancy level.
- `app_instance_ocid` — OCID of the app-tier compute instance that should
  receive the instance-principal grants.

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
- `app_dynamic_group_id` — Dynamic group OCID for app-tier instance principal
- `app_policy_id` — Policy OCID granting Vault Secrets + Object Storage read
- `ops_group_id` — IAM group OCID for compartment administrators
- `ops_policy_id` — Policy OCID granting compartment admin rights
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.iam import CompartmentAdminGroup, ComputeInstancePrincipal, IamGrant
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE, MANAGEMENT

# ── Configuration ─────────────────────────────────────────────────────────────

config = Config()

compartment_id: str = config.require("compartment_ocid")
tenancy_id: str = config.require("tenancy_ocid")
app_instance_id: str = config.require("app_instance_ocid")
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

# ── Step 4 — IAM principals ───────────────────────────────────────────────────
#
# ComputeInstancePrincipal creates:
#
#   DynamicGroup matching rule:
#     instance.id = '<app_instance_ocid>'
#     → only the configured app-tier instance is a member.
#
#   Policy statements (scoped to this compartment):
#     Allow dynamic-group id <dynamic_group_ocid> to read object-family in compartment id <compartment_id>
#     Allow dynamic-group id <dynamic_group_ocid> to read secret-family in compartment id <compartment_id>
#
#   What instances can access:
#     - Object Storage: list buckets, read objects (GET/HEAD). Cannot write or delete.
#     - Vault Secrets: retrieve secret bundles (e.g. DB password). Cannot manage secrets.
#
#   How to use on the instance (no API keys needed):
#     import oci, base64
#     signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
#     client = oci.secrets.SecretsClient({}, signer=signer)
#     bundle = client.get_secret_bundle(secret_id="ocid1.vaultsecret...").data
#     db_password = base64.b64decode(bundle.secret_bundle_content.content).decode()
#
# CompartmentAdminGroup creates:
#
#   Group: empty at creation — add operators post-deploy:
#     oci iam group add-user \
#         --group-id $(pulumi stack output ops_group_id) \
#         --user-id <user_ocid>
#
#   Policy statement (scoped to this compartment):
#     Allow group {stack}-ops-group to manage all-resources in compartment id <compartment_id>
#
#   What group members can do:
#     - Full CRUD on all resources within this compartment only.
#     - Cannot touch tenancy-level resources (users, groups, other compartments).

app_principal: ComputeInstancePrincipal = ComputeInstancePrincipal(
    name="app",
    tenancy_id=tenancy_id,
    compartment_id=compartment_id,
    instance_ids=[app_instance_id],
    grants=[
        IamGrant.read_secrets(),  # fetch DB password from Vault — no credentials on the VM
        IamGrant.read_objects(),  # read app config from Object Storage
    ],
)

ops_group: CompartmentAdminGroup = CompartmentAdminGroup(
    name="ops",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
)

# ── Stack outputs ──────────────────────────────────────────────────────────────
#
# vcn.export() also publishes network_audit_log_group_id when flow_logs=True.
vcn.export()
app_principal.export()
ops_group.export()
