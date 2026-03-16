# CloudSpells

High-level, opinionated infrastructure building blocks for Oracle Cloud Infrastructure — built on Pulumi.

CloudSpells encodes proven reference architectures as immutable, composable building blocks. Instead of wiring together low-level resources yourself, you declare what you want — a VCN, a scalable workload, a Kubernetes cluster — and CloudSpells handles every topology, routing, and security decision correctly by default. It is multi-cloud by design: a cloud-neutral abstraction layer sits above provider-specific implementations, starting with OCI.

## What makes CloudSpells different

- **Architecture is the product.** Network topology, subnet tiers, routing policy, gateway placement, and security posture are fixed by design — derived from cloud-provider best practices — and are not configurable at call time.
- **Minimal required input.** A block requires only essential identifiers (name, compartment, network CIDR). Every value that can be derived, computed, or defaulted securely must be — exposing unnecessary parameters is treated as a design defect.
- **Not a Terraform replacement.** CloudSpells is the opposite of a thin API wrapper. Terraform and raw Pulumi give you every knob and let you wire everything yourself; CloudSpells makes the hard decisions for you so you cannot misconfigure them.

## Quick start

```python
from core import Config
from providers.oci.network import Vcn
from providers.oci.compute import ComputeInstance
from providers.oci.nsg import Nsg, HTTP, HTTPS, SSH
from providers.oci.roles import INTERNET_EDGE

config = Config()
compartment_id = config.require("compartment_ocid")

# A fully-wired 4-tier VCN — public, private, secure, and management subnets,
# all gateways, and correct routing — from a single call.
vcn = Vcn("lab", compartment_id=compartment_id)

# An NSG role — places this resource in the public subnet, opens HTTP/HTTPS/SSH,
# and adds ICMP path-MTU rules automatically.
web_nsg = Nsg("web", role=INTERNET_EDGE, ports=[HTTP, HTTPS, SSH],
              vcn=vcn, compartment_id=compartment_id)

# A compute instance — subnet inferred from the NSG role, SSH key auto-generated.
instance = ComputeInstance("web", compartment_id=compartment_id, vcn=vcn, nsg=web_nsg)

vcn.export()
instance.export()
```

## Where to start

| I want to… | Go to |
|-----------|-------|
| Install CloudSpells and set up credentials | [Getting Started → Installation](getting-started/installation.md) |
| Deploy my first VCN | [Getting Started → First Deploy](getting-started/first-deploy.md) |
| Deploy a compute instance | [Tutorials → Compute Instance](tutorials/compute.md) |
| Deploy an OKE Kubernetes cluster | [Tutorials → OKE Cluster](tutorials/oke.md) |
| Deploy an autoscaling web tier | [Tutorials → Scalable Workload](tutorials/autoscale.md) |
| Share a VCN between stacks | [How-to → Share a VCN Across Stacks](how-to/vcnref.md) |
| Configure security rules | [How-to → Configure NSG Rules](how-to/nsg-rules.md) |
| SSH into a private instance | [How-to → Use a Bastion](how-to/bastion.md) |
| Understand the design philosophy | [Concepts → Design Philosophy](concepts/design.md) |
| Understand the 4-tier network topology | [Concepts → Network Topology](concepts/network-topology.md) |
| Browse the full API | [API Reference → OCI Provider](api/providers/network.md) |

## Design principles

**1. Architecture is the product.**
Network topology, subnet tiers, routing policy, gateway placement, and security posture are fixed by design — derived from OCI best practices — and are not configurable at call time.

**2. Minimal required input.**
A block requires only essential identifiers (name, compartment, network). Every value that can be derived, computed, or defaulted securely must be. Exposing unnecessary parameters is a design defect.

**3. Not a Terraform replacement.**
CloudSpells encodes opinionated reference architectures. For non-standard topologies or full control over individual resources, use raw Pulumi. You can mix both in the same stack freely.
