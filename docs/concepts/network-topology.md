# Network Topology

Every CloudSpells deployment is built on a fixed 4-tier VCN architecture. This page explains the topology, the CIDR sizing rationale, the routing policy per tier, and the security posture — and why none of it is configurable.

---

## The 4-tier architecture

```
VCN  10.0.0.0/16  (example — prefix configurable, structure fixed)
│
├── private     10.0.0.0/17    50%   ← NAT GW + Service GW
│   App servers · K8s nodes and pods · instance pools
│
├── secure      10.0.128.0/18  25%   ← Service GW only
│   Databases · secrets managers · audit stores
│
├── public      10.0.192.0/19  12.5% ← Internet GW
│   Load balancers · internet-facing hosts
│
└── management  10.0.224.0/19  12.5% ← Service GW only
    Monitoring agents · Bastion service · VPN/FastConnect endpoints
```

The four tiers are created by binary subdivision of the VCN CIDR. You supply the VCN CIDR — everything inside it is derived.

---

## CIDR allocation

CloudSpells splits the VCN CIDR by dividing the prefix into increasingly specific subnet tiers:

| Tier | Share | Prefix offset | Rationale |
|------|-------|---------------|-----------|
| Private | 50% | prefix + 1 | OCI VCN-native CNI allocates one subnet IP per running pod. A 100-node cluster with 30 pods/node needs ~3 000 IPs — only the private tier is large enough |
| Secure | 25% | prefix + 2 | Databases need far fewer IPs; generous allocation leaves room for replicas and future growth |
| Public | 12.5% | prefix + 3 | Each OCI Load Balancer uses 2 IPs (primary + failover). Even large deployments rarely exceed ~50 IPs here |
| Management | 12.5% | prefix + 3 | Monitoring agents, Bastion service, VPN endpoints; same Service-Gateway-only isolation as secure |

For a `/16` VCN:

| Tier | CIDR | Usable IPs |
|------|------|-----------|
| Private | `10.0.0.0/17` | 32 766 |
| Secure | `10.0.128.0/18` | 16 382 |
| Public | `10.0.192.0/19` | 8 190 |
| Management | `10.0.224.0/19` | 8 190 |

The VCN CIDR must be RFC 1918 (`10.x`, `172.16–31.x`, `192.168.x`) with a prefix between `/16` and `/20`. Smaller prefixes produce the same tier structure at reduced scale.

---

## Routing per tier

Each tier has its own route table. Routing is fixed — not configurable:

| Tier | Default route (`0.0.0.0/0`) | Oracle services |
|------|----------------------------|-----------------|
| Public | Internet Gateway | — |
| Private | NAT Gateway | Service Gateway |
| Secure | **none** | Service Gateway |
| Management | **none** | Service Gateway |

### Why the secure tier has no default route

The secure tier is designed for stateful data stores — databases, key vaults, audit logs. The threat model for these resources requires they **never initiate internet connections**, even outbound. If a database is compromised, there should be no network path to exfiltrate data to an external server.

Removing the default route enforces this at the infrastructure level. No application misconfiguration, security group oversight, or OS-level firewall gap can create an internet path that does not exist at the routing layer.

### Why the private tier has NAT

Application servers (and Kubernetes pods with VCN-native CNI) need outbound internet access for:

- OS package updates
- External API calls (payment processors, SMS gateways, monitoring services)
- Container image pulls from public registries

NAT Gateway provides this without making instances directly reachable from the internet. Private instances have no public IP and cannot receive unsolicited inbound connections — only outbound connections they initiate.

### Why management has no NAT

Monitoring agents and management tooling communicate with OCI control-plane services (monitoring, logging, object storage) via the Service Gateway — no internet path is needed. Keeping the management tier at the same isolation level as the secure tier means a compromised monitoring agent cannot reach the internet.

---

## Gateways

Three gateways are created for every VCN:

| Gateway | Purpose |
|---------|---------|
| **Internet Gateway** | Bidirectional internet access for the public subnet. Requires instances to have a public IP or be behind a load balancer. |
| **NAT Gateway** | Outbound-only internet access for the private subnet. Instances have no public IP and cannot receive inbound connections. |
| **Service Gateway** | Access to Oracle-managed services (Object Storage, Container Registry, Monitoring, Logging, etc.) without traversing the public internet. Used by private, secure, and management tiers. |

---

## Security enforcement

OCI enforces network rules at two layers. CloudSpells populates both automatically:

**Security Lists** — applied at the subnet boundary. OCI evaluates these rules before traffic enters or leaves the subnet. CloudSpells adds security list rules when role-bearing NSGs are declared, and cross-subnet rules when `nsg.serves()` is called between NSGs in different tiers.

**NSGs** — applied at the VNIC (network interface) level. More granular than security lists; traffic between two NSGs in the same subnet is controlled entirely by NSG rules. CloudSpells generates NSG rules from the role and from `serves()` relationships.

Both layers are always consistent. You never write a rule in one layer and forget the other.

---

## VCN CIDR selection guide

| Deployment scale | Recommended VCN CIDR | Private subnet | Notes |
|-----------------|---------------------|----------------|-------|
| Development / lab | `10.0.0.0/20` | `/21` (2 046 IPs) | Fine for small OKE clusters (< 10 nodes) |
| Small production | `10.0.0.0/18` | `/19` (8 190 IPs) | Suitable for moderate-sized clusters |
| Medium production | `10.0.0.0/17` | `/18` (16 382 IPs) | Comfortable headroom for OKE autoscaling |
| Large / enterprise | `10.0.0.0/16` | `/17` (32 766 IPs) | Maximum scale |

**Rule of thumb for OKE:** estimate `(max_nodes × max_pods_per_node) + max_nodes` IPs for the private subnet. Add 20% headroom for rolling upgrades.

---

## What cannot be changed

The following are fixed by design and are not exposed as parameters:

- **Number of tiers** (always 4)
- **Tier names and purposes** (public / private / secure / management)
- **CIDR allocation ratios** (50 / 25 / 12.5 / 12.5)
- **Gateway types per tier** (Internet / NAT / Service as described above)
- **Routing policy per tier** (default route target is fixed per tier)

This is intentional. If you need a different topology, use raw `pulumi_oci` resources. CloudSpells is for use-cases where the reference architecture fits — and for those use-cases, the fixed topology means you cannot get it wrong.
