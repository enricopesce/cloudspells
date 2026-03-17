# VCN Architecture Reference

Complete technical reference for the `Vcn` spell. This page covers the network topology, CIDR allocation algorithm, gateway configuration, routing policy, security list lifecycle, and the `VcnRef` cross-stack pattern.

---

## Overview

`Vcn` is a Pulumi `ComponentResource` that encodes a fixed four-tier OCI network topology. It creates the VCN, three gateways, four route tables, four security lists, and four subnets in a single declaration. The user supplies a name, compartment OCID, and optionally a CIDR block — everything else is derived.

**Resources created (every VCN):**

| Resource type | Count | Notes |
|---|---|---|
| `oci.core.Vcn` | 1 | The VCN itself |
| `oci.core.InternetGateway` | 1 | Public subnet egress/ingress |
| `oci.core.NatGateway` | 1 | Private subnet outbound-only internet |
| `oci.core.ServiceGateway` | 1 | Oracle service plane (OCIR, Monitoring, Logging) |
| `oci.core.RouteTable` | 4 | One per subnet tier |
| `oci.core.SecurityList` | 4 | Created by `finalize_network` |
| `oci.core.Subnet` | 4 | Created by `finalize_network` |

---

## Subnet topology

The VCN CIDR is divided into four contiguous, CIDR-aligned tiers by binary subdivision. The formula applies at any prefix length.

```
VCN  (prefix /N)                                  100%
├── Private     prefix /(N+1)   lower half    —   50%
└── remainder   prefix /(N+1)   upper half
    ├── Secure      prefix /(N+2)  lower half  —  25%
    └── remainder   prefix /(N+2)  upper half
        ├── Public      prefix /(N+3)  lower half  — 12.5%
        └── Management  prefix /(N+3)  upper half  — 12.5%
```

The four tiers occupy the VCN CIDR contiguously with no gaps and no overlaps. Private is placed at the naturally CIDR-aligned lower half, guaranteeing that its prefix is always valid regardless of the VCN base address.

### CIDR table by VCN prefix

| VCN CIDR | Private | Secure | Public | Management |
|---|---|---|---|---|
| `10.0.0.0/16` | `10.0.0.0/17` (32 766 h) | `10.0.128.0/18` (16 382 h) | `10.0.192.0/19` (8 190 h) | `10.0.224.0/19` (8 190 h) |
| `10.0.0.0/18` | `10.0.0.0/19` (8 190 h) | `10.0.32.0/20` (4 094 h) | `10.0.48.0/21` (2 046 h) | `10.0.56.0/21` (2 046 h) |
| `10.0.0.0/20` | `10.0.0.0/21` (2 046 h) | `10.0.8.0/22` (1 022 h) | `10.0.12.0/23` (510 h) | `10.0.14.0/23` (510 h) |
| `10.0.0.0/24` | `10.0.0.0/25` (126 h) | `10.0.0.128/26` (62 h) | `10.0.0.192/27` (30 h) | `10.0.0.224/27` (30 h) |

`h` = usable host IPs after subtracting the 5 addresses OCI reserves per subnet (network, broadcast, first, second, and last usable).

**Default CIDR:** `10.0.0.0/18`. Override via the `cidr_block` parameter.

### Subnet accessor methods

CIDR values are available immediately after `Vcn.__init__` — before `finalize_network` is called — so other spells can use them when constructing security rules:

| Method | Returns |
|---|---|
| `vcn.get_public_subnet_cidr()` | Public subnet CIDR as `pulumi.Input[str]` |
| `vcn.get_private_subnet_cidr()` | Private subnet CIDR as `pulumi.Input[str]` |
| `vcn.get_secure_subnet_cidr()` | Secure subnet CIDR as `pulumi.Input[str]` |
| `vcn.get_management_subnet_cidr()` | Management subnet CIDR as `pulumi.Input[str]` |

Return type is `pulumi.Input[str]` (not plain `str`) so the same accessor works identically for both `Vcn` and `VcnRef`.

---

## Tier purposes and constraints

| Tier | `prohibit_public_ip_on_vnic` | Default workloads |
|---|---|---|
| **Public** | `False` — instances may receive public IPs | OCI Load Balancers; OKE API endpoint |
| **Private** | `True` — no public IPs | App servers; OKE worker nodes and pods; instance pools |
| **Secure** | `True` — no public IPs | Databases; secrets managers; audit stores |
| **Management** | `True` — no public IPs | OCI Bastion service; monitoring agents; VPN/FastConnect endpoints |

---

## Gateways

Three gateways are created unconditionally for every VCN.

### Internet Gateway

