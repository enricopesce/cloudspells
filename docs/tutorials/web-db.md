# Tutorial: Deploy a 3-Tier Web Application

This tutorial builds a production-style 3-tier stack: an internet-facing load balancer in the public subnet, two web backends in the private subnet, and two database nodes in the secure subnet — all wired with role-based NSG security.

**What you will build:**

```
Internet
   │  HTTP 80 / HTTPS 443 / SSH 22
   ▼
┌─────────────────────────────────────────────────────┐
│ Public subnet (/19)  — Internet Gateway route       │
│  load-balancer  [INTERNET_EDGE]                     │
└──────────────────────┬──────────────────────────────┘
                       │ TCP 8080 + SSH 22
                       ▼
┌─────────────────────────────────────────────────────┐
│ Private subnet (/17) — NAT GW + Service GW routes   │
│  web-backend-1  [APP_SERVER]                        │
│  web-backend-2  [APP_SERVER]                        │
└──────────────────────┬──────────────────────────────┘
                       │ TCP 5432 + SSH 22
                       ▼
┌─────────────────────────────────────────────────────┐
│ Secure subnet (/18)  — Service GW only (no NAT)     │
│  db-1  [DATABASE]  — 200 GB high-performance volume │
│  db-2  [DATABASE]  — 200 GB high-performance volume │
└─────────────────────────────────────────────────────┘
```

**What gets created:** 1 VCN (4 subnets + 3 gateways), 3 NSGs, 5 compute instances, 2 block volumes.

---

## Prerequisites

- Completed [Installation](../getting-started/installation.md)
- OCI compartment OCID at hand

---

## Step 1 — Initialise the stack

```bash
cd examples/web-db

pulumi stack init dev
pulumi config set compartment_ocid ocid1.compartment.oc1..aaaa...
```

Optionally override defaults:

```bash
pulumi config set app_port 8080     # port the web backends listen on (default: 8080)
pulumi config set db_port 5432      # database port (default: 5432)
pulumi config set ssh_key "$(cat ~/.ssh/id_rsa.pub)"
```

---

## Step 2 — Walk through the code

Open `examples/web-db/__main__.py`. It has four logical steps.

### 2a. Create the VCN

```python
from cloudspells.providers.oci.network import Vcn

vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    cidr_block=vcn_cidr,
)
```

One call creates the VCN, all three gateways, and four route tables. Security lists and subnets are deferred until the first spell calls `finalize_network()`.

### 2b. Declare roles with NSGs

```python
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE

lb_nsg  = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS, SSH], vcn=vcn, compartment_id=compartment_id)
web_nsg = Nsg("web-backend",   role=APP_SERVER,                               vcn=vcn, compartment_id=compartment_id)
db_nsg  = Nsg("database",      role=DATABASE,                                 vcn=vcn, compartment_id=compartment_id)
```

Each `role` constant encodes a security posture:

| Role | Subnet tier | Egress |
|------|-------------|--------|
| `INTERNET_EDGE` | Public | Internet GW; accepts declared ports from `0.0.0.0/0` |
| `APP_SERVER` | Private | NAT GW + Oracle Services |
| `DATABASE` | Secure | Oracle Services only — no internet path |

Ambient NSG rules (service egress) are generated automatically. You declare only application ports.

### 2c. Wire the traffic hops

```python
lb_nsg.serves(web_nsg, port=app_port)   # LB  → web: app port + SSH mgmt
web_nsg.serves(db_nsg, port=db_port)    # web → DB:  db port  + SSH mgmt
```

Each `serves()` call generates **four NSG rules** in one line:

- `lb-nsg` → EGRESS → `web-nsg` on `app_port`
- `web-nsg` ← INGRESS ← `lb-nsg` on `app_port`
- `lb-nsg` → EGRESS → `web-nsg` on 22 (SSH management channel)
- `web-nsg` ← INGRESS ← `lb-nsg` on 22

It also creates the matching cross-subnet Security List rules, so OCI's two enforcement layers stay in sync without any manual calls.

### 2d. Create the compute instances

```python
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.volume import VolumeSpec

load_balancer  = ComputeInstance("load-balancer",  compartment_id=compartment_id, vcn=vcn, ssh_public_key=ssh_key, nsg=lb_nsg)
web_backend_1  = ComputeInstance("web-backend-1",  compartment_id=compartment_id, vcn=vcn, ssh_public_key=ssh_key, nsg=web_nsg)
web_backend_2  = ComputeInstance("web-backend-2",  compartment_id=compartment_id, vcn=vcn, ssh_public_key=ssh_key, nsg=web_nsg)

db_1 = ComputeInstance(
    "db-1",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    nsg=db_nsg,
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)
db_2 = ComputeInstance(
    "db-2",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    nsg=db_nsg,
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)
```

Every instance inherits its subnet from its NSG role — no `subnet=` argument needed. Both `web_backend_1` and `web_backend_2` share `web_nsg`; the shared NSG covers both instances automatically with no extra rules.

The database nodes each get a 200 GB block volume at `PERF_HIGH` (higher IOPS/throughput, suitable for database workloads).

---

## Step 3 — Deploy

```bash
pulumi preview   # verify the plan
pulumi up
```

Deployment takes roughly 5–8 minutes.

---

## Step 4 — Inspect outputs

```bash
pulumi stack output
```

Key outputs:

| Output | Description |
|--------|-------------|
| `load_balancer_public_ip` | Public IP — entry point for HTTP/HTTPS traffic |
| `web_backend_1_private_ip` | Private IP of first web backend |
| `web_backend_2_private_ip` | Private IP of second web backend |
| `db_1_private_ip` | Private IP of first DB node |
| `db_2_private_ip` | Private IP of second DB node |

---

## Step 5 — Add a third web backend

Because all web instances share `web_nsg`, adding another backend requires no NSG changes at all:

```python
web_backend_3 = ComputeInstance(
    "web-backend-3",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    nsg=web_nsg,   # same NSG — zero rule changes
)
```

This is the key advantage of role-based NSGs over instance-level security rules: the security posture scales horizontally without configuration churn.

---

## Teardown

```bash
pulumi destroy
```

---

## What's next

- [Deploy a secure, monitored network →](secure-vcn.md) — add flow logs, a management tier, and Zero Trust Packet Routing labels
- [Configure NSG Rules →](../how-to/nsg-rules.md) — deep dive into role constants, `serves()`, and custom rules
- [Use a Bastion for private access →](../how-to/bastion.md) — SSH into the web or DB tier without a public IP
