# Tutorial: Secure, Monitored Network

This tutorial deploys a production-ready OCI network with all four security tiers, VCN Flow Logs for audit, a dedicated management tier, and Zero Trust Packet Routing (ZPR) labels — no compute instances required.

**What you will build:**

```
┌─────────────────────────────────────────────────────────────────┐
│  VCN  10.0.0.0/16                                               │
│                                                                 │
│  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Public /19      │  │ Private /17                          │  │
│  │ (LB tier)       │  │ (App tier)                           │  │
│  │ IGW route       │  │ NAT GW + Service GW routes           │  │
│  │ lb-nsg ──────────┼──► app-nsg                             │  │
│  └─────────────────┘  └──────────────────┬───────────────────┘  │
│                                          │ TCP 1521             │
│  ┌────────────────────────────────────────▼───────────────────┐  │
│  │ Secure /18 (DB tier)                                       │  │
│  │ Service GW only — NO internet path                         │  │
│  │ db-nsg                                                     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Management /19 — Service GW only                           │  │
│  │ mgmt-nsg — SSH access to all other tiers                   │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
             ↕ all traffic captured by VCN Flow Logs
```

**What gets created:** 1 VCN (4 subnets + 3 gateways), 4 NSGs, 1 Log Group + 4 Flow Log objects.

---

## Prerequisites

- Completed [Installation](../getting-started/installation.md)
- OCI compartment OCID at hand

---

## Step 1 — Initialise the stack

```bash
cd examples/secure-vcn

pulumi stack init dev
pulumi config set compartment_ocid ocid1.compartment.oc1..aaaa...
```

Optionally override defaults:

```bash
pulumi config set management_ingress_cidr 10.1.0.0/24   # restrict SSH source — do this before go-live
pulumi config set app_port 8080                          # app-tier TCP port (default: 8080)
pulumi config set db_port  1521                          # database TCP port (default: 1521)
pulumi config set log_retention_days 90                  # flow log retention: 30/60/90/120/150/180
```

> **Security note:** `management_ingress_cidr` defaults to `0.0.0.0/0`. Always restrict this to your actual operations CIDR before deploying to production.

---

## Step 2 — Walk through the code

Open `examples/secure-vcn/__main__.py`. It has three logical steps.

### 2a. Create the VCN with flow logs enabled

```python
from cloudspells.providers.oci.network import Vcn

vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr,
    flow_logs=True,
    flow_logs_retention=log_retention_days,
)
```

Setting `flow_logs=True` attaches a `VcnFlowLogs` spell automatically. It creates a Log Group and one Flow Log object per subnet, capturing all accepted and rejected traffic for network audit and forensics. The `flow_logs_retention` parameter accepts 30, 60, 90, 120, 150, or 180 days.

When `flow_logs=True`, `vcn.export()` also publishes `network_audit_log_group_id` so downstream stacks or monitoring tools can subscribe to the log group.

### 2b. Declare all four security roles

```python
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE, MANAGEMENT

lb_nsg   = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS], vcn=vcn, compartment_id=compartment_id)
app_nsg  = Nsg("app-server",    role=APP_SERVER,                          vcn=vcn, compartment_id=compartment_id)
db_nsg   = Nsg("database",      role=DATABASE,                            vcn=vcn, compartment_id=compartment_id)
mgmt_nsg = Nsg("management",    role=MANAGEMENT,                          vcn=vcn, compartment_id=compartment_id)
```

All four CloudSpells role constants are represented here:

| Role | Subnet | Egress | Ambient rules |
|------|--------|--------|---------------|
| `INTERNET_EDGE` | Public | Internet GW | Accepts declared ports from `0.0.0.0/0` |
| `APP_SERVER` | Private | NAT GW + Oracle Services | none |
| `DATABASE` | Secure | Oracle Services only | No internet egress |
| `MANAGEMENT` | Management | Oracle Services only | No internet egress |

Every NSG is also tagged with `ZprLabel=tier:<name>` for Zero Trust Packet Routing (see [below](#zero-trust-packet-routing)).

### 2c. Wire traffic relationships

```python
# Restrict SSH ingress on the management tier to a specific CIDR.
mgmt_nsg.allow_from_cidr("ssh-in", SSH, management_ingress_cidr, description="SSH from ops network")

# Application traffic hops (app port + SSH management channel each).
lb_nsg.serves(app_nsg, port=app_port)    # LB  → app: app_port + SSH 22
app_nsg.serves(db_nsg, port=db_port)     # app → DB:  db_port  + SSH 22

# Management tier reaches each tier directly over SSH only.
# with_ssh=False because SSH IS the declared port — no extra channel added.
mgmt_nsg.serves(lb_nsg,  port=SSH, with_ssh=False)   # mgmt → LB
mgmt_nsg.serves(app_nsg, port=SSH, with_ssh=False)   # mgmt → app
mgmt_nsg.serves(db_nsg,  port=SSH, with_ssh=False)   # mgmt → DB
```

`allow_from_cidr()` adds a single ingress rule for a specific source CIDR — useful when the source is an external network rather than another NSG in the VCN.

The `with_ssh=False` flag on the management `serves()` calls suppresses the automatic SSH management channel that `serves()` normally adds alongside the application port. Since the declared `port` here is already `SSH`, adding a second SSH channel would create duplicate rules.

---

## Step 3 — Deploy

```bash
pulumi preview   # verify the plan
pulumi up
```

Deployment takes roughly 3–5 minutes.

---

## Step 4 — Inspect outputs

```bash
pulumi stack output
```

Key outputs:

| Output | Description |
|--------|-------------|
| `vcn_id` | VCN OCID |
| `public_subnet_id` | Public (LB) subnet OCID |
| `private_subnet_id` | Private (App) subnet OCID |
| `secure_subnet_id` | Secure (DB) subnet OCID |
| `management_subnet_id` | Management subnet OCID |
| `network_audit_log_group_id` | Log Group OCID — subscribe your SIEM here |

---

## Zero Trust Packet Routing

Every NSG created by CloudSpells is tagged with `ZprLabel=tier:<name>`. If you enable **Zero Trust Packet Routing (ZPR)** in your OCI tenancy, you can write ZPR policies that enforce traffic rules at the OCI control plane — independently of, and in addition to, NSG rules:

```
Define policy "network-zpr-policy" as
  allow private-nsg to connect to secure-nsg on TCP port 1521
  where target.security-attribute.ZprLabel = 'tier:secure'
```

ZPR policies guarantee that no misconfigured VNIC attachment can bypass the NSG rules, providing a second, identity-based enforcement layer.

---

## Using subnet IDs in downstream stacks

The subnet OCIDs are normal Pulumi stack outputs. A downstream service stack can consume them via `VcnRef`:

```python
from cloudspells.providers.oci.network import VcnRef

vcn = VcnRef.from_stack_reference(
    stack_ref=pulumi.StackReference("org/secure-network/dev"),
    name="lab",
    compartment_id=compartment_id,
)
```

See [Share a VCN Across Stacks](../how-to/vcnref.md) for the full pattern.

---

## Teardown

```bash
pulumi destroy
```

---

## What's next

- [Deploy a 3-Tier Web Application →](web-db.md) — add compute instances across the tiers
- [Share a VCN Across Stacks →](../how-to/vcnref.md) — let service stacks consume this network
- [Configure NSG Rules →](../how-to/nsg-rules.md) — deep dive into role constants and custom rules
