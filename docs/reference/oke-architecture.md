# OKE Architecture Reference

Complete technical reference for the `OkeCluster` spell. This page covers the cluster configuration, subnet placement, VCN-native CNI, the NSG security model, every security rule this spell writes, node pool configuration, and operational outputs.

---

## Overview

`OkeCluster` is a Pulumi `ComponentResource` that deploys a complete Oracle Kubernetes Engine cluster. It creates the Kubernetes control plane, one or more node pools spread across all availability domains, and the entire two-layer security configuration (subnet-level security lists + VNIC-level NSGs).

**Resources created per `OkeCluster`:**

| Resource type | Count | Notes |
|---|---|---|
| `oci.containerengine.Cluster` | 1 | `BASIC_CLUSTER` type |
| `oci.containerengine.NodePool` | `len(node_pools)` | Each configured pool is spread across all ADs |
| `oci.core.NetworkSecurityGroup` | 4 | api, lb, worker, pod |
| `oci.core.NetworkSecurityGroupSecurityRule` | `33 + len(kubectl_allowed_cidrs)` | See NSG rules section |

Security lists are not created by `OkeCluster` — OKE subnet rules are installed through the parent `Vcn` network profile and materialised when `finalize_network` is called.

When OKE uses a live `Vcn`, `OkeCluster` installs the OKE network profile before `finalize_network()`. When OKE uses `VcnRef`, it does not mutate the referenced VCN; it requires the source stack to have exported the exact OKE profile first. Enable that in the VCN stack with `vcn.enable_oke_profile(kubectl_allowed_cidrs=[...])`.

---

## Cluster configuration

| Parameter | Value | Notes |
|---|---|---|
| Cluster type | `BASIC_CLUSTER` | Enhanced cluster features not required for standard workloads |
| CNI type | `OCI_VCN_IP_NATIVE` | Every pod gets a real VCN subnet IP |
| Pod CIDR | `10.244.0.0/16` | Kubernetes virtual address space for pods (not routed in VCN). With VCN-native CNI, pod data-plane traffic uses real VCN subnet IPs; the Pod CIDR is a Kubernetes-internal virtual address space. |
| Services CIDR | `10.96.0.0/16` | Kubernetes virtual address space for `ClusterIP` services |
| API endpoint | Public subnet | Public IP enabled; external `kubectl` access is allowed only from `kubectl_allowed_cidrs` |
| API NSG | `api_nsg` | Only traffic matching `api_nsg` rules reaches the API server VNIC |

**Pod CIDR and Services CIDR** are Kubernetes-internal address spaces. With `OCI_VCN_IP_NATIVE`, pod data-plane traffic uses real VCN subnet IPs from the private subnet; the pod and services CIDRs are used only for `ClusterIP` routing inside `kube-proxy` / `iptables`.

---

## Subnet placement

```
                            Internet
                               │
                         port 6443 (kubectl from allowed CIDRs)
                         port 443 / 80 (LB)
                               │
        ┌──────────────────────▼──────────────────────┐
        │  Public subnet  (Internet GW)               │
        │  ┌────────────────────────────────────────┐ │
        │  │  OKE API endpoint  [api_nsg]           │ │
        │  │  OCI Load Balancers [lb_nsg]  ─ ─ ─ ─ ┼─┤ (operator-attached)
        │  └────────────────────────────────────────┘ │
        └──────────────────────┬──────────────────────┘
                               │
                  kubelet (10250)  NodePort (30000-32767)
                  kube-proxy (10256)  webhooks (all)
                               │
        ┌──────────────────────▼──────────────────────┐
        │  Private subnet  (NAT GW + Service GW)      │
        │  ┌────────────────┐  ┌─────────────────────┐│
        │  │ Worker VNICs   │  │ Pod VNICs (OCI CNI) ││
        │  │ [worker_nsg]   │  │ [pod_nsg]           ││
        │  └────────────────┘  └─────────────────────┘│
        └─────────────────────────────────────────────┘
                               │
                         NAT Gateway
                               │
                          Internet
                    (image pulls, external APIs)
```

Workers and pods share the private subnet CIDR. NSGs discriminate between them at the VNIC level so the control plane, load balancer, and pods each see only the resources they are permitted to reach — even though both kinds of VNICs are in the same `/17` or `/19` address block.

