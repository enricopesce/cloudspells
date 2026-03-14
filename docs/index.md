# CloudBlocks

High-level, opinionated infrastructure building blocks for Oracle Cloud Infrastructure — built on Pulumi.

CloudBlocks encodes proven reference architectures as immutable, composable building blocks. Instead of wiring together low-level resources yourself, you declare what you want — a VCN, a scalable workload, a Kubernetes cluster — and CloudBlocks handles every topology, routing, and security decision correctly by default. It is multi-cloud by design: a cloud-neutral abstraction layer sits above provider-specific implementations, starting with OCI.

## What makes CloudBlocks different

- **Architecture is the product.** Network topology, subnet tiers, routing policy, gateway placement, and security posture are fixed by design — derived from cloud-provider best practices — and are not configurable at call time.
- **Minimal required input.** A block requires only essential identifiers (name, compartment, network CIDR). Every value that can be derived, computed, or defaulted securely must be — exposing unnecessary parameters is treated as a design defect.
- **Not a Terraform replacement.** CloudBlocks is the opposite of a thin API wrapper. Terraform and raw Pulumi give you every knob and let you wire everything yourself; CloudBlocks makes the hard decisions for you so you cannot misconfigure them.

## Quick start

```python
import pulumi
import pulumi_oci as oci
from providers.oci.network import Vcn
from providers.oci.compute import ComputeInstance

config = pulumi.Config()
compartment_id = config.require("compartment_ocid")

# A fully-wired 4-tier VCN — public, private, secure, and management subnets,
# all gateways, and correct routing — from a single call.
vcn = Vcn(
    "lab",
    compartment_id=compartment_id,
    cidr_block="10.0.0.0/16",
)

# A compute instance in the private subnet with automatic SSH key generation
# and a block volume — no further wiring needed.
instance = ComputeInstance(
    "app",
    compartment_id=compartment_id,
    vcn=vcn,
    shape="VM.Standard.E4.Flex",
    image_id=config.require("image_ocid"),
)

pulumi.export("instance_ip", instance.private_ip)
```

## Navigation

| Section | Description |
|---------|-------------|
| [API Reference — Core](api/core/base.md) | `BaseResource`, naming, tagging, and helper utilities |
| [API Reference — Abstractions](api/core/abstractions/network.md) | Cloud-neutral dataclasses and abstract base classes |
| [API Reference — Blocks](api/blocks/vcn.md) | High-level OCI building blocks (VCN, Compute, OKE, …) |
| [API Reference — OCI Provider](api/providers/network.md) | Full OCI provider implementation details |

## Design principles

**1. High-level constructs, not low-level wrappers.**
CloudBlocks encodes fixed, opinionated reference architectures. It is not a Terraform replacement or a thin cloud-API layer. Architecture decisions — topology, routing, security posture — are baked in, not left to the caller.

**2. Minimal user input.**
Blocks must require only essential identifiers. Every value that can be derived, computed, or defaulted securely must be. Exposing unnecessary parameters — especially ones that just pass through underlying provider options — is a design defect.

**3. Full documentation required.**
Every public class, method, and module has a Google-style docstring. No undocumented public API is acceptable.
