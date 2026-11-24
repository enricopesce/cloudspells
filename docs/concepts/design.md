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
| Wire network permissions between workloads | NSG roles and `serves()` |
| Risk misconfiguring any of the above | Not possible — there are no knobs to misconfigure |

---

## Architecture is the product

CloudSpells makes the architecture the product. Network topology, subnet tiers, gateway placement, routing policy, and security posture are **fixed by design** — derived from OCI best practices — and are not configurable at call time.

The user's job is to name things and pick a location. The spell's job is everything else.

This is a deliberate constraint, not a limitation. Every parameter you do not have to specify is one you cannot get wrong.

---

## What CloudSpells is — and is not

**CloudSpells is not a Terraform replacement or a low-level cloud-API wrapper.**

Terraform and raw Pulumi give you every resource type with every attribute exposed. That is the right tool when you need full control over non-standard architectures. CloudSpells is the opposite: it encodes a small set of proven reference architectures and makes them trivially deployable.

```
Low-level tools              CloudSpells
────────────────             ──────────────────────────
Full API surface             Curated spells
Maximum flexibility          Minimum required input
Architecture = your problem  Architecture = solved by design
Every knob exposed           Only essential identifiers
```

Use CloudSpells when your architecture matches a reference pattern. Use raw Pulumi when you genuinely need something outside those patterns.

---

## Minimal required input

A spell requires only the minimum information that cannot be derived:

- **Name** — every resource needs a name
- **Compartment OCID** — where to deploy in OCI
- **Network reference** — which VCN to attach to

Everything else — CIDRs, subnet placement, route tables, security rules, gateway wiring — is derived or defaulted securely.

**Exposing unnecessary parameters is treated as a design defect.** If a parameter exists only to pass through an underlying OCI provider option, it does not belong in a spell. Users who need that level of control should use raw Pulumi resources directly.

---

## Resource naming

CloudSpells owns the suffixes passed to `create_resource_name()`. Fixed child resources use literal suffixes such as `vcn`, `sn-private`, or `api-nsg`. Repeated child resources, such as block volumes, node pools, and generated NSG rules, use deterministic ordinal suffixes such as `vol-1`, `pool-1`, or `nsg-rule-1`.

Caller-facing labels remain useful metadata. `VolumeSpec.label`, `NodePoolConfig.name`, and NSG rule labels are used for lookup helpers, outputs, tags, and descriptions; they do not become Pulumi resource-name suffixes.

---

## Security lists and network security groups

Security lists apply to every VNIC in a subnet. NSGs apply to their members. OCI combines the permissions from the applicable lists and groups, including for traffic between VNICs in the same subnet.

The VCN owns the subnet baseline. When you call `nsg.serves(target, port)`, CloudSpells adds egress on the source group and ingress on the target group. See [OCI security rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

## Network finalization

The first subnet consumer calls `finalize_network()` and materializes the four subnets with their lists. NSG rules can be declared before or after that call. Register any explicit subnet-wide policy with `vcn.add_security_rules(...)` before the first subnet consumer, `vcn.export()` or `vcn.finalize_network()`.

---

## Multi-cloud by design

CloudSpells started with OCI and is designed from the ground up to add more providers. The three-layer structure enforces this:

```
packages/cloudspells-core/src/cloudspells/core/abstractions/   — cloud-neutral interfaces (AbstractNetwork, …)
packages/cloudspells-oci/src/cloudspells/providers/oci/        — OCI implementation
packages/cloudspells-aws/src/cloudspells/providers/aws/        — future
packages/cloudspells-gcp/src/cloudspells/providers/gcp/        — future
```

Adding a new provider means implementing the abstractions under a new `packages/cloudspells-<cloud>/` directory. No changes to the core layer or to user-facing code are needed. A user who writes `from cloudspells.providers.oci.network import Vcn` today will import `from cloudspells.providers.aws.network import Vpc` tomorrow — same calling convention, same mental model.

---

## Mental model

Think of a CloudSpells spell as a **constructor for a complete reference architecture**, not a wrapper around a cloud resource.

When you call `Vcn("lab", compartment_id=cid)` you are not creating one resource — you are accepting a pre-built, pre-audited network blueprint and stamping it with a name and a location. The blueprint encodes every decision: four subnet tiers at fixed CIDR ratios, a NAT Gateway for the private tier, no default route for the secure tier, a Service Gateway for OCI-managed traffic. None of those decisions are yours to make — and that is the point.

The same logic applies to every spell. `OkeCluster` is not a thin wrapper over `oci.containerengine.Cluster` — it is an opinionated OKE deployment pattern that includes four NSGs with component-specific rules, cross-AD node placement, and VCN-native CNI. You supply a name, a compartment, and a VCN handle. The spell supplies everything else.

The mental model transfer: **a spell is a building block, not a resource**. The block has one acceptable form. Your job is to choose the right block for the job, not to configure the block's internals.

---

## Practice implications

The fixed-architecture model changes how you write infrastructure code day-to-day:

**Do not pass provider options through.** If a parameter is not in a spell's `__init__` signature, it is not supported. Attempting to forward a raw OCI provider argument is a sign you are reaching outside the spell's intended use. Use raw `pulumi_oci` resources for that resource instead.

**Check spell coverage before designing.** If the reference architecture you need does not match any existing spell, either compose multiple spells (which is the common case) or use raw Pulumi for the non-standard parts. Do not try to bend a spell into a shape it was not built for.

---

## When to reach for raw Pulumi instead

CloudSpells is the right tool for reference architectures. Use raw `pulumi_oci` resources when you need:

- A resource type CloudSpells does not cover yet
- Non-standard subnet topology (e.g. a flat single-tier network)
- Fine-grained control over specific provider options for a one-off requirement

You can mix CloudSpells spells and raw Pulumi resources in the same stack freely. The VCN, subnets, and security lists created by `Vcn` are standard Pulumi outputs — you can reference them from any raw resource.