---

## VCN-native CNI (`OCI_VCN_IP_NATIVE`)

With `OCI_VCN_IP_NATIVE`, the OCI CNI plugin allocates one or more VCN subnet IPs directly to each pod VNIC rather than using a virtual overlay network.

**Consequences for capacity planning:**

- Every running pod consumes one IP from the private subnet.
- Every worker node consumes one IP from the private subnet.
- Total IPs required: `(max_nodes × max_pods_per_node) + max_nodes`.

**Consequences for security:**

- Pod VNICs and worker VNICs both have IPs from the same private subnet CIDR.
- Security lists cannot distinguish between them — rules written to the subnet CIDR apply to both workers and pods.
- NSGs operate at the VNIC level and carry a separate ID per VNIC. This is why `OkeCluster` creates four NSGs: `api_nsg`, `lb_nsg`, `worker_nsg`, and `pod_nsg`. The OCI data plane enforces NSG rules before delivering a packet to a VNIC, regardless of whether the source and destination share a subnet CIDR.

**Consequence for `kubectl exec` / `kubectl port-forward`:**

These commands create a direct TCP stream from the API server to the kubelet (port 10250) on the target worker node. The kubelet then connects to the container. This flow is permitted by the `api_nsg → worker_nsg` rule on port 10250.

**Consequence for admission controller webhooks:**

Admission webhooks require the API server to reach the webhook pod on an arbitrary TCP port. This is covered by the `api_nsg → pod_nsg` ALL protocol egress rule and the matching ingress rule on `pod_nsg`.

---

## Node pool

Nodes are placed in the private subnet. The pool is spread across every availability domain in the region using OCI `placement_configs`:

```python
placement_configs = [
    NodePoolNodeConfigDetailsPlacementConfigArgs(
        availability_domain=ad.name,
        subnet_id=vcn.private_subnet.id,
    )
    for ad in availability_domains
]
```

The total node count (`size`) is divided as evenly as possible across ADs by the OCI control plane. If one AD has a capacity constraint, OCI places additional nodes in the remaining ADs.

`NodePoolConfig.name` is a semantic pool label. CloudSpells keeps it in tags (`PoolLabel`) and examples, while the Pulumi resource names use CloudSpells-owned ordinal suffixes such as `pool-1`.

### Node configuration

| Parameter | Source | Notes |
|---|---|---|
| `node_shape` | caller-supplied | Any OCI Flex shape (e.g. `VM.Standard.A1.Flex`, `VM.Standard.E4.Flex`) |
| `ocpus` | caller-supplied | OCPUs per node |
| `memory_in_gbs` | caller-supplied | RAM in GiB per node |
| `image_id` | caller-supplied | Boot image OCID — use OKE-managed images for pre-installed `kubelet` and `containerd` |
| `ssh_public_key` | optional | Installed on all nodes; enables direct SSH for debugging |
| `nsg_ids` | automatic | `[worker_nsg.id]` — applied to the node's primary VNIC |
| Pod VNIC NSG | automatic | `[pod_nsg.id]` — applied to each pod VNIC created by the CNI plugin |
| Pod subnet | automatic | `vcn.private_subnet.id` — same subnet as the node VNIC |

---

## Two-layer security model

`OkeCluster` enforces security at two complementary OCI layers.

### Layer 1 — Security lists (subnet boundary)

Security lists enforce coarse-grained, subnet-to-subnet routing policy. They are evaluated on every packet entering or leaving a subnet. `OkeCluster` installs the OKE network profile with a complete set of public and private subnet rules before calling `vcn.finalize_network()`.

