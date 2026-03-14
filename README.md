# CloudBlocks — High-Level Infrastructure Building Blocks for OCI

**Stop configuring infrastructure. Start deploying architectures.**

[![CI](https://github.com/enricopesce/ociblocks/actions/workflows/ci.yml/badge.svg)](https://github.com/enricopesce/ociblocks/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/enricopesce/ociblocks)](LICENSE)
[![Pulumi 3.x](https://img.shields.io/badge/pulumi-3.x-blueviolet)](https://www.pulumi.com/)
[![OCI](https://img.shields.io/badge/cloud-OCI-red)](https://www.oracle.com/cloud/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/enricopesce/ociblocks/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue)

CloudBlocks is a Python-based infrastructure as code framework built on [Pulumi](https://www.pulumi.com/) that packages proven Oracle Cloud Infrastructure reference architectures as minimal, opinionated building blocks — you name things, the block handles everything else.

---

## The Problem — and Why CloudBlocks Exists

Raw Pulumi and Terraform give you every knob. That freedom is also the source of every misconfigured security rule, every missing NAT route, and every accidentally public subnet.

CloudBlocks makes **the architecture the product**. Network topology, subnet tiers, gateway placement, routing policy, and security posture are baked in — derived from OCI best practices — and are not configurable at call time. The user's job is to name things and pick a location. The block's job is everything else.

| With raw Pulumi / Terraform | With CloudBlocks |
|-----------------------------|-----------------|
| Define VCN, subnets, route tables, gateways, security lists — each resource individually | `Vcn(name="lab", compartment_id=cid)` — one call, full 4-tier architecture |
| Wire up NAT, Service GW, and Internet GW routes by hand | Routes are fixed by tier and generated automatically |
| Write security list rules for every subnet pair | Declare a role (`INTERNET_EDGE`, `APP_SERVER`, `DATABASE`) — rules are inferred |
| Risk misconfiguration on every project | Architecture is encoded once, reused everywhere, correct by construction |

> **The user's job is to name things and pick a location. The block's job is everything else.**

---

## Quick Start

```bash
git clone https://github.com/enricopesce/ociblocks.git
cd ociblocks
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Deploy a VCN

A single call provisions a complete 4-tier network: public, private, secure, and management subnets with Internet GW, NAT GW, Service GW, and all route tables wired correctly.

```python
from providers.oci.network import Vcn

vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

vcn.export()
```

That's it. Four subnets, three gateways, four route tables, security lists — all generated from one line.

### 2. Add a Compute Instance

Assign a role, and CloudBlocks infers the subnet tier, generates NSG rules, and sets up security lists automatically.

```python
from providers.oci.compute import ComputeInstance
from providers.oci.network import Vcn
from providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from providers.oci.roles import INTERNET_EDGE
from providers.oci.volume import VolumeSpec

vcn = Vcn(name="lab", compartment_id=compartment_id)

# Declare what this VM is — rules are generated from the role
web_nsg = Nsg(
    "web-server",
    role=INTERNET_EDGE,
    ports=[HTTP, HTTPS, SSH],
    vcn=vcn,
    compartment_id=compartment_id,
)

# nsg= infers subnet=SUBNET_PUBLIC from the INTERNET_EDGE role
web_server = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    nsg=web_nsg,
    volumes=[
        VolumeSpec(size_in_gbs=100, label="data"),
        VolumeSpec(size_in_gbs=200, label="logs", vpus_per_gb=VolumeSpec.PERF_LOW),
    ],
)

vcn.export()
web_server.export()
```

### 3. A Production Web + DB Stack

Three-tier architecture with a load balancer, web backends, and isolated database nodes. Role-based security generates all NSG and Security List rules from traffic relationship declarations.

```python
from providers.oci.compute import ComputeInstance
from providers.oci.network import Vcn
from providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE
from providers.oci.volume import VolumeSpec

vcn = Vcn(name="lab", compartment_id=compartment_id, cidr_block="10.0.0.0/16")

# Declare security posture via roles — no manual rule writing
lb_nsg  = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS, SSH], vcn=vcn, compartment_id=compartment_id)
web_nsg = Nsg("web-backend",   role=APP_SERVER,     vcn=vcn, compartment_id=compartment_id)
db_nsg  = Nsg("database",      role=DATABASE,        vcn=vcn, compartment_id=compartment_id)

# One line per hop generates bilateral NSG rules + Security List rules
lb_nsg.serves(web_nsg, port=app_port)   # LB → web: app port + SSH mgmt
web_nsg.serves(db_nsg, port=db_port)   # web → DB: db port + SSH mgmt

# Subnet tier inferred from role — no explicit subnet= parameter
load_balancer = ComputeInstance("load-balancer", compartment_id=compartment_id, vcn=vcn, nsg=lb_nsg)
web_backend_1 = ComputeInstance("web-backend-1", compartment_id=compartment_id, vcn=vcn, nsg=web_nsg)
web_backend_2 = ComputeInstance("web-backend-2", compartment_id=compartment_id, vcn=vcn, nsg=web_nsg)
db_1 = ComputeInstance("db-1", compartment_id=compartment_id, vcn=vcn, nsg=db_nsg,
                        volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)])
db_2 = ComputeInstance("db-2", compartment_id=compartment_id, vcn=vcn, nsg=db_nsg,
                        volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)])
