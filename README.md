# CloudSpells — High-Level Infrastructure Spells for OCI

**Stop configuring infrastructure. Start deploying architectures.**

[![CI](https://github.com/enricopesce/cloudspells/actions/workflows/ci.yml/badge.svg)](https://github.com/enricopesce/cloudspells/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/enricopesce/cloudspells)](LICENSE)
[![Pulumi 3.x](https://img.shields.io/badge/pulumi-3.x-blueviolet)](https://www.pulumi.com/)
[![OCI](https://img.shields.io/badge/cloud-OCI-red)](https://www.oracle.com/cloud/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/enricopesce/cloudspells/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue)

> **Alpha — API is stabilising; expect changes between minor versions.**

CloudSpells is a Python-based infrastructure as code framework built on [Pulumi](https://www.pulumi.com/) that packages proven Oracle Cloud Infrastructure reference architectures as minimal, opinionated spells — you name things, the spell handles everything else.

---

## The Problem — and Why CloudSpells Exists

Raw Pulumi and Terraform give you every knob. That freedom is also the source of every misconfigured security rule, every missing NAT route, and every accidentally public subnet.

CloudSpells makes **the architecture the product**. Network topology, subnet tiers, gateway placement, routing policy, and security posture are baked in — derived from OCI best practices — and are not configurable at call time. The user's job is to name things and pick a location. The spell's job is everything else.

| With raw Pulumi / Terraform | With CloudSpells |
|-----------------------------|-----------------|
| Define VCN, subnets, route tables, gateways, security lists — each resource individually | `Vcn(name="lab", compartment_id=cid)` — one call, full 4-tier architecture |
| Wire up NAT, Service GW, and Internet GW routes by hand | Routes are fixed by tier and generated automatically |
| Write security list rules for every subnet pair | Declare a role (`INTERNET_EDGE`, `APP_SERVER`, `DATABASE`) — rules are inferred |
| Risk misconfiguration on every project | Architecture is encoded once, reused everywhere, correct by construction |

> **The user's job is to name things and pick a location. The spell's job is everything else.**

---

## Quick Start

### Install

CloudSpells is split into two independently-installable packages:

```bash
pip install cloudspells-core   # cloud-neutral abstractions and utilities
pip install cloudspells-oci    # OCI spells (installs cloudspells-core automatically)
```

For local development from source:

```bash
git clone https://github.com/enricopesce/cloudspells.git
cd cloudspells
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Deploy a VCN

A single call provisions a complete 4-tier network: public, private, secure, and management subnets with Internet GW, NAT GW, Service GW, and all route tables wired correctly.

```python
from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn

cfg = Config()
vcn = Vcn(
    name="lab",
    compartment_id=cfg.require("compartment_ocid"),
)

vcn.export()
```

Four subnets, three gateways, four route tables, security lists — all generated from one line.

### 2. Add a Compute Instance

Assign a role, and CloudSpells infers the subnet tier, generates NSG rules, and sets up security lists automatically.

```python
from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from cloudspells.providers.oci.roles import INTERNET_EDGE
from cloudspells.providers.oci.volume import VolumeSpec

cfg = Config()
compartment_id = cfg.require("compartment_ocid")
ssh_public_key = cfg.require("ssh_public_key")

vcn = Vcn(name="lab", compartment_id=compartment_id)

# Declare what this VM is — rules are generated from the role
web_nsg = Nsg(
    "web-server",
    role=INTERNET_EDGE,
    ports=[HTTP, HTTPS, SSH],
    vcn=vcn,
    compartment_id=compartment_id,
)

# nsg= carries the VCN and infers public placement from INTERNET_EDGE
web_server = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    image_id="ocid1.image.oc1..<your-image-ocid>",
    nsg=web_nsg,
    ssh_public_key=ssh_public_key,
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
from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, POSTGRES, Nsg
from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE
from cloudspells.providers.oci.volume import VolumeSpec

cfg = Config()
compartment_id = cfg.require("compartment_ocid")
ssh_public_key = cfg.require("ssh_public_key")
image = cfg.require("instance_image_ocid")

vcn = Vcn(name="lab", compartment_id=compartment_id, cidr_block="10.0.0.0/16")

# Declare security posture via roles — no manual rule writing
lb_nsg  = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS], vcn=vcn, compartment_id=compartment_id)
web_nsg = Nsg("web-backend",   role=APP_SERVER,     vcn=vcn, compartment_id=compartment_id)
db_nsg  = Nsg("database",      role=DATABASE,        vcn=vcn, compartment_id=compartment_id)

# One call per hop generates bilateral NSG rules + Security List rules
lb_nsg.serves(web_nsg, port=HTTP)      # LB → web: HTTP + SSH mgmt
web_nsg.serves(db_nsg, port=POSTGRES)  # web → DB: Postgres + SSH mgmt

# VCN and subnet tier are inferred from the role-bearing NSG
load_balancer = ComputeInstance(
    "load-balancer", compartment_id=compartment_id, image_id=image,
    ssh_public_key=ssh_public_key, nsg=lb_nsg,
)
web_backend_1 = ComputeInstance(
    "web-backend-1", compartment_id=compartment_id, image_id=image,
    ssh_public_key=ssh_public_key, nsg=web_nsg,
)
web_backend_2 = ComputeInstance(
    "web-backend-2", compartment_id=compartment_id, image_id=image,
    ssh_public_key=ssh_public_key, nsg=web_nsg,
)
db_1 = ComputeInstance(
    "db-1", compartment_id=compartment_id, image_id=image,
    ssh_public_key=ssh_public_key, nsg=db_nsg,
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)
db_2 = ComputeInstance(
    "db-2", compartment_id=compartment_id, image_id=image,
    ssh_public_key=ssh_public_key, nsg=db_nsg,
    volumes=[VolumeSpec(size_in_gbs=200, label="data", vpus_per_gb=VolumeSpec.PERF_HIGH)],
)
```

Adding a third web backend? Attach `web_nsg` to a new `ComputeInstance`. Zero NSG changes required.

---

## Available Spells

| Spell | Cloud | What it encapsulates | Status |
|-------|-------|----------------------|--------|
| `Vcn` | OCI | 4-tier VCN (public/private/secure/management), all gateways, route tables, security lists | Alpha |
| `OkeCluster` | OCI | Oracle Kubernetes Engine cluster, node pool, OCI_VCN_IP_NATIVE CNI, multi-AD node placement | Alpha |
| `ComputeInstance` | OCI | VM instance attached through a role-bearing NSG, SSH key management, block volume attachments | Alpha |
| `Bastion` | OCI | OCI Bastion service in the private subnet, ready for session-based access | Alpha |
| `ScalableWorkload` | OCI | Load balancer (public) + instance pool (private) + CPU/schedule autoscaling | Alpha |
| `LoadBalancer` | OCI | Flexible-shape public load balancer with HTTP/HTTPS listeners and health checks | Alpha |
| `InternalLoadBalancer` | OCI | Private load balancer in the secure subnet for internal service-to-service traffic | Alpha |
| `Nsg` | OCI | Network Security Group with role-based rule generation and port constants | Alpha |
| `VcnFlowLogs` | OCI | VCN flow log capture for network audit and compliance | Alpha |
| `ObjectStorageBucket` | OCI | Standard object storage bucket with lifecycle and versioning defaults | Alpha |
| `BackupBucket` | OCI | Versioned bucket with permanent-delete retention for backups | Alpha |
| `DataLakeBucket` | OCI | Archive-tier bucket optimised for large-scale data lake storage | Alpha |
| `ArchiveBucket` | OCI | Deep-archive bucket for long-term cold storage | Alpha |
| `StaticWebsiteBucket` | OCI | Public-read bucket with static website hosting enabled | Alpha |
| `ComputeInstancePrincipal` | OCI | Dynamic group + policy granting compute instances in a compartment access to caller-specified OCI services (e.g. Object Storage, Vault Secrets) | Alpha |
| `OkeNodePrincipal` | OCI | Dynamic group + policy granting OKE node pool instances the full permission set required for cluster operation | Alpha |
| `CompartmentAdminGroup` | OCI | IAM group + `manage all-resources` policy delegating compartment administration to a human operator group | Alpha |
| AWS provider | AWS | Full spell library for AWS | Planned |
| GCP provider | GCP | Full spell library for GCP | Planned |

---

## Architecture

CloudSpells uses a strict three-layer design that separates cloud-neutral contracts from cloud-specific implementations. The codebase is published as two independent packages:

```
packages/
├── cloudspells-core/            ← pip install cloudspells-core
│   └── src/cloudspells/
│       └── core/
│           ├── abstractions/    ← cloud-neutral interfaces (AbstractNetwork, AbstractScalableWorkload, …)
│           ├── base.py          ← BaseResource: naming, tagging, SSH key management
│           ├── config.py        ← Config: zero-Pulumi-dependency config wrapper
│           ├── naming.py        ← ResourceNamer: {stack}-{resource}-{suffix} convention
│           ├── ports.py         ← TCP/UDP port constants (HTTP, HTTPS, SSH, …)
│           └── tagging.py       ← ResourceTagger: consistent tag sets across all resources
│
└── cloudspells-oci/             ← pip install cloudspells-oci
    └── src/cloudspells/
        └── providers/
            └── oci/             ← OCI implementation (canonical, use this for new code)
                ├── network.py           ← Vcn, VcnRef
                ├── kubernetes.py        ← OkeCluster
                ├── compute.py           ← ComputeInstance
                ├── bastion.py           ← Bastion
                ├── autoscale.py         ← ScalableWorkload
                ├── loadbalancer.py      ← LoadBalancer, InternalLoadBalancer
                ├── nsg.py               ← Nsg + role-based rule generation
                ├── roles.py             ← role constants (INTERNET_EDGE, APP_SERVER, DATABASE, …)
                ├── storage.py           ← ObjectStorageBucket, BackupBucket, DataLakeBucket, ArchiveBucket, StaticWebsiteBucket
                ├── volume.py            ← VolumeSpec
                ├── network_logging.py   ← VcnFlowLogs
                └── iam.py               ← ComputeInstancePrincipal, OkeNodePrincipal, CompartmentAdminGroup
```

**The key design insight:** adding a new cloud provider means implementing the abstractions under `packages/cloudspells-<cloud>/src/cloudspells/providers/<cloud>/` — zero changes to the user-facing API. An application written against `AbstractNetwork` works identically across OCI, AWS, and GCP once the provider implementations exist.

### VCN Network Topology

Every `Vcn` spell creates a fixed, four-tier architecture regardless of CIDR size:

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

- **Minimal user input** — spells accept only a name, compartment, and network reference. Every value that can be derived, computed, or defaulted securely is. Exposing unnecessary parameters is a design defect, not a feature.

- **Architecture as the product** — network topology, routing policy, gateway placement, and security posture are fixed by design. The spell encodes the correct architecture; the user just names things and picks a location.

- **Multi-cloud by design** — cloud-neutral abstractions in `cloudspells.core.abstractions` define what a network or workload is. OCI, AWS, and GCP are implementations, not forks. The user-facing API is the same regardless of the target cloud.

---

## Installation and Setup

### Prerequisites

- Python 3.8 or later
- [Pulumi CLI](https://www.pulumi.com/docs/get-started/install/) installed and on your `PATH`
- OCI credentials configured at `~/.oci/config` (see [OCI SDK and CLI Configuration](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm))

### Install

```bash
pip install cloudspells-oci
```

For local development from source:

```bash
git clone https://github.com/enricopesce/cloudspells.git
cd cloudspells
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
| [`loadbalancer`](examples/loadbalancer/) | VCN + HTTPS load balancer with HTTP→HTTPS redirect and health checks. |
| [`storage`](examples/storage/) | Backup bucket + data lake bucket with lifecycle and versioning defaults. |
| [`web-db`](examples/web-db/) | Three-tier web+DB stack: LB (public) → app servers (private) → DB nodes (secure). |
| [`iam`](examples/iam/) | `ComputeInstancePrincipal` + `OkeNodePrincipal` + `CompartmentAdminGroup` — instance principals and compartment admin group; `tenancy_ocid` config key. |
| [`secure-vcn`](examples/secure-vcn/) | VCN with flow logs, four-tier NSGs, management-tier SSH controls, and zero-credential app tier via `ComputeInstancePrincipal`. |
| [`import-vcn`](examples/import-vcn/) | Consume a VCN owned by a separate stack via `VcnRef.from_stack_reference()`. |

---

## Contributing

CloudSpells is actively looking for contributors. See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for the full guide — project philosophy, local setup, quality gate, spell authoring steps, and PR guidelines.

---

## Roadmap

- [x] OCI core spells — VCN, OKE, Compute, Bastion, ScalableWorkload
- [x] NSG support with role constants and port constants
- [x] 4-tier network architecture with fixed routing
- [x] Security list rule helpers and `INTERNET` constant
- [x] `VcnRef` for cross-stack VCN references
- [x] `VcnFlowLogs` for network audit and compliance
- [x] `LoadBalancer` and `InternalLoadBalancer` spells
- [x] Object storage spells (ObjectStorageBucket, BackupBucket, DataLakeBucket, ArchiveBucket, StaticWebsiteBucket)
- [x] Split into `cloudspells-core` and `cloudspells-oci` packages for independent versioning
- [x] PyPI publishing via GitHub Actions
- [ ] AWS provider — implement `AbstractNetwork`, `AbstractScalableWorkload`, etc. for AWS
- [ ] GCP provider — same abstraction layer for GCP
- [ ] Azure provider
- [ ] CloudSpells CLI tool for stack management

---

## License and Acknowledgements

Released under the terms described in [LICENSE](LICENSE).

CloudSpells is built on [Pulumi](https://www.pulumi.com/) and the [pulumi-oci](https://github.com/pulumi/pulumi-oci) provider. The design philosophy — making the architecture the product — is inspired by the principle that correct infrastructure should not require expert configuration on every deployment.
