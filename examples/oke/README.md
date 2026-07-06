# OKE Example

Deploys an Oracle Kubernetes Engine (OKE) cluster with a managed node pool
using the full 4-tier VCN architecture. Worker node VNICs and pod IPs both
use the private subnet with separate worker and pod NSGs for VCN-native pod
networking (`OCI_VCN_IP_NATIVE`).

## Network architecture

```
VCN  10.0.0.0/18  (default)
│
├── public    10.0.48.0/21  ← Internet Gateway
│   API endpoint (kubectl access) + OCI Load Balancers
│   Ingress: port 6443 from private (workers+pods) and internet,
│            HTTP/HTTPS from internet (LB)
│   Egress:  kubelet (10250), NodePort, kube-proxy, all (webhooks) to private
│
├── private   10.0.0.0/19   ← NAT Gateway + Service Gateway
│   Worker node VNICs + Pod IPs (OCI VCN-native CNI)
│   Both share this subnet so pods can reach external APIs via NAT.
│   Pod-to-pod security is enforced by Kubernetes NetworkPolicy.
│   Ingress: kubelet/NodePort/kube-proxy + all (webhooks) from public, ICMP
│   Egress:  OCI services, API server, HTTPS to internet (images + APIs)
│
├── secure    10.0.32.0/20  ← Service Gateway only (no internet path)
│   Databases, secrets managers, audit stores.
│   Not used by OKE — workloads here cannot initiate internet connections.
│
└── management  10.0.56.0/21  ← Service Gateway only
    Bastion hosts, monitoring agents, VPN/FastConnect endpoints.
    Not used by OKE directly.
```

### Why workers and pods share the private subnet

With `OCI_VCN_IP_NATIVE` CNI each running pod gets a real VCN subnet IP.
Placing pods in the private subnet (with NAT) rather than the secure subnet
(Service Gateway only) means pods can initiate outbound HTTPS connections —
which is required for any workload that calls an external service (payment
APIs, SMS gateways, monitoring agents, package registries, etc.).

The secure subnet is intentionally reserved for **stateful data stores**
(databases, vaults) whose threat model requires they never initiate internet
connections.  Application-tier workloads like pods need NAT.

Pod-to-pod security is not a subnet concern — OCI security lists cannot
distinguish pod IPs from worker IPs within the same CIDR, and intra-subnet
traffic bypasses security list rules entirely.  Use Kubernetes
**NetworkPolicy** for pod isolation.

## What gets created

- 1 VCN (`10.0.0.0/18` by default)
- Internet, NAT, and Service Gateways
- 4 route tables (one per tier)
- 4 security lists (populated with OKE rules via the builder pattern)
- 4 subnets (public / private / secure / management)
- 1 OKE `BASIC_CLUSTER` with VCN-native pod networking
- 1 Node pool spread across all availability domains

## Prerequisites

- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed
- OCI credentials configured (`~/.oci/config`)
- Python virtual environment set up from the repository root:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | — | OCI compartment OCID |
| `kubernetes_version` | Yes | — | OKE Kubernetes version |
| `node_shape` | Yes | — | Shape for worker nodes |
| `node_image_id` | Yes | — | Image OCID for worker nodes |
| `node_count` | Yes | — | Number of worker nodes in the default pool |
| `oke_ocpus` | Yes | — | OCPUs per worker node |
| `oke_memory_in_gbs` | Yes | — | Memory in GB per worker node |
| `kubectl_allowed_cidrs` | No | empty | Comma-separated CIDRs allowed to reach the public API endpoint |

## Deploy

```bash
cd examples/oke

pulumi stack init dev
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set kubernetes_version v1.32.1
pulumi config set node_shape VM.Standard.E4.Flex
pulumi config set node_image_id <your-node-image-ocid>
pulumi config set node_count 3
pulumi config set oke_ocpus 4
pulumi config set oke_memory_in_gbs 24

# Optional: limit public Kubernetes API access
pulumi config set kubectl_allowed_cidrs 203.0.113.0/24

pulumi preview
pulumi up
```

## Access the Cluster

After deployment, download the kubeconfig using the OCI CLI:

```bash
oci ce cluster create-kubeconfig \
  --cluster-id $(pulumi stack output okeinfra_cluster_id) \
  --file ~/.kube/config \
  --region <your-region> \
  --token-version 2.0.0

kubectl get nodes
```

The example also writes a local `kubeconfig` file in `examples/oke` after a
successful deployment.

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `cidr_block` | VCN CIDR block |
| `public_subnet_id` | OCID of the public subnet (API endpoint + LB) |
| `private_subnet_id` | OCID of the private subnet (worker nodes and pod IPs) |
| `secure_subnet_id` | OCID of the secure subnet (not used by OKE) |
| `management_subnet_id` | OCID of the management subnet |
| `okeinfra_cluster_id` | OCID of the OKE cluster |
| `okeinfra_cluster_endpoint` | Public Kubernetes API endpoint |
| `okeinfra_kubernetes_version` | Kubernetes version deployed |
| `okeinfra_lb_nsg_id` | NSG OCID for OCI-managed Kubernetes load balancers |
| `okeinfra_kubeconfig` | _(secret)_ Kubeconfig, exported after `pulumi up` |

## Enhanced cluster variant

This example uses `OkeCluster`, which provisions a `BASIC_CLUSTER`. For
production workloads that need OCI Workload Identity, managed cluster add-on
lifecycle, and OCI DevOps integration, swap in `OkeClusterEnhanced` — it takes
the **same constructor arguments**, so only the import and class name change:

```python
from cloudspells.providers.oci.kubernetes import NodePoolConfig, OkeClusterEnhanced

oke = OkeClusterEnhanced(
    name="okeinfra",
    compartment_id=compartment_id,
    vcn=vcn,
    kubernetes_version=kubernetes_version,
    kubectl_allowed_cidrs=[c for c in (config.get("kubectl_allowed_cidrs") or "").split(",") if c],
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
```

An ENHANCED cluster cannot be downgraded to BASIC in place, so choose the tier
before the first `pulumi up`.

## Teardown

```bash
pulumi destroy
```
