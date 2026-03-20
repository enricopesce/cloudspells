# OKE Example

Deploys an Oracle Kubernetes Engine (OKE) cluster with a managed node pool
using the full 4-tier VCN architecture.  Worker node VNICs and pod IPs are
placed in separate subnets, following Oracle's recommended topology for
VCN-native pod networking (`OCI_VCN_IP_NATIVE`).

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
| `vcn_cidr_block` | No | `10.0.0.0/18` | VCN CIDR — RFC 1918, prefix `/16`–`/20` |
| `kubernetes_version` | No | `v1.32.1` | Kubernetes version |
| `node_shape` | No | `VM.Standard.A1.Flex` | Shape for worker nodes |
| `oke_ocpus` | No | `2` | OCPUs per worker node |
| `oke_memory_in_gbs` | No | `12` | Memory in GB per worker node |
| `oke_min_nodes` | No | `2` | Number of worker nodes in the pool |
| `node_image_id` | No | _(latest Oracle Linux)_ | Custom image OCID for worker nodes |

## Deploy

```bash
cd examples/oke

pulumi stack init dev
pulumi config set compartment_ocid <your-compartment-ocid>

# Optional: larger VCN for big clusters (more pod IPs in secure subnet)
pulumi config set vcn_cidr_block 10.0.0.0/16

# Optional: tune the node pool
pulumi config set kubernetes_version v1.32.1
pulumi config set node_shape VM.Standard.E4.Flex
pulumi config set oke_ocpus 4
pulumi config set oke_memory_in_gbs 24
pulumi config set oke_min_nodes 3

pulumi preview
pulumi up
```

## Access the Cluster

After deployment, download the kubeconfig using the OCI CLI:

```bash
oci ce cluster create-kubeconfig \
  --cluster-id $(pulumi stack output cluster_id) \
  --file ~/.kube/config \
  --region <your-region> \
  --token-version 2.0.0

kubectl get nodes
```

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `cidr_block` | VCN CIDR block |
| `public_subnet_id` | OCID of the public subnet (API endpoint + LB) |
| `private_subnet_id` | OCID of the private subnet (worker nodes) |
| `secure_subnet_id` | OCID of the secure subnet (pod IPs) |
| `management_subnet_id` | OCID of the management subnet |
| `cluster_id` | OCID of the OKE cluster |

## Teardown

```bash
pulumi destroy
```
