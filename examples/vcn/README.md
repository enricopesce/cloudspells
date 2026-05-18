# VCN Example

Deploys a standalone Virtual Cloud Network with a 4-tier subnet architecture,
gateways, route tables, and security lists.  All outputs are exported so other
stacks can import this VCN via `VcnRef.from_stack_reference()` without
recreating any network resources.

## Network architecture

```
VCN  10.0.0.0/18  (default — 16 384 IPs total)
│
├── private   10.0.0.0/19    8 190 usable  ← NAT GW + Service GW
│   App servers · K8s nodes · instance pools
│   Gets 50 % of the VCN because OCI VCN-native pod networking
│   allocates one subnet IP per running pod.
│
├── secure    10.0.32.0/20   4 094 usable  ← Service GW only (no NAT)
│   Databases · secrets managers · audit stores
│   No internet path at all — not even outbound NAT.
│   A compromised workload here cannot reach the internet.
│
├── public    10.0.48.0/21   2 046 usable  ← Internet GW
│   Load balancers · bastion hosts
│   Only resources that must receive internet traffic live here.
│
└── management  10.0.56.0/21   2 046 usable  ← Service GW only (no NAT)
    Monitoring agents · bastion service · VPN/FastConnect endpoints
    Same isolation policy as secure — no internet access.
```

### Tier sizing rationale

| Tier | Share | Rationale |
|------|-------|-----------|
| Private | 50 % (prefix+1) | OCI VCN-native CNI gives every pod its own subnet IP — a 100-node cluster with 30 pods/node consumes ~3 000 IPs |
| Secure | 25 % (prefix+2) | Databases need far fewer IPs; generous allocation leaves room for replicas and future growth |
| Public | 12.5 % (prefix+3) | Each OCI Load Balancer uses 2 IPs (primary + failover); even a large deployment rarely needs more than ~50 IPs here |
| Management | 12.5 % (prefix+3) | Monitoring agents, bastion service, VPN/FastConnect; shares the same Service-Gateway-only routing as the secure tier |

### Routing per tier

| Tier | Default route | OCI services |
|------|--------------|--------------|
| Public | `0.0.0.0/0` → Internet Gateway | — |
| Private | `0.0.0.0/0` → NAT Gateway | Service Gateway |
| Secure | **none** | Service Gateway only |
| Management | **none** | Service Gateway only |

## What gets created

- 1 VCN
- Internet Gateway, NAT Gateway, Service Gateway
- 4 route tables (public / private / secure / management)
- 4 security lists (populated by spells via the builder pattern)
- 4 subnets (public / private / secure / management)

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

## Deploy

```bash
cd examples/vcn

pulumi stack init dev
pulumi config set compartment_ocid <your-compartment-ocid>

pulumi preview
pulumi up
```

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `cidr_block` | VCN CIDR block |
| `public_subnet_id` | OCID of the public subnet |
| `private_subnet_id` | OCID of the private subnet |
| `secure_subnet_id` | OCID of the secure subnet |
| `public_subnet_cidr` | Public subnet CIDR |
| `private_subnet_cidr` | Private subnet CIDR |
| `secure_subnet_cidr` | Secure subnet CIDR |
| `public_security_list_id` | Public security list OCID |
| `private_security_list_id` | Private security list OCID |
| `secure_security_list_id` | Secure security list OCID |
| `management_subnet_id` | OCID of the management subnet |
| `management_subnet_cidr` | Management subnet CIDR |
| `management_security_list_id` | Management security list OCID |
| `drg_id` | DRG OCID, or `None` when no DRG is attached |
| `cloudspells_network_schema` | CloudSpells OCI VCN schema marker |
| `cloudspells_network_profiles` | Network profiles installed in this VCN stack |

All outputs are consumed automatically by `VcnRef.from_stack_reference()`
when another stack imports this VCN.

## Teardown

```bash
pulumi destroy
```