- **Direction:** bidirectional (inbound + outbound)
- **Used by:** public subnet (default route `0.0.0.0/0`)
- **Requirement:** traffic must be directed at an instance that has a public IP or is behind an OCI Load Balancer; the gateway alone does not expose private instances

### NAT Gateway

- **Direction:** outbound only — instances initiate connections, external hosts cannot
- **Used by:** private subnet (default route `0.0.0.0/0`)
- **Prevents:** any unsolicited inbound connection from the internet to worker nodes or pods

### Service Gateway

- **Direction:** bidirectional with OCI service plane
- **Used by:** private, secure, and management subnets
- **Traffic stays within OCI:** packets to Oracle services (OCIR, Object Storage, Monitoring, Logging, Streaming) exit through the service gateway and never traverse the internet, even when the destination is a public IP
- **CIDR block:** the `all <region> services` CIDR block is fetched from `oci.core.get_services().services[0]` at plan time

---

## Routing

Each subnet tier has a dedicated route table. The routes are fixed and not configurable.

### Public route table

| Destination | Via | Notes |
|---|---|---|
| `0.0.0.0/0` | Internet Gateway | All traffic not matched by a more specific route exits to the internet |

### Private route table

| Destination | Via | Notes |
|---|---|---|
| `0.0.0.0/0` | NAT Gateway | Outbound-only internet (image pulls, external API calls) |
| `<services CIDR>` | Service Gateway | Oracle services without internet transit |

### Secure route table

| Destination | Via | Notes |
|---|---|---|
| `<services CIDR>` | Service Gateway | Oracle services only — no default route, no internet path |

**Design rationale:** Instances in the secure tier (databases, key vaults) must never initiate an internet connection. The absence of a default route enforces this at the infrastructure level. No misconfigured application, missing security rule, or OS-level firewall gap can create an internet path that does not exist in the route table.

### Management route table

| Destination | Via | Notes |
|---|---|---|
| `<services CIDR>` | Service Gateway | Same isolation policy as secure — management agents communicate with OCI control-plane services only |

---

## Security list lifecycle (builder pattern)

Security lists and subnets are **not** created in `Vcn.__init__`. They are created only when `finalize_network` is called. This is deliberate: multiple spells (OKE, Compute, ScalableWorkload) contribute rules to the same security lists, and OCI enforces a hard limit of **5 security lists per subnet**. By using one list per subnet and accumulating all rules before creating it, CloudSpells consumes 1 slot and leaves 4 free for additional services.

### Initialisation sequence

```
Vcn.__init__()                     ← creates VCN, gateways, route tables
  │
  ├─ spell1.add_security_list_rules(...)   ← accumulate rules
  ├─ spell2.add_security_list_rules(...)   ← accumulate rules
  │
  └─ vcn.finalize_network()               ← creates security lists + subnets
       (idempotent: subsequent calls are no-ops)
```

When other CloudSpells spells are used (OKE, Compute, ScalableWorkload), they call `finalize_network` automatically at the end of their `__init__`. In standalone mode — a VCN without other spells — call `finalize_network` explicitly.

### `add_security_list_rules`

Accumulates rules into eight internal lists (one ingress + one egress per tier). Must be called **before** `finalize_network`. Raises `RuntimeError` if called after.

```python
vcn.add_security_list_rules(
    public_ingress=[...],
    public_egress=[...],
    private_ingress=[...],
    private_egress=[...],
    secure_ingress=[...],
    secure_egress=[...],
    management_ingress=[...],
    management_egress=[...],
)
```

All parameters are optional. Omit tiers you are not modifying.

### `finalize_network`

Idempotent. Only the first call creates resources. After it returns:

- `vcn.public_security_list` — `oci.core.SecurityList`
- `vcn.private_security_list` — `oci.core.SecurityList`
- `vcn.secure_security_list` — `oci.core.SecurityList`
- `vcn.management_security_list` — `oci.core.SecurityList`
- `vcn.public_subnet` — `oci.core.Subnet`
- `vcn.private_subnet` — `oci.core.Subnet`
- `vcn.secure_subnet` — `oci.core.Subnet`
- `vcn.management_subnet` — `oci.core.Subnet`

If `flow_logs=True` was passed to `__init__`, a `VcnFlowLogs` component is also created inside `finalize_network` and accessible via `vcn.flow_logs`.

---

## Flow logs (opt-in)

Pass `flow_logs=True` to `Vcn.__init__` to enable VCN Flow Logs for all four subnets. Flow logs capture accepted and rejected traffic at the subnet boundary — useful for network audit, threat detection, and debugging.

