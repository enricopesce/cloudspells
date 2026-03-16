# Tutorial: Deploy an OKE Cluster

This tutorial deploys an Oracle Kubernetes Engine (OKE) cluster with a managed node pool using the `OkeCluster` spell.

**What you will build:**

```
kubectl (port 6443)
   │
   ▼
┌────────────────────────────────────────────────────┐
│ Public subnet  ← Internet Gateway                  │
│  OKE API endpoint + OCI Load Balancers             │
└────────────────────────────────────────────────────┘
          │ kubelet / NodePort / kube-proxy
          ▼
┌────────────────────────────────────────────────────┐
│ Private subnet  ← NAT GW + Service GW              │
│  Worker node VNICs + Pod IPs (VCN-native CNI)      │
│  Nodes spread across all Availability Domains      │
└────────────────────────────────────────────────────┘
```

**What gets created:** 1 VCN (4 subnets + 3 gateways), 1 OKE BASIC_CLUSTER, 1 node pool spread across all ADs, all required security list rules.

---

## Prerequisites

- Completed [Installation](../getting-started/installation.md)
- OCI compartment OCID at hand
- `kubectl` installed locally

---

## Step 1 — Initialise the stack

```bash
cd examples/oke

pulumi stack init dev
pulumi config set compartment_ocid ocid1.compartment.oc1..aaaa...
```

All other values have sensible defaults (shown below). Override only what you need:

```bash
# Optional overrides
pulumi config set kubernetes_version v1.32.1
pulumi config set node_shape VM.Standard.A1.Flex   # ARM — cost-effective
pulumi config set oke_min_nodes 2
pulumi config set oke_ocpus 2
pulumi config set oke_memory_in_gbs 12
```

---

## Step 2 — Walk through the code

Open `examples/oke/__main__.py`.

```python
from providers.oci.network import Vcn
from providers.oci.kubernetes import OkeCluster

vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

oke = OkeCluster(
    name="okeinfra",
    compartment_id=compartment_id,
    vcn=vcn,
    kubernetes_version=kubernetes_version,
    shape=node_shape,
    memory_in_gbs=oke_memory_in_gbs,
    min_nodes=oke_min_nodes,
    ocpus=oke_ocpus,
)
```

`OkeCluster` handles all the complexity:

- Adds security list rules for the Kubernetes control plane (port 6443), kubelet (10250), NodePort range, kube-proxy, and ICMP
- Places the API endpoint in the public subnet and worker nodes in the private subnet
- Configures `OCI_VCN_IP_NATIVE` CNI so every pod gets a real VCN subnet IP
- Spreads nodes across all Availability Domains automatically
- Calls `vcn.finalize_network()` to materialise subnets and security lists

### Why workers and pods share the private subnet

With VCN-native CNI, each running pod gets a real VCN subnet IP. The private subnet (which has NAT) is used instead of the secure subnet (Service Gateway only) so pods can initiate outbound HTTPS connections — required for any workload calling an external API, image registry, or monitoring service.

Use Kubernetes **NetworkPolicy** for pod-to-pod isolation; OCI security lists cannot distinguish pod IPs from worker IPs within the same CIDR.

---

## Step 3 — Deploy

```bash
pulumi preview   # verify the plan
pulumi up
```

OKE cluster creation takes 8–15 minutes.

---

## Step 4 — Configure kubectl

```bash
oci ce cluster create-kubeconfig \
    --cluster-id $(pulumi stack output oke_cluster_id) \
    --file ~/.kube/config \
    --region $(pulumi stack output region) \
    --token-version 2.0.0

kubectl get nodes
```

Nodes should appear as `Ready` within a minute or two of the cluster becoming active.

---

## Step 5 — Inspect outputs

```bash
pulumi stack output
```

Key outputs:

| Output | Description |
|--------|-------------|
| `oke_cluster_id` | OKE cluster OCID |
| `oke_node_pool_id` | Node pool OCID |
| `private_subnet_id` | Private subnet (worker nodes and pods) |
| `public_subnet_id` | Public subnet (API endpoint, load balancers) |

---

## Default configuration reference

| Parameter | Default | Notes |
|-----------|---------|-------|
| `kubernetes_version` | `v1.32.1` | Check OCI console for latest supported version |
| `node_shape` | `VM.Standard.A1.Flex` | ARM; use `VM.Standard.E4.Flex` for x86 |
| `oke_min_nodes` | `2` | Minimum node count (spread across ADs) |
| `oke_ocpus` | `2` | OCPUs per node |
| `oke_memory_in_gbs` | `12` | Memory per node in GB |
| `vcn_cidr_block` | `10.0.0.0/16` | Larger CIDRs accommodate more pods |

---

## CIDR sizing note

With VCN-native CNI, a 100-node cluster with 30 pods per node consumes ~3 000 IPs in the private subnet. The default `/16` VCN gives the private tier a `/17` (32 766 usable IPs), which is sufficient for very large clusters. For smaller deployments a `/18` or `/20` VCN is fine.

---

## Teardown

```bash
pulumi destroy
```

---

## What's next

- [Deploy a scalable workload →](autoscale.md) — load-balanced instance pool with CPU autoscaling
- [Use VcnRef to share this network →](../how-to/vcnref.md) — deploy the OKE cluster in a dedicated stack and reference the network from application stacks