```

Adding a third web backend? Attach `web_nsg` to a new `ComputeInstance`. Zero NSG changes required.

---

## Available Blocks

| Block | Cloud | What it encapsulates | Status |
|-------|-------|----------------------|--------|
| `Vcn` | OCI | 4-tier VCN (public/private/secure/management), all gateways, route tables, security lists | Stable |
| `OkeCluster` | OCI | Oracle Kubernetes Engine cluster, node pool, OCI_VCN_IP_NATIVE CNI, multi-AD node placement | Stable |
| `ComputeInstance` | OCI | VM instance, SSH key management, block volume attachments | Stable |
| `Bastion` | OCI | OCI Bastion service in the private subnet, ready for session-based access | Stable |
| `ScalableWorkload` | OCI | Load balancer (public) + instance pool (private) + CPU autoscaling | Stable |
| `Nsg` | OCI | Network Security Group with role-based rule generation and port constants | Stable |
| AWS provider | AWS | Full block library for AWS | Planned |
| GCP provider | GCP | Full block library for GCP | Planned |

---

## Architecture

CloudBlocks uses a strict three-layer design that separates cloud-neutral contracts from cloud-specific implementations:

```
src/
├── core/
│   ├── abstractions/        ← cloud-neutral interfaces (AbstractNetwork, AbstractScalableWorkload, …)
│   ├── base.py              ← BaseResource: naming, tagging, SSH key management
│   ├── naming.py            ← ResourceNamer: {stack}-{resource}-{suffix} convention
│   └── tagging.py           ← ResourceTagger: consistent tag sets across all resources
│
├── providers/
│   ├── oci/                 ← OCI implementation (canonical, use this for new code)
│   │   ├── network.py       ← Vcn, VcnRef
│   │   ├── kubernetes.py    ← OkeCluster
│   │   ├── compute.py       ← ComputeInstance
│   │   ├── bastion.py       ← Bastion
│   │   ├── autoscale.py     ← ScalableWorkload
│   │   ├── nsg.py           ← Nsg + port constants (SSH, HTTP, HTTPS, …)
│   │   └── roles.py         ← role constants (INTERNET_EDGE, APP_SERVER, DATABASE, …)
│   ├── aws/                 ← (future)
│   └── gcp/                 ← (future)
│
└── blocks/                  ← backward-compat re-exports only — no logic here
```

**The key design insight:** adding a new cloud provider means implementing the abstractions in `src/providers/<cloud>/` — zero changes to the user-facing API. An application written against `AbstractNetwork` works identically across OCI, AWS, and GCP once the provider implementations exist.

### VCN Network Topology

Every `Vcn` block creates a fixed, four-tier architecture regardless of CIDR size:

```
VCN (e.g. 10.0.0.0/16)
├── Private subnet    /17  (50%) — NAT GW + Service GW routes   [app workloads]
├── Secure subnet     /18  (25%) — Service GW only, no internet  [databases]
├── Public subnet     /19 (12.5%) — Internet GW route            [edge/LBs]
└── Management subnet /19 (12.5%) — Service GW only              [bastion/ops]
```

Subnet tier, gateway routing, and security posture are not configurable — they are the architecture.

---

## Design Principles

- **Minimal user input** — blocks accept only a name, compartment, and network reference. Every value that can be derived, computed, or defaulted securely is. Exposing unnecessary parameters is a design defect, not a feature.

- **Architecture as the product** — network topology, routing policy, gateway placement, and security posture are fixed by design. The block encodes the correct architecture; the user just names things and picks a location.

- **Multi-cloud by design** — cloud-neutral abstractions in `src/core/abstractions/` define what a network or workload is. OCI, AWS, and GCP are implementations, not forks. The user-facing API is the same regardless of the target cloud.

---

## Installation and Setup

### Prerequisites

- Python 3.8 or later
- [Pulumi CLI](https://www.pulumi.com/docs/get-started/install/) installed and on your `PATH`
- OCI credentials configured at `~/.oci/config` (see [OCI SDK and CLI Configuration](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm))

### Install

```bash
git clone https://github.com/enricopesce/ociblocks.git
cd ociblocks
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure Pulumi OCI provider