```python
vcn = Vcn(
    name="prod",
    compartment_id=comp_id,
    flow_logs=True,
    flow_logs_retention=90,   # days: 30 | 60 | 90 | 120 | 150 | 180
)
```

The `VcnFlowLogs` component (accessible via `vcn.flow_logs`) creates an OCI log group and one OCI log resource per subnet tier. The log group OCID is exported as `network_audit_log_group_id` when `vcn.export()` is called.

Flow logs are **not enabled by default** — the additional OCI Logging cost may not be justified for all environments.

---

## `VcnRef` — cross-stack reference

`VcnRef` is a read-only handle to a VCN managed by a separate Pulumi stack. It exposes the same interface as `Vcn` (subnet accessors, security list references, `add_security_list_rules` as a no-op) so spells that accept `Vcn | VcnRef` work identically with either.

**When `add_security_list_rules` is called on a `VcnRef`:** the call is a no-op and Pulumi emits a warning. Any security rules required by the deployed spells must already exist in the source VCN stack.

### Constructing a `VcnRef` from a stack reference

```python
vcn = VcnRef.from_stack_reference("acme/networking/prod")
```

The source stack must export the following keys (all emitted automatically by `Vcn.export()`):

| Export key | Type | Description |
|---|---|---|
| `vcn_id` | `str` | VCN OCID |
| `cidr_block` | `str` | VCN CIDR |
| `public_subnet_id` | `str` | Public subnet OCID |
| `private_subnet_id` | `str` | Private subnet OCID |
| `secure_subnet_id` | `str` | Secure subnet OCID |
| `management_subnet_id` | `str` | Management subnet OCID |
| `public_subnet_cidr` | `str` | Public subnet CIDR |
| `private_subnet_cidr` | `str` | Private subnet CIDR |
| `secure_subnet_cidr` | `str` | Secure subnet CIDR |
| `management_subnet_cidr` | `str` | Management subnet CIDR |
| `public_security_list_id` | `str` | Public security list OCID |
| `private_security_list_id` | `str` | Private security list OCID |
| `secure_security_list_id` | `str` | Secure security list OCID |
| `management_security_list_id` | `str` | Management security list OCID |

### Constructing a `VcnRef` manually

When the source stack does not use CloudSpells:

```python
vcn = VcnRef(
    vcn_id="ocid1.vcn.oc1...",
    public_subnet_id="ocid1.subnet.oc1...",
    private_subnet_id="ocid1.subnet.oc1...",
    public_subnet_cidr="10.0.192.0/19",
    private_subnet_cidr="10.0.0.0/17",
)
```

---

## `Vcn.export()` — stack outputs

Call `export()` to publish the canonical VCN outputs. This makes the network consumable by other stacks via `VcnRef.from_stack_reference`.

`export()` calls `finalize_network()` automatically if it has not been called yet.

```python
vcn = Vcn(name="prod", compartment_id=comp_id)
vcn.export()
```

Exported keys match the table in the `VcnRef` section above, plus `network_audit_log_group_id` when flow logs are enabled.

---

## CIDR sizing guide

| Deployment scale | Recommended VCN CIDR | Private subnet | Usable IPs |
|---|---|---|---|
| Lab / development | `10.0.0.0/20` | `/21` | 2 046 |
| Small production | `10.0.0.0/18` | `/19` | 8 190 |
| Medium production | `10.0.0.0/17` | `/18` | 16 382 |
| Large / enterprise | `10.0.0.0/16` | `/17` | 32 766 |

**Rule of thumb for OKE with VCN-native CNI:** `(max_nodes × max_pods_per_node) + max_nodes` IPs for the private subnet. Add 20% headroom for rolling upgrades and surge capacity.

For a 100-node cluster at 30 pods/node: `(100 × 30) + 100 = 3 100` IPs minimum. A `/20` VCN (2 046 usable private IPs) is insufficient; a `/18` (8 190) or larger is required.

---

## What is fixed by design

The following are architectural constants — not parameters:

| Fixed value | Rationale |
|---|---|
| 4 subnet tiers | Minimum number of distinct isolation zones for a production workload |
| Tier names (public / private / secure / management) | Names encode intent; changing them requires changing everything that depends on them |
| CIDR ratios (50 / 25 / 12.5 / 12.5) | Derived from OKE pod density requirements; private must dominate |
| Internet GW on public only | Other tiers have no legitimate reason to accept unsolicited inbound connections |
| NAT GW on private only | Secure and management tiers reach only Oracle services; internet transit is not required |
| No default route on secure and management | Eliminates the exfiltration path at the infrastructure level |

If your use-case requires a different topology, use `pulumi_oci` directly. CloudSpells is for use-cases where this reference architecture fits.