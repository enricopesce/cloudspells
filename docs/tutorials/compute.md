# Tutorial: Deploy a Compute Instance

This tutorial deploys a public-facing web server on OCI — a VM in the public subnet, reachable on HTTP, HTTPS, and SSH from the internet — using the `ComputeInstance` and `Nsg` blocks.

**What you will build:**

```
Internet
   │  HTTP 80 / HTTPS 443 / SSH 22
   ▼
┌──────────────────────────────────────────┐
│ Public subnet  ← Internet Gateway        │
│  web-server  [INTERNET_EDGE role]        │
│  100 GB data volume + 200 GB logs volume │
└──────────────────────────────────────────┘
```

**What gets created:** 1 VCN (4 subnets + 3 gateways), 1 NSG, 1 compute instance, 2 block volumes, 1 SSH key pair.

---

## Prerequisites

- Completed [Installation](../getting-started/installation.md)
- OCI compartment OCID at hand

---

## Step 1 — Initialise the stack

```bash
cd examples/compute

pulumi stack init dev
pulumi config set compartment_ocid ocid1.compartment.oc1..aaaa...
```

Optionally, provide your own SSH public key (skip this to auto-generate one):

```bash
pulumi config set ssh_key "$(cat ~/.ssh/id_rsa.pub)"
```

---

## Step 2 — Walk through the code

Open `examples/compute/__main__.py`. It has three logical steps.

### 2a. Create the VCN

```python
from providers.oci.network import Vcn

vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)
```

A fully-wired 4-tier VCN. No further network configuration is needed.

### 2b. Attach a role with an NSG

```python
from providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from providers.oci.roles import INTERNET_EDGE

web_nsg = Nsg(
    "web-server",
    role=INTERNET_EDGE,
    ports=[HTTP, HTTPS, SSH],
    vcn=vcn,
    compartment_id=compartment_id,
)
```

`INTERNET_EDGE` is a semantic role constant. It tells CloudBlocks that this resource lives in the **public subnet** and communicates directly with the internet. CloudBlocks automatically adds ICMP path-MTU rules in both directions — you only declare the application ports.

### 2c. Create the compute instance

```python
from providers.oci.compute import ComputeInstance
from providers.oci.volume import VolumeSpec

web_server = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    nsg=web_nsg,
    volumes=[
        VolumeSpec(size_in_gbs=100, label="data"),
        VolumeSpec(size_in_gbs=200, label="logs", vpus_per_gb=VolumeSpec.PERF_LOW),
    ],
)
```

The instance inherits its subnet from the NSG role: because `web_nsg` uses `INTERNET_EDGE`, the instance is automatically placed in the public subnet. No subnet argument needed.

`ComputeInstance` calls `vcn.finalize_network()` automatically — security lists and subnets are materialised at this point.

---

## Step 3 — Deploy

```bash
pulumi preview   # verify the plan
pulumi up
```

Deployment takes roughly 3–5 minutes.

---

## Step 4 — Connect via SSH

If you provided your own key:

```bash
ssh opc@$(pulumi stack output web_server_public_ip)
```

If the key was auto-generated, retrieve the private key first:

```bash
pulumi stack output web_server_ssh_private_key --show-secrets > ~/.ssh/oci_web
chmod 600 ~/.ssh/oci_web
ssh -i ~/.ssh/oci_web opc@$(pulumi stack output web_server_public_ip)
```

---

## Step 5 — Inspect outputs

```bash
pulumi stack output
```

Key outputs:

| Output | Description |
|--------|-------------|
| `web_server_public_ip` | Public IP of the instance |
| `web_server_id` | Instance OCID |
| `web_server_ssh_private_key` | _(secret)_ Only present when auto-generated |

---

## Teardown

```bash
pulumi destroy
```

---

## What's next

- [Deploy an OKE cluster →](oke.md)
- [Use a Bastion for private access →](../how-to/bastion.md) — place the instance in the private subnet instead and access it via the OCI Bastion service
