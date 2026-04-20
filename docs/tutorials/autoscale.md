# Tutorial: Deploy a Scalable Workload

This tutorial deploys a horizontally-scalable web tier using the `ScalableWorkload` spell: an OCI Load Balancer in the public subnet, an instance pool in the private subnet, and CPU-based autoscaling.

**What you will build:**

```
Internet (HTTP port 80)
   │
   ▼
┌─────────────────────────────────────────────────────┐
│ Public subnet  ← Internet Gateway                   │
│  OCI Load Balancer                                   │
└─────────────────────────────────────────────────────┘
          │  health checks + traffic
          ▼
┌─────────────────────────────────────────────────────┐
│ Private subnet  ← NAT GW + Service GW               │
│  Instance pool (1–3 nginx VMs)                       │
│  Autoscales on CPU: out >80%, in <20%                │
└─────────────────────────────────────────────────────┘
```

**What gets created:** 1 VCN, 1 load balancer, 1 instance configuration, 1 instance pool, 1 autoscaling policy, security list rules for HTTP (80).

> **Note:** An HTTPS listener and port 443 rules are only created when `ssl_certificate_name` is set in `OciLoadBalancerConfig`.

---

## Prerequisites

- Completed [Installation](../getting-started/installation.md)
- OCI compartment OCID at hand
- Boot image OCID for the pool instances (OCI Console → Compute → Images, or use the OCI CLI)

---

## Step 1 — Initialise the stack

```bash
cd examples/autoscale

pulumi stack init dev
pulumi config set compartment_ocid ocid1.compartment.oc1..example
pulumi config set image_ocid        ocid1.image.oc1..example
```

Optionally provide an SSH key (skip to auto-generate):

```bash
pulumi config set ssh_key "$(cat ~/.ssh/id_rsa.pub)"
```

---

## Step 2 — Walk through the code

Open `examples/autoscale/__main__.py`.

### 2a. Prepare a cloud-init script

The example passes a plain cloud-init script to install nginx and create a health check endpoint:

```python
user_data_script = """#!/bin/bash
set -e
yum install -y --disablerepo='*' --enablerepo='ol8_appstream,ol8_baseos_latest' nginx
systemctl enable nginx && systemctl start nginx
firewall-cmd --permanent --add-service=http && firewall-cmd --reload
echo "OK" > /usr/share/nginx/html/health
"""
```

CloudSpells base64-encodes `user_data` internally before passing it to OCI — pass the plain string or bytes directly.

The load balancer health check polls `/health` on port 80. Instances that fail health checks are removed from the rotation.

### 2b. Create the VCN and workload

```python
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.autoscale import ScalableWorkload

vcn = Vcn(
    name="scalable",
    compartment_id=compartment_id,
)

scalable_pool = ScalableWorkload(
    name="web-pool",
    compartment_id=compartment_id,
    vcn=vcn,
    image_id=config.require("image_ocid"),
    ssh_public_key=config.get("ssh_key"),
    user_data=user_data_script,
    max_instances=3,
)
```

`image_id` is a required parameter — pass the OCID of a boot image for the pool instances. Obtain it from the OCI Console or CLI and store it in Pulumi config.

`ScalableWorkload` encapsulates the entire tier:

- Load balancer in the **public subnet**, listening on port 80
- Instance pool in the **private subnet**, bootstrapped with your `user_data`
- CPU autoscaling: scale out when CPU > 80%, scale in when CPU < 20%
- 300-second cooldown between scaling events
- Defaults to `VM.Standard.E4.Flex` with 1 OCPU / 16 GB RAM
- Minimum 1 instance; set `max_instances` to control the ceiling (defaults to 5 if not specified)

---

## Step 3 — Deploy

```bash
pulumi preview   # verify the plan
pulumi up
```

Deployment takes 5–10 minutes (instance pool provisioning is the slow step).

---

## Step 4 — Test the load balancer

```bash
LB_IP=$(pulumi stack output web_pool_lb_ip)
curl http://$LB_IP/
```

Each response shows the `hostname` of the instance that handled the request. Reload a few times to see requests distributed across pool members.

Check the health endpoint:

```bash
curl http://$LB_IP/health
# OK
```

---

## Step 5 — Inspect outputs

```bash
pulumi stack output
```

Key outputs:

| Output | Description |
|--------|-------------|
| `web_pool_lb_ip` | Public IP of the load balancer |
| `web_pool_lb_id` | Load balancer OCID |
| `web_pool_pool_id` | Instance pool OCID |
| `web_pool_ssh_private_key` | _(secret)_ Only present when auto-generated |

---

## Scaling policy reference

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU utilisation | > 80% | Add 1 instance |
| CPU utilisation | < 20% | Remove 1 instance |
| Cooldown | — | 300 seconds between events |
| Min instances | — | 1 |
| Max instances | — | Set via `max_instances` |

---

## SSH access to pool members

Pool instances are in the private subnet and have no public IP. Use the OCI Bastion service or a jump host in the public subnet.

If you need direct SSH access during development, add a bastion to the same stack:

```python
from cloudspells.providers.oci.bastion import Bastion

bastion = Bastion(
    name="mgmt",
    compartment_id=compartment_id,
    vcn=vcn,
)
```

Declare the `Bastion` **before** `ScalableWorkload` so its SSH rule is registered before `finalize_network()` runs. See the [Bastion how-to guide](../how-to/bastion.md) for session creation steps.

---

## Teardown

```bash
pulumi destroy
```

---

## What's next

- [Use VcnRef to share the network →](../how-to/vcnref.md) — move the VCN to its own stack and reference it from the workload stack
- [Add a Bastion →](../how-to/bastion.md) — SSH into private pool instances without a public IP
