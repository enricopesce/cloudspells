# Design Philosophy

Understanding why CloudSpells is built the way it is helps you use it correctly — and helps you know when *not* to use it.

---

## The problem CloudSpells solves

Raw Pulumi and Terraform give you every knob. You define VCNs, subnets, route tables, gateways, and security lists individually, wire them together yourself, and make every architectural decision at the keyboard.

That freedom is also the source of every misconfigured security rule, every missing NAT route, and every accidentally-public subnet. The platform team's job is to encode best practices. The application team's job is to deploy applications. Raw IaC tools conflate those jobs.

**CloudSpells separates them.**

| With raw Pulumi / Terraform | With CloudSpells |
|-----------------------------|-----------------|
| Define VCN, subnets, route tables, gateways, security lists — each resource individually | `Vcn("lab", compartment_id=cid)` — one call, full 4-tier architecture |
| Calculate CIDR splits manually | Derived automatically from the VCN CIDR |
| Wire NAT, Internet, and Service Gateways to the right route tables | Done by design |
| Write security list rules for every tier | Added by role constants and `serves()` |
| Risk misconfiguring any of the above | Not possible — there are no knobs to misconfigure |

---

## Architecture is the product

CloudSpells makes the architecture the product. Network topology, subnet tiers, gateway placement, routing policy, and security posture are **fixed by design** — derived from OCI best practices — and are not configurable at call time.

The user's job is to name things and pick a location. The block's job is everything else.

This is a deliberate constraint, not a limitation. Every parameter you do not have to specify is one you cannot get wrong.

---

## What CloudSpells is — and is not

**CloudSpells is not a Terraform replacement or a low-level cloud-API wrapper.**

Terraform and raw Pulumi give you every resource type with every attribute exposed. That is the right tool when you need full control over non-standard architectures. CloudSpells is the opposite: it encodes a small set of proven reference architectures and makes them trivially deployable.

```
Low-level tools              CloudSpells
────────────────             ──────────────────────────
Full API surface             Curated building blocks
Maximum flexibility          Minimum required input
Architecture = your problem  Architecture = solved by design
Every knob exposed           Only essential identifiers
```

Use CloudSpells when your architecture matches a reference pattern. Use raw Pulumi when you genuinely need something outside those patterns.

---

## Minimal required input

A block requires only the minimum information that cannot be derived:

- **Name** — every resource needs a name
- **Compartment OCID** — where to deploy in OCI
- **Network reference** — which VCN to attach to

Everything else — CIDRs, subnet placement, route tables, security rules, gateway wiring — is derived or defaulted securely.

**Exposing unnecessary parameters is treated as a design defect.** If a parameter exists only to pass through an underlying OCI provider option, it does not belong in CloudSpells. Users who need that level of control should use raw Pulumi resources directly.

---

## Two layers of security enforcement

OCI enforces network rules at two levels: **Security Lists** (subnet-level, stateful) and **NSGs** (VNIC-level, stateful). CloudSpells populates both automatically so they are always consistent.

When you declare an NSG with a role:

1. The NSG gets the correct ambient VNIC-level rules (ICMP path-MTU, egress to services or internet depending on tier)
2. The VCN security list for that subnet tier gets the corresponding subnet-level rules

When you call `nsg.serves(target, port)`:

1. Both NSGs get bilateral application-port rules
2. When the two NSGs are in different tiers, the cross-subnet security list entries are also generated

You never touch a security list directly. Consistent enforcement at both layers is the default, not an option you have to remember.

---

## The lazy-init builder pattern

The `Vcn` block uses a lazy-init builder pattern. Security rules accumulate as service blocks are declared, and the actual OCI resources (subnets, security lists) are materialised in a single call to `finalize_network()`.

```python
vcn = Vcn("lab", compartment_id=compartment_id)

# Rules accumulate here — no OCI API calls yet
app_nsg = Nsg("app", role=APP_SERVER, vcn=vcn, ...)
app_nsg.serves(db_nsg, port=5432)

# ComputeInstance calls finalize_network() automatically
instance = ComputeInstance("web", vcn=vcn, nsg=app_nsg, ...)
```

This means rule accumulation is order-independent within a stack: you can declare NSGs in any order and the final security list will be correct. `finalize_network()` is idempotent — calling it multiple times has no effect after the first.

---

## Multi-cloud by design

CloudSpells started with OCI and is designed from the ground up to add more providers. The three-layer structure enforces this:

```
src/core/abstractions/     — cloud-neutral interfaces (AbstractNetwork, …)
src/providers/oci/         — OCI implementation
src/providers/aws/         — future
src/providers/gcp/         — future
```

Adding a new provider means implementing the abstractions under a new `src/providers/<cloud>/` directory. No changes to the core layer or to user-facing code are needed. A user who writes `from providers.oci.network import Vcn` today will import `from providers.aws.network import Vpc` tomorrow — same calling convention, same mental model.

---

## When to reach for raw Pulumi instead

CloudSpells is the right tool for reference architectures. Use raw `pulumi_oci` resources when you need:

- A resource type CloudSpells does not cover yet
- Non-standard subnet topology (e.g. a flat single-tier network)
- Fine-grained control over specific provider options for a one-off requirement

You can mix CloudSpells blocks and raw Pulumi resources in the same stack freely. The VCN, subnets, and security lists created by `Vcn` are standard Pulumi outputs — you can reference them from any raw resource.
