# VCN Network Design

## Overview

Every OCIBlocks deployment is built on a single VCN that is divided into four
dedicated tiers.  The tier boundaries are fixed by the CIDR arithmetic, not by
configuration, so every stack gets the same well-known layout regardless of the
VCN size chosen.

---

## Tier Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  VCN  10.0.0.0/18  (default)                                            │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  PRIVATE  10.0.0.0/19   8 190 usable IPs   (50 % of VCN)       │    │
│  │                                                                 │    │
│  │  App servers · OKE worker nodes · instance pools                │    │
│  │                                                                 │    │
│  │  Route: 0.0.0.0/0 → NAT GW   +   OCI services → Service GW    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  SECURE   10.0.32.0/20  4 094 usable IPs   (25 % of VCN)       │    │
│  │                                                                 │    │
│  │  Databases · OKE pod IPs (VCN-native CNI) · secrets managers    │    │
│  │                                                                 │    │
│  │  Route: OCI services → Service GW only  (no internet at all)   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │  PUBLIC   10.0.48.0/21  2 046 usable IPs   (12.5 % of VCN)  │       │
│  │                                                              │       │
│  │  Load balancers · bastion hosts                              │       │
│  │                                                              │       │
│  │  Route: 0.0.0.0/0 → Internet GW                             │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │  MANAGEMENT  10.0.56.0/21  2 046 usable IPs  (12.5 % VCN)   │       │
│  │                                                              │       │
│  │  Monitoring agents · bastion service · VPN/FastConnect       │       │
│  │                                                              │       │
│  │  Route: OCI services → Service GW only  (no internet)       │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
   Internet GW          NAT GW           Service GW
   (public only)   (private only)    (private + secure
                                      + management)
```

---

## Traffic Flow

```
Internet
   │
   │  inbound (443 / 80)
   ▼
┌──────────┐
│  PUBLIC  │  Load Balancers
│          │──────────────────► PRIVATE  (app servers, K8s)
│  Bastion │  SSH jump
│          │──────────────────► PRIVATE / MANAGEMENT
└──────────┘

┌───────────┐
│  PRIVATE  │  DB connections
│           │──────────────────► SECURE  (databases)
│  App tier │  metrics / logs
│           │──────────────────► MANAGEMENT (monitoring)
└───────────┘
      │
      │  outbound (package installs, API calls)
      ▼
   NAT GW ──► Internet

┌──────────┐
│  SECURE  │  DB backups / metrics
│          │──► Service GW ──► OCI Object Storage / Monitoring
└──────────┘
      ✗  no internet path (not even outbound NAT)

┌────────────┐
│ MANAGEMENT │  agent telemetry
│            │──► Service GW ──► OCI Logging / Monitoring
└────────────┘
      ✗  no internet path
```

---

## CIDR Allocation

The VCN is split proportionally, not equally.  With OKE VCN-native pod
networking (`OCI_VCN_IP_NATIVE`):

* **Worker nodes** land in the **private** subnet — one IP per node VNIC.
* **Pod IPs** land in the **secure** subnet — one real subnet IP per running
  pod, with 31 IPs pre-allocated per VNIC before any pod starts.

Both tiers must be sized for their respective populations.

| Tier | Proportion | Prefix offset | /18 VCN (default) | /16 VCN | /20 VCN (min) |
|------|-----------|---------------|-------------------|---------|---------------|
| Private | 50 % | +1 | `/19` — 8 190 IPs | `/17` — 32 766 IPs | `/21` — 2 046 IPs |
| Secure | 25 % | +2 | `/20` — 4 094 IPs | `/18` — 16 382 IPs | `/22` — 1 022 IPs |
| Public | 12.5 % | +3 | `/21` — 2 046 IPs | `/19` — 8 190 IPs | `/23` — 510 IPs |
| Management | 12.5 % | +3 | `/21` — 2 046 IPs | `/19` — 8 190 IPs | `/23` — 510 IPs |

**Why not equal quarters?**  An equal split of a `/18` gives each tier `/20`
(4 094 IPs).  Pod consumption dominates: a 100-node cluster with 30 pods/node
consumes ~3 000 IPs in the secure tier alone, plus ~100 IPs in private for the
node VNICs.  Giving private 50 % (8 190 IPs) provides headroom for both current
pods-per-node counts and future cluster growth without a disruptive VCN resize.

### CIDR calculation example for `10.0.0.0/18`

```
10.0.0.0/18  →  split in half
│
├── 10.0.0.0/19   ← private  (first half, largest block)
│
└── 10.0.32.0/19  →  split in half
    │
    ├── 10.0.32.0/20  ← secure  (first quarter)
    │
    └── 10.0.48.0/20  →  split in half
        │
        ├── 10.0.48.0/21  ← public      (first eighth)
        └── 10.0.56.0/21  ← management  (last eighth)
