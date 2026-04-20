# VCN Architecture Reference

Complete technical reference for the `Vcn` spell. This page covers the network topology, CIDR allocation algorithm, gateway configuration, routing policy, security list lifecycle, and the `VcnRef` cross-stack pattern.

---

## Overview

`Vcn` is a Pulumi `ComponentResource` that encodes a fixed four-tier OCI network topology. It creates the VCN, three gateways, four route tables, four security lists, and four subnets in a single declaration. The user supplies a name, compartment OCID, and optionally a CIDR block — everything else is derived.

**Resources created (every VCN):**

| Resource type | Count | Notes |
|---|---|---|
| `oci.core.Vcn` | 1 | The VCN itself |
| `oci.core.DefaultSecurityList` | 1 | Overrides the VCN built-in default security list with zero rules — see [Default security list neutralisation](#default-security-list-neutralisation) |
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
- **CIDR block:** the `all <region> services` CIDR block is resolved lazily via `oci.core.get_services_output()` at plan time — no blocking API call is made during Python construction

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

## Default security list neutralisation

Every OCI VCN ships with a built-in **default security list** that is automatically attached to every subnet. Out of the box this list includes a wide-open egress rule (`0.0.0.0/0`, all protocols) which would silently permit outbound traffic regardless of the per-tier security lists CloudSpells manages.

`Vcn` immediately neutralises this list by creating an `oci.core.DefaultSecurityList` resource that takes ownership of it and sets both its ingress and egress rule sets to empty. The resource is accessible via `vcn.default_security_list`.

After neutralisation, only the four per-tier security lists created by `finalize_network` are in effect. Every subnet operates under a **deny-by-default** whitelist model — a packet is permitted only if a matching rule exists in the subnet's security list (or an attached NSG).

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

### Baseline security rules

Before creating the security lists, `finalize_network` injects a fixed set of baseline rules that are always present regardless of which spells have contributed their own rules.

**Applied to the private tier (egress):**

| Protocol | Destination | Description |
|---|---|---|
| ALL | `0.0.0.0/0` (CIDR_BLOCK) — route table directs traffic to the NAT Gateway | Outbound-only internet egress for image pulls and external API calls |
| ALL | `<services CIDR>` | Oracle service plane egress (OCIR, Monitoring, Logging) |

**Applied to the private, secure, and management tiers (egress):**

| Protocol | Destination | Description |
|---|---|---|
| ALL | `<services CIDR>` | Oracle service plane egress without internet transit |

**Secure-tier segmentation (ingress):**

| Protocol | Source | Description |
|---|---|---|
| TCP (all ports) | Private subnet CIDR | Only the private (application) tier may initiate connections into the secure (data) tier |

The secure-tier rule establishes the canonical private→secure communication path (app servers → databases) at the security-list layer. All other inbound sources — public subnet, management subnet, internet — are implicitly denied by the deny-by-default model. OCI stateful connection tracking handles return packets; no matching egress rule is required.

Individual spells and NSGs add port-specific rules on top of this baseline.

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

`VcnRef` is a read-only handle to a CloudSpells VCN managed by a separate Pulumi stack. It exposes the same interface as `Vcn` (subnet accessors, security list references) so spells that accept `Vcn | VcnRef` work identically with either.

**`VcnRef` is only supported for VCNs created by CloudSpells.** The source stack must export the standard CloudSpells output keys (all emitted automatically by `Vcn.export()`).

**When `add_security_list_rules` is called on a `VcnRef`:** a `RuntimeError` is raised immediately, listing the rule sets that cannot be applied. Any security rules required by the deployed spells must already exist in the source CloudSpells VCN stack — add them there first, then re-run this stack.

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
| `drg_id` | `str \| None` | DRG OCID (optional — `None` when no DRG is attached) |

### Constructing a `VcnRef` manually

When consuming a CloudSpells VCN that does not publish a Pulumi stack reference (e.g. a VCN created by an older CloudSpells deployment without `export()`), you can construct `VcnRef` directly with the OCID and CIDR values:

```python
vcn = VcnRef(
    vcn_id="ocid1.vcn.oc1...",
    cidr_block="10.0.0.0/18",          # required — raises ValueError if omitted
    public_subnet_id="ocid1.subnet.oc1...",
    private_subnet_id="ocid1.subnet.oc1...",
    secure_subnet_id="ocid1.subnet.oc1...",
    management_subnet_id="ocid1.subnet.oc1...",
    public_subnet_cidr="10.0.48.0/21",
    private_subnet_cidr="10.0.0.0/19",
    secure_subnet_cidr="10.0.32.0/20",
    management_subnet_cidr="10.0.56.0/21",
)
```

`cidr_block` is **required**. Omitting it raises `ValueError` immediately — the constructor will not silently fall back to an incorrect value.

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

## Optional constructor parameters

The following `Vcn.__init__` parameters are all optional. The required parameters are `name` and `compartment_id`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `cidr_block` | `str` | `"10.0.0.0/18"` | VCN IPv4 CIDR |
| `additional_cidr_blocks` | `list[str]` | `None` | Extra secondary CIDRs attached to the VCN |
| `ipv6_enabled` | `bool` | `False` | Enable OCI-assigned IPv6 on the VCN |
| `flow_logs` | `bool` | `False` | Enable `VcnFlowLogs` for all four subnets |
| `flow_logs_retention` | `int` | `90` | Flow-log retention in days: 30 / 60 / 90 / 120 / 150 / 180 |
| `drg` | `bool` | `False` | Attach a Dynamic Routing Gateway (FastConnect / IPSec VPN) |
| `on_premise_cidrs` | `list[str]` | `None` | On-premises CIDRs routed via the DRG (requires `drg=True`) |
| `nat_public_ip_id` | `str` | `None` | Reserved public IP OCID to assign to the NAT Gateway |
| `nat_block_traffic` | `bool` | `False` | Block all NAT Gateway egress without deleting the gateway |
| `dhcp_options_id` | `str` | `None` | Custom DHCP options OCID — overrides the VCN default |
| `defined_tags` | `pulumi.Input[dict[str, pulumi.Input[str]]]` | `None` | OCI defined tags applied to the VCN and all child resources |

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