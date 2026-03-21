# Tutorial: Deploy an OKE Cluster

This tutorial deploys an Oracle Kubernetes Engine (OKE) cluster with a managed node pool using the `OkeCluster` spell.

**What you will build:**

```
kubectl (port 6443)
   │
   ▼
┌────────────────────────────────────────────────────┐
│ Public subnet  ← Internet Gateway                  │
│  OKE API endpoint [api_nsg]                        │
│  OCI Load Balancers [lb_nsg]                       │
└────────────────────────────────────────────────────┘
          │ kubelet (10250) / NodePort / kube-proxy
          ▼
┌────────────────────────────────────────────────────┐
│ Private subnet  ← NAT GW + Service GW              │
│  Worker VNICs [worker_nsg]                         │
│  Pod VNICs [pod_nsg]  (VCN-native CNI)             │
│  Nodes spread across all Availability Domains      │
└────────────────────────────────────────────────────┘
```

**What gets created:** 1 VCN (4 subnets + 3 gateways), 1 OKE BASIC_CLUSTER, 1 node pool spread across all ADs, 4 NSGs with 32 NSG rules, all required security list rules.

---

## Prerequisites

- Completed [Installation](../getting-started/installation.md)
- OCI compartment OCID at hand
- OKE-compatible node image OCID (OCI Console → Marketplace → Oracle Linux image for OKE)
- `kubectl` installed locally

---

## Step 1 — Initialise the stack

```bash
cd examples/oke

pulumi stack init dev
pulumi config set compartment_ocid ocid1.compartment.oc1..example
pulumi config set node_image_id    ocid1.image.oc1..example
```

Additional values with defaults — override only what you need:

```bash
pulumi config set kubernetes_version v1.32.1
pulumi config set node_shape        VM.Standard.A1.Flex   # ARM — cost-effective
pulumi config set node_count        3
pulumi config set oke_ocpus         2
pulumi config set oke_memory_in_gbs 12
```

---

## Step 2 — Walk through the code

Open `examples/oke/__main__.py`.

```python
import os
from cloudspells.core import Config
from cloudspells.providers.oci.kubernetes import NodePoolConfig, OkeCluster
from cloudspells.providers.oci.network import Vcn

config = Config()
compartment_id     = config.require("compartment_ocid")
kubernetes_version = config.require("kubernetes_version")

vcn = Vcn(name="lab", compartment_id=compartment_id)

oke = OkeCluster(
    name="okeinfra",
    compartment_id=compartment_id,
    vcn=vcn,
    kubernetes_version=kubernetes_version,
    display_name="infra",
    node_pools=[
        NodePoolConfig(
            name="default",
            shape=config.require("node_shape"),
            image=config.require("node_image_id"),
            node_count=config.require_int("node_count"),
            ocpus=config.require_float("oke_ocpus"),
            memory_in_gbs=config.require_float("oke_memory_in_gbs"),
        ),
    ],
)

vcn.export()
oke.export()

# Write kubeconfig to the example directory for isolated kubectl access
oke.create_kubeconfig(os.path.join(os.path.dirname(__file__), "kubeconfig"))
```

`OkeCluster` handles all the complexity:

- Accepts one or more `NodePoolConfig` descriptors — each produces an independent OCI node pool, enabling mixed shapes (e.g. system pool + GPU pool)
- Adds 19 security list rules covering the Kubernetes control plane (6443), kubelet (10250), NodePort range (30000-32767), and kube-proxy (10256)
- Creates 4 NSGs (`api_nsg`, `lb_nsg`, `worker_nsg`, `pod_nsg`) with 32 VNIC-level rules for fine-grained segmentation
- Places the API endpoint in the public subnet and worker/pod VNICs in the private subnet
- Configures `OCI_VCN_IP_NATIVE` CNI so every pod gets a real VCN subnet IP
- Spreads nodes across all Availability Domains automatically
- Calls `vcn.finalize_network()` to materialise subnets and security lists

### The NSG security model

Workers and pods share the private subnet CIDR. Four NSGs segment them at the VNIC level:

| NSG | Attached to | What it controls |
|---|---|---|
| `api_nsg` | Kubernetes API endpoint VNIC | Who may reach the API server |
| `lb_nsg` | OCI Load Balancer VNICs | Internet → LB, LB → workers |
| `worker_nsg` | Every worker node VNIC | kubelet, NodePort, node-to-node |
| `pod_nsg` | Every pod VNIC (OCI CNI) | Pod east-west, webhooks, egress |