```bash
pulumi config set oci:tenancyOcid   <tenancy-ocid>
pulumi config set oci:userOcid      <user-ocid>
pulumi config set oci:fingerprint   <key-fingerprint>
pulumi config set oci:privateKeyPath ~/.oci/oci_api_key.pem
pulumi config set oci:region        <region>          # e.g. eu-frankfurt-1
```

### Run an example

```bash
cd examples/vcn
pulumi stack init dev
pulumi config set compartment_ocid <compartment-ocid>
pulumi up
```

---

## Examples

Each example is a self-contained Pulumi stack in `examples/`:

| Example | Description |
|---------|-------------|
| [`vcn`](examples/vcn/) | Minimal VCN deployment — 4-tier network, all gateways. Outputs consumed by `import-vcn`. |
| [`compute`](examples/compute/) | VCN + internet-facing VM with role-based NSG, block volumes. |
| [`oke`](examples/oke/) | VCN + Oracle Kubernetes Engine cluster with configurable node pool. |
| [`bastion`](examples/bastion/) | VCN + OCI Bastion service for secure private-subnet access. |
| [`autoscale`](examples/autoscale/) | VCN + load balancer + auto-scaling instance pool with CPU policies. |
| [`web-db`](examples/web-db/) | Three-tier web+DB stack: LB (public) → app servers (private) → DB nodes (secure). |
| [`secure-vcn`](examples/secure-vcn/) | VCN with VCN flow log capture enabled for network audit. |
| [`import-vcn`](examples/import-vcn/) | Consume a VCN owned by a separate stack via `VcnRef.from_stack_reference()`. |

---

## Contributing

**We're building the definitive opinionated infrastructure as code library for Oracle Cloud Infrastructure — and extending it to AWS and GCP. If you believe infrastructure should be correct by default, not by careful configuration, we want to work with you.**

CloudBlocks is early-stage and actively looking for contributors who care about platform engineering done right. Every block you contribute saves the next team from a week of reading cloud documentation and another week of debugging security list rules.

### Who we need

- **Python / Pulumi developers** — extend existing blocks, add tests, improve type coverage
- **OCI experts** — validate reference architectures, add missing OCI-native services
- **AWS / GCP engineers** — implement the AWS and GCP provider layers (the abstraction interfaces are already defined)
- **Platform engineers** — real-world usage feedback, example stacks, battle-testing
- **Documentation writers** — examples, tutorials, API reference improvements

### How to start

1. Browse [issues labeled `good-first-issue`](https://github.com/enricopesce/ociblocks/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue) for a well-scoped starting point.
2. Read `CLAUDE.md` for architecture rules and coding standards — these are enforced, not suggestions.
3. Look at an existing block (e.g. `src/providers/oci/bastion.py`) as a template: minimal constructor, full docstrings, no exposed low-level parameters.
4. Open an issue before starting large work so we can align on design before you invest time.

### Development workflow

```bash
source .venv/bin/activate

# Lint and format
ruff check src/ tests/ --fix
ruff format src/ tests/

# Type checking
pyright

# Tests with coverage
pytest

# Full quality gate (run before opening a PR)
ruff check src/ tests/ && ruff format --check src/ tests/ && pyright && pytest
```

All four checks must pass. PRs that fail the quality gate will not be merged.

---

## Roadmap

- [x] OCI core blocks — VCN, OKE, Compute, Bastion, ScalableWorkload
- [x] NSG support with role constants and port constants
- [x] 4-tier network architecture with fixed routing
- [x] Security list rule helpers and `INTERNET` constant
- [x] `VcnRef` for cross-stack VCN references
- [ ] AWS provider — implement `AbstractNetwork`, `AbstractScalableWorkload`, etc. for AWS
- [ ] GCP provider — same abstraction layer for GCP
- [ ] Azure provider
- [ ] CloudBlocks CLI tool for stack management
- [ ] MkDocs documentation site (in progress — `mkdocs.yml` present)
- [ ] Community block registry

---

## License and Acknowledgements

Released under the terms described in [LICENSE](LICENSE).

CloudBlocks is built on [Pulumi](https://www.pulumi.com/) and the [pulumi-oci](https://github.com/pulumi/pulumi-oci) provider. The design philosophy — making the architecture the product — is inspired by the principle that correct infrastructure should not require expert configuration on every deployment.