In addition to the OKE-specific rules documented below, `finalize_network` always injects a set of **VCN baseline rules** before materialising the security lists. These include NAT Gateway egress for the private tier and Service Gateway egress for the private/secure/management tiers. See [Baseline security rules](vcn-architecture.md#baseline-security-rules) in the VCN Architecture reference for the full list.

Because the security list is shared (one list per subnet, accumulated from all spells), the rules written here establish the minimum necessary subnet-level connectivity. Within-subnet traffic (pod-to-pod, node-to-node) that stays inside the same CIDR block is **not** governed by security lists — it is governed exclusively by NSGs.

### Layer 2 — NSGs (VNIC boundary)

NSGs enforce fine-grained, component-to-component rules. Each NSG is attached to a specific set of VNICs. Rules reference other NSGs as source or destination (not CIDRs), so they remain correct even when IP addresses change.

The four OKE NSGs:

| NSG | Attached to | Purpose |
|---|---|---|
| `api_nsg` | Kubernetes API endpoint VNIC | Controls who may reach the API server |
| `lb_nsg` | OCI Load Balancer VNICs (operator-attached) | Controls internet-to-LB and LB-to-worker paths |
| `worker_nsg` | Every worker node primary VNIC | Controls node-level access (kubelet, NodePort, egress) |
| `pod_nsg` | Every pod VNIC (OCI CNI) | Controls pod-level access (east-west, webhooks, egress) |

**How to attach `lb_nsg` to an OCI Load Balancer:**

When a Kubernetes `Service` of type `LoadBalancer` is created, the OCI Cloud Controller Manager provisions an OCI Load Balancer. Add the `lb_nsg` OCID to the service annotation so the CCM attaches the NSG to the LB:

```yaml
apiVersion: v1
kind: Service
metadata:
  annotations:
    oci.oraclecloud.com/security-group-ids: "<lb_nsg_id>"
spec:
  type: LoadBalancer
```

The OCID is available via `cluster.lb_nsg.id` (in Pulumi) or `pulumi stack output <name>_lb_nsg_id` (from CLI after `oke.export()`).

---

## Security list rules

The following rules are added to the shared VCN security lists by the OKE network profile.

### Public subnet — Ingress

| Protocol | Source | Port / Type | Description |
|---|---|---|---|
| TCP | Private subnet CIDR | 6443 | Workers and pods reach the Kubernetes API server |
| TCP | Private subnet CIDR | 12250 | Workers and pods reach the control-plane internal port |
| TCP | each `kubectl_allowed_cidrs` entry | 6443 | External `kubectl` and CI tooling reach the API |
| TCP | `0.0.0.0/0` | 443 | Load balancer receives HTTPS from the internet |
| TCP | `0.0.0.0/0` | 80 | Load balancer receives HTTP from the internet |

### Public subnet — Egress

| Protocol | Destination | Port / Type | Description |
|---|---|---|---|
| TCP | `<services CIDR>` (SERVICE_CIDR_BLOCK) | all | Control plane telemetry and management to OCI services |
| TCP | Private subnet CIDR | 10250 | Control plane calls kubelet for pod lifecycle operations |
| TCP | Private subnet CIDR | 30000–32767 | Load balancer forwards to worker nodes via NodePort |
| TCP | Private subnet CIDR | 10256 | Load balancer health-checks via kube-proxy |
| ALL | Private subnet CIDR | all | Control plane reaches pods on arbitrary ports (webhooks, admission controllers, metrics) |

### Private subnet — Ingress

| Protocol | Source | Port / Type | Description |
|---|---|---|---|
| TCP | Public subnet CIDR | 10250 | Control plane manages pods via kubelet |
| TCP | Public subnet CIDR | 30000–32767 | Load balancer forwards traffic via NodePort |
| TCP | Public subnet CIDR | 10256 | Load balancer health-checks via kube-proxy |
| ALL | Public subnet CIDR | all | Control plane reaches pods for webhooks and admission controllers |

### Private subnet — Egress

| Protocol | Destination | Port / Type | Description |
|---|---|---|---|
| TCP | `<services CIDR>` (SERVICE_CIDR_BLOCK) | all | Workers pull images from OCIR; pods reach monitoring and logging |
| TCP | Public subnet CIDR | 6443 | Workers and pods reach the Kubernetes API server |
| TCP | Public subnet CIDR | 12250 | Workers and pods reach the control-plane internal port |
| TCP | `0.0.0.0/0` | 443 | Workers pull container images; pods call external APIs via HTTPS |
| TCP | `0.0.0.0/0` | 80 | Workers pull images from HTTP registries; OCI pre-authenticated URLs |

**Total security list rules added:** `4 + len(kubectl_allowed_cidrs)` public ingress + 5 public egress + 4 private ingress + 5 private egress = `18 + len(kubectl_allowed_cidrs)` rules.

---

## NSG rules

NSG rules use NSG OCIDs as source/destination (not CIDRs), providing VNIC-level precision even when workers and pods share a subnet.

### `api_nsg` rules

#### Ingress

| Protocol | Source (NSG) | Port / Type | Description |
|---|---|---|---|
| TCP | `worker_nsg` | 6443 | Worker nodes reach the Kubernetes API server |
| TCP | `worker_nsg` | 12250 | Worker nodes reach the control-plane internal port |
| TCP | `pod_nsg` | 6443 | Pods reach the Kubernetes API server |
| TCP | `pod_nsg` | 12250 | Pods reach the control-plane internal port |
| TCP | each `kubectl_allowed_cidrs` entry (CIDR) | 6443 | External `kubectl` and CI tooling |

#### Egress

| Protocol | Destination | Port / Type | Description |
|---|---|---|---|
| ALL | `<services CIDR>` (SERVICE_CIDR_BLOCK) | all | Control plane telemetry and management |
| TCP | `worker_nsg` | 10250 | Control plane calls kubelet on worker nodes |
| ALL | `pod_nsg` | all | Control plane reaches pods on arbitrary ports (webhooks, exec, metrics) |

### `lb_nsg` rules

#### Ingress

| Protocol | Source | Port / Type | Description |
|---|---|---|---|
| TCP | `0.0.0.0/0` (CIDR) | 443 | Internet reaches the load balancer on HTTPS |
| TCP | `0.0.0.0/0` (CIDR) | 80 | Internet reaches the load balancer on HTTP |

#### Egress

| Protocol | Destination (NSG) | Port / Type | Description |
|---|---|---|---|
| TCP | `worker_nsg` | 30000–32767 | Load balancer forwards requests via NodePort |
| TCP | `worker_nsg` | 10256 | Load balancer queries kube-proxy health before routing |

### `worker_nsg` rules

#### Ingress

| Protocol | Source (NSG / CIDR) | Port / Type | Description |
|---|---|---|---|
| TCP | `api_nsg` | 10250 | Control plane calls kubelet for pod lifecycle, logs, exec |
| TCP | `lb_nsg` | 30000–32767 | Load balancer forwards requests via NodePort |
| TCP | `lb_nsg` | 10256 | Load balancer health-checks via kube-proxy |
| ALL | `pod_nsg` | all | Pods communicate with worker VNIC (OCI CNI VNIC-native) |
| ALL | `worker_nsg` | all | Node-to-node traffic for OCI CNI pod traffic across ADs |

#### Egress

| Protocol | Destination (NSG / CIDR) | Port / Type | Description |
|---|---|---|---|
| TCP | `api_nsg` | 6443 | Workers register with and query the API server |
| TCP | `api_nsg` | 12250 | Workers communicate with the control-plane internal port |
| ALL | `<services CIDR>` (SERVICE_CIDR_BLOCK) | all | Workers pull images from OCIR; send metrics and logs |
| ALL | `pod_nsg` | all | Workers reach pod VNICs (OCI CNI VNIC-native) |
| ALL | `worker_nsg` | all | Node-to-node traffic for OCI CNI across ADs |
| TCP | `0.0.0.0/0` (CIDR) | 443 | Workers pull container images via HTTPS; pods call external APIs |
| TCP | `0.0.0.0/0` (CIDR) | 80 | Workers pull images from HTTP registries; OCI pre-authenticated URLs |

### `pod_nsg` rules

#### Ingress

| Protocol | Source (NSG) | Port / Type | Description |
|---|---|---|---|
| ALL | `api_nsg` | all | Control plane reaches pods on arbitrary ports (webhooks, exec, metrics scraping) |
| ALL | `worker_nsg` | all | Worker nodes reach pod VNICs (OCI CNI VNIC-native) |
| ALL | `pod_nsg` | all | Pod-to-pod east-west traffic |

#### Egress

| Protocol | Destination (NSG / CIDR) | Port / Type | Description |
|---|---|---|---|
| ALL | `pod_nsg` | all | Pod-to-pod east-west traffic |
| ALL | `worker_nsg` | all | Pods reach worker VNICs (OCI CNI VNIC-native) |
| TCP | `api_nsg` | 6443 | Pods reach the Kubernetes API server |
| TCP | `api_nsg` | 12250 | Pods reach the control-plane internal port |
| ALL | `<services CIDR>` (SERVICE_CIDR_BLOCK) | all | Pods reach OCI services (object storage, monitoring, logging) |
| TCP | `0.0.0.0/0` (CIDR) | 443 | Pods call external APIs and download dependencies via HTTPS |
| TCP | `0.0.0.0/0` (CIDR) | 80 | Pods access HTTP endpoints and OCI pre-authenticated URLs |

**Total NSG rules created:** `4 + len(kubectl_allowed_cidrs)` api_nsg ingress + 3 api_nsg egress + 2 lb_nsg ingress + 2 lb_nsg egress + 5 worker_nsg ingress + 7 worker_nsg egress + 3 pod_nsg ingress + 7 pod_nsg egress = `33 + len(kubectl_allowed_cidrs)` rules (the `_r` helper creates one `NetworkSecurityGroupSecurityRule` resource per rule).

---

## Traffic flows — annotated

### `kubectl apply` from a developer laptop

```
laptop:ephemeral → API endpoint public IP:6443
  → Internet GW → public subnet
  → api_nsg INGRESS: configured CIDR TCP 6443  ✓ (NSG rule)
  → public security list INGRESS: configured CIDR TCP 6443  ✓ (security list rule)
```

### API server calling kubelet for `kubectl exec`

```
API endpoint:ephemeral → worker node VNIC:10250
  → api_nsg EGRESS: worker_nsg TCP 10250  ✓
  → worker_nsg INGRESS: api_nsg TCP 10250  ✓
  (same private subnet — security list not evaluated for intra-subnet traffic)
```

### OCI Load Balancer health-check

```
lb_nsg VNIC:ephemeral → worker node VNIC:10256
  → lb_nsg EGRESS: worker_nsg TCP 10256  ✓
  → worker_nsg INGRESS: lb_nsg TCP 10256  ✓
```

### OCI Load Balancer forwarding to a NodePort service

```
lb_nsg VNIC:ephemeral → worker node VNIC:30000-32767
  → lb_nsg EGRESS: worker_nsg TCP 30000-32767  ✓
  → worker_nsg INGRESS: lb_nsg TCP 30000-32767  ✓
```

### Pod calling the Kubernetes API server

```
pod VNIC:ephemeral → API endpoint:6443
  → pod_nsg EGRESS: api_nsg TCP 6443  ✓
  → api_nsg INGRESS: pod_nsg TCP 6443  ✓
  (cross-subnet: private → public)
  → private security list EGRESS: public subnet CIDR TCP 6443  ✓
  → public security list INGRESS: private subnet CIDR TCP 6443  ✓
```

### Pod calling an external HTTPS API

```
pod VNIC:ephemeral → 0.0.0.0/0:443
  → pod_nsg EGRESS: 0.0.0.0/0 TCP 443  ✓
  → private security list EGRESS: 0.0.0.0/0 TCP 443  ✓
  → NAT Gateway → internet
```

### Admission controller webhook (API server → pod)

```
API endpoint:ephemeral → pod VNIC:webhook_port (arbitrary)
  → api_nsg EGRESS: pod_nsg ALL  ✓
  → pod_nsg INGRESS: api_nsg ALL  ✓
  (cross-subnet: public → private)
  → public security list EGRESS: private subnet CIDR ALL  ✓
  → private security list INGRESS: public subnet CIDR ALL  ✓
```

---

## Port reference

| Port | Protocol | Component | Direction | Description |
|---|---|---|---|---|
| 6443 | TCP | API server | inbound | Kubernetes API (kubectl, workers, pods) |
| 12250 | TCP | API server | inbound | OKE control-plane internal port |
| 10250 | TCP | kubelet | inbound | API server → kubelet (exec, logs, lifecycle) |
| 10256 | TCP | kube-proxy | inbound | LB health-check endpoint |
| 30000–32767 | TCP | kube-proxy / host | inbound | NodePort service range |
| 443 | TCP | internet | outbound | Image pulls (OCIR, Docker Hub); external API calls |
| 80 | TCP | internet | outbound | HTTP image registries; OCI pre-authenticated URLs |

---

## Operational outputs

### `OkeCluster.export()`

Publishes three Pulumi stack outputs using the spell's logical `name` as a prefix (hyphens converted to underscores):

| Output key | Value | Example (name="okeinfra") |
|---|---|---|
| `{name}_cluster_id` | OKE cluster OCID | `okeinfra_cluster_id` |
| `{name}_kubernetes_version` | Kubernetes version string | `okeinfra_kubernetes_version` |
| `{name}_lb_nsg_id` | `lb_nsg` OCID | `okeinfra_lb_nsg_id` |

`lb_nsg_id` is the value to put in the `oci.oraclecloud.com/security-group-ids` service annotation.

### `OkeCluster.create_kubeconfig(filename)`

Writes a kubeconfig file to the specified path. Uses `oci.containerengine.get_cluster_kube_config` to fetch the cluster's KUBECONFIG content from the OCI API.

```python
cluster.create_kubeconfig("/tmp/kubeconfig")
# or
cluster.create_kubeconfig(os.path.expanduser("~/.kube/config"))
```

Alternatively, use the OCI CLI after deployment:

```bash
oci ce cluster create-kubeconfig \
    --cluster-id $(pulumi stack output okeinfra_cluster_id) \
    --file ~/.kube/config \
    --region <region> \
    --token-version 2.0.0
```

---

## Initialisation order

Understanding the sequence is important when composing multiple spells:

```
Vcn.__init__()
  └─ creates VCN, gateways, route tables (NOT security lists or subnets)

OkeCluster.__init__()
  ├─ vcn.enable_oke_profile(kubectl_allowed_cidrs=[...])
  │    └─ installs OKE security-list rules and exports the profile ID
  │
  ├─ vcn.finalize_network()
  │    ├─ _inject_baseline_rules()   ← NAT/Service GW egress
  │    ├─ _create_security_lists()   ← materialises all accumulated rules
  │    └─ _create_subnets()          ← creates 4 subnets
  │
  ├─ _create_oke_nsgs()
  │    ├─ creates api_nsg, lb_nsg, worker_nsg, pod_nsg
  │    └─ wires all NSG-to-NSG rules
  │
  ├─ oci.containerengine.Cluster(...)
  └─ oci.containerengine.NodePool(...)
```

`finalize_network` is idempotent — only the first call creates resources. If `OkeCluster` is combined with `ComputeInstance` or `ScalableWorkload`, rule-owning dependencies such as role-bearing NSGs must be constructed before the first call to `finalize_network` completes, and subsequent calls from other spells are no-ops.

---

## Minimum viable example

```python
from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.kubernetes import NodePoolConfig, OkeCluster

config = Config()
compartment_id = config.require("compartment_ocid")

vcn = Vcn(name="lab", compartment_id=compartment_id)

cluster = OkeCluster(
    name="k8s",
    compartment_id=compartment_id,
    vcn=vcn,
    kubernetes_version="v1.32.1",
    node_pools=[
        NodePoolConfig(
            name="default",
            shape="VM.Standard.A1.Flex",
            image=config.require("node_image_id"),
            node_count=3,
            ocpus=2,
            memory_in_gbs=12,
        ),
    ],
)

cluster.export()
```

This creates the complete stack: 1 VCN, 4 subnets, 3 gateways, 4 route tables, 4 security lists (with `18 + len(kubectl_allowed_cidrs)` OKE rules), 4 NSGs (with `33 + len(kubectl_allowed_cidrs)` rules), 1 OKE cluster, and one node pool per `NodePoolConfig`.

---

## What `OkeCluster` does not manage

| Concern | Where to handle it |
|---|---|
| Kubernetes NetworkPolicy | Apply with `kubectl` or a GitOps tool |
| Pod Security Admission | Configure via `kube-apiserver` admission plugin |
| OCI Load Balancer SSL termination | Configure in the Kubernetes Service annotation |
| OCI Load Balancer shape | Configure in the Kubernetes Service annotation (`oci.oraclecloud.com/loadbalancer-shape`) |
| Cluster autoscaler | Deploy as a Kubernetes workload with OCI autoscaler config |
| Node pool autoscaling | Configure after cluster creation via OCI Console / CLI |
| OKE add-ons (CoreDNS, kube-proxy, CNI) | Managed by OCI; version follows the Kubernetes version |
| RBAC | Manage with `kubectl` or a GitOps tool |