### Attaching `lb_nsg` to a Kubernetes Load Balancer service

When you create a `Service` of type `LoadBalancer`, add the NSG via annotation so the OCI Cloud Controller Manager attaches it:

```yaml
apiVersion: v1
kind: Service
metadata:
  annotations:
    oci.oraclecloud.com/security-group-ids: "<okeinfra_lb_nsg_id>"
spec:
  type: LoadBalancer
```

Get the OCID with:

```bash
pulumi stack output okeinfra_lb_nsg_id
```

### Why workers and pods share the private subnet

With VCN-native CNI, each running pod gets a real VCN subnet IP. The private subnet (which has NAT) is used instead of the secure subnet (Service Gateway only) so pods can initiate outbound HTTPS connections — required for image pulls and workloads calling external APIs.

Security lists cannot distinguish pod IPs from worker IPs within the same CIDR. NSGs operate at the VNIC level and carry a separate ID per VNIC — this is why the four-NSG model exists. Use Kubernetes **NetworkPolicy** for pod-to-pod isolation within the cluster.

---

## Step 3 — Deploy

```bash
pulumi preview   # verify the plan
pulumi up
```

OKE cluster creation takes 8–15 minutes.

---

## Step 4 — Configure kubectl

The example writes a kubeconfig to `examples/oke/kubeconfig` automatically. Use it without touching the system kubeconfig:

```bash
KUBECONFIG=./kubeconfig kubectl get nodes
```

Or generate via the OCI CLI pointing at the stack output:

```bash
oci ce cluster create-kubeconfig \
    --cluster-id $(pulumi stack output okeinfra_cluster_id) \
    --file ~/.kube/config \
    --region <your-region> \
    --token-version 2.0.0

kubectl get nodes
```

Nodes should appear as `Ready` within a minute or two of the cluster becoming active.

---

## Step 5 — Inspect outputs

```bash
pulumi stack output
```

Key outputs (prefix `okeinfra_` matches the `name="okeinfra"` argument):

| Output | Description |
|---|---|
| `okeinfra_cluster_id` | OKE cluster OCID |
| `okeinfra_kubernetes_version` | Kubernetes version deployed |
| `okeinfra_lb_nsg_id` | `lb_nsg` OCID — use in `oci.oraclecloud.com/security-group-ids` annotation |
| `private_subnet_id` | Private subnet OCID (worker nodes and pods) |
| `public_subnet_id` | Public subnet OCID (API endpoint, load balancers) |

---

## Required configuration reference

| Parameter | Required | Suggested value | Notes |
|---|---|---|---|
| `compartment_ocid` | yes | — | OCI compartment OCID |
| `node_image_id` | yes | — | OKE-compatible Oracle Linux image OCID |
| `kubernetes_version` | yes | — | e.g. `v1.32.1` — check OCI console for supported versions |
| `node_shape` | yes | `VM.Standard.A1.Flex` | e.g. `VM.Standard.A1.Flex` (ARM) or `VM.Standard.E4.Flex` (x86) |
| `node_count` | yes | `3` | Worker node count (spread evenly across ADs by OCI) |
| `oke_ocpus` | yes | `2` | OCPUs per node |
| `oke_memory_in_gbs` | yes | `12` | RAM in GiB per node |

---

## CIDR sizing note

With VCN-native CNI, a 100-node cluster with 30 pods per node consumes ~3,100 IPs in the private subnet. The default `/18` VCN gives the private tier a `/19` (8 190 usable IPs), which is sufficient for moderate clusters. For larger deployments use a `/16` or `/17` VCN.

See [VCN Architecture → CIDR sizing guide](../reference/vcn-architecture.md#cidr-sizing-guide) for a full sizing table.

---

## Teardown

```bash
pulumi destroy
```

---

## What's next

- [OKE Architecture reference →](../reference/oke-architecture.md) — full NSG rule tables, traffic flows, port reference
- [Deploy a scalable workload →](autoscale.md) — load-balanced instance pool with CPU autoscaling
- [Use VcnRef to share this network →](../how-to/vcnref.md) — deploy OKE in a dedicated stack and reference the network from application stacks