```

---

## Routing

| Tier | Default route | OCI service CIDR |
|------|--------------|-----------------|
| Public | `0.0.0.0/0` → Internet Gateway | — |
| Private | `0.0.0.0/0` → NAT Gateway | → Service Gateway |
| Secure | **none** | → Service Gateway |
| Management | **none** | → Service Gateway |

The **absence of a default route** in the secure and management tiers is the
critical security control.  A workload in those tiers cannot initiate any
outbound connection to the internet — not even via NAT.  The only external
reachability is to OCI-managed service endpoints (Object Storage, Logging,
Monitoring) via the Service Gateway, which never traverses the public internet.

---

## Security List Strategy

Each tier has exactly one security list.  The OCI limit is five lists per
subnet; keeping to one leaves four slots free for future service-specific rules
applied outside OCIBlocks.

Rules are accumulated via the builder pattern before the subnets are created:

```python
vcn = Vcn(name="prod", compartment_id=comp_id)

# Each service block registers its own rules:
oke = OkeCluster(vcn=vcn, ...)          # adds K8s API + node rules
db  = DatabaseBlock(vcn=vcn, ...)       # adds DB port rules (future)

# finalize_network() is called automatically by the last block,
# or explicitly in standalone mode:
vcn.finalize_network()
```

---

## Subnet Constants

Import the tier constants instead of bare strings to get type checking and
IDE auto-complete:

```python
from blocks.vcn.network import SUBNET_PUBLIC, SUBNET_PRIVATE, SUBNET_SECURE, SUBNET_MANAGEMENT

instance = ComputeInstance(
    name="app",
    vcn=vcn,
    compartment_id=comp_id,
    subnet=SUBNET_PRIVATE,   # ← type-checked as SubnetTier literal
)
```

| Constant | Value | Default for |
|----------|-------|-------------|
| `SUBNET_PUBLIC` | `"public"` | Load balancers, bastion |
| `SUBNET_PRIVATE` | `"private"` | App servers, K8s nodes (default) |
| `SUBNET_SECURE` | `"secure"` | Databases, secrets |
| `SUBNET_MANAGEMENT` | `"management"` | Monitoring, VPN, internal tooling |

---

## VCN Size Rules

Three rules are enforced on every plain-string `cidr_block` value at
construction time.  Dynamic `pulumi.Output` values are accepted without
validation and must be controlled by the caller.

| Rule | Constraint | Reason |
|------|-----------|--------|
| RFC 1918 only | `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16` | Public IPs in VCN CIDR conflict with internet routing |
| No host bits | Network-canonical form (`10.0.0.0/18`, not `10.0.1.0/18`) | OCI rejects non-canonical CIDRs |
| Prefix `/16`–`/20` | Minimum `/20` keeps private at `/21` (2 046 IPs) for worker VNICs and secure at `/22` (1 022 IPs) for pod IPs | Tighter prefix leaves the secure subnet too small for VCN-native pod IPs (~100 nodes × 10 pods = 1 000 IPs minimum) |

Violations raise `ValueError` immediately with a clear message, before any
OCI API call is made.
