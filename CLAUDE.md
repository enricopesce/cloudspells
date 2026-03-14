# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Rules

- **Minimal user input**: blocks must require only essential identifiers (name, compartment, VCN). Every value that can be derived, computed, or defaulted securely must be. Exposing unnecessary parameters is a design defect.
- **Full documentation required**: every public class, method, and module must have a Google-style docstring with `Args:`, `Returns:`, `Raises:`, `Attributes:`, and `Example:` as applicable. No undocumented public API is acceptable.

## Design Philosophy

**Blocks must require minimal user input.** A block encapsulates a complete, well-architected design based on certified OCI reference architectures. The user supplies only the essential identifiers (compartment, VCN, name) and the block handles all internal wiring: security rules, routing, subnet placement, gateway configuration, and resource relationships. Sensible, secure defaults are never left to the caller.

When adding or modifying a block, ask: *can the user deploy this correctly with fewer parameters?* If a value can be derived, computed, or defaulted securely, it must be. Exposing unnecessary knobs is a design defect.

## Project Overview

OCIBlocks is a Python-based infrastructure-as-code framework built on Pulumi that provides high-level building blocks for Oracle Cloud Infrastructure (OCI). It extends Pulumi's `ComponentResource` model to create modular, reusable abstractions that encapsulate multiple OCI resources into simplified interfaces.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Type checking
pyright

# Lint (ruff — reports errors)
ruff check src/ tests/

# Lint with auto-fix
ruff check src/ tests/ --fix

# Format (ruff)
ruff format src/ tests/

# Format check only (no changes)
ruff format --check src/ tests/

# Run all tests with coverage
pytest

# Run a single test file
pytest tests/test_vcn.py

# Run a single test case
pytest tests/test_vcn.py::TestVcn::test_vcn_creates_base_resources

# Dead code detection
vulture src/ --min-confidence 80

# Full quality gate (run before committing)
ruff check src/ tests/ && ruff format --check src/ tests/ && pyright && pytest

# Preview infrastructure changes (run from an example directory)
cd examples/autoscale && pulumi preview

# Deploy infrastructure
cd examples/autoscale && pulumi up

# Destroy infrastructure
cd examples/autoscale && pulumi destroy
```

Always activate the virtualenv before running tests or pyright: `source .venv/bin/activate`.

## Architecture

### Core Framework (`src/core/`)

- **`base.py`**: `BaseResource` class extends `pulumi.ComponentResource`. All building blocks inherit from this. Provides standardized naming, tagging, and resource management.
- **`naming.py`**: `ResourceNamer` creates standardized resource names (`{stack-name}-{resource-name}-{suffix}`) and DNS labels.
- **`tagging.py`**: `ResourceTagger` creates freeform tags with consistent metadata.
- **`helper.py`**: Utility functions for subnet CIDR calculation, random word generation, and availability domain mapping.

### Building Blocks (`src/blocks/`)

- **VCN (`vcn/network.py`)**: Virtual Cloud Network with Internet/NAT/Service Gateways and a 4-tier subnet architecture:
  - **Public tier**: Load balancers and bastion hosts. Route: Internet Gateway.
  - **Private tier**: App servers, K8s nodes, instance pools. Route: NAT Gateway + Service Gateway (internet-capable outbound).
  - **Secure tier**: Databases, secrets, audit stores. Route: Service Gateway **only** — no internet path at all, not even outbound NAT.
  - **Management tier**: Monitoring agents, bastion service, VPN/FastConnect endpoints, internal tooling. Route: Service Gateway only — same isolation as secure.
  - VCN CIDR is split proportionally: private=50% (prefix+1), secure=25% (prefix+2), public=12.5% (prefix+3), management=12.5% (prefix+3). Index order: [public, private, secure, management].
- **VcnRef (`vcn/network.py`)**: Read-only wrapper around a VCN deployed in another Pulumi stack. Use `VcnRef.from_stack_reference(stack_name)` to construct. It is a no-op for `add_security_list_rules`/`finalize_network`. All service blocks (OKE, Compute, ScalableWorkload) accept `Vcn | VcnRef`.
- **OKE (`oke/cluster.py`)**: Oracle Kubernetes Engine cluster with node pools and security integration.
- **Compute (`compute/instance.py`)**: Compute instances with automated SSH key generation and block volumes. Supports public, private, secure, and management subnet tiers.
- **Bastion (`compute/bastion.py`)**: OCI Bastion service resource for secure shell access to private resources.
- **ScalableWorkload (`autoscale/workload.py`)**: Horizontally-scalable compute with OCI Load Balancer, Instance Configuration, Instance Pool, and metric/schedule-based Autoscaling Configuration. Load balancer goes to the public subnet; instance pool to the private subnet.

### Key Pattern: Lazy Initialization

VCN uses lazy initialization for network finalization:

```python
# 1. Create VCN (no security lists or subnets yet)
vcn = Vcn(name="lab", compartment_id=compartment_id, stack_name=stack_name)

# 2. Services add their security rules
compute_instance = ComputeInstance(name="web", vcn=vcn, ...)  # Calls vcn.add_security_list_rules()

# 3. finalize_network() is called automatically by the service
# This creates security lists and subnets with all accumulated rules
```

Services (OKE, Compute, ScalableWorkload) call `vcn.add_security_list_rules()` to add rules, then call `vcn.finalize_network()` which creates the actual security lists and subnets. `finalize_network()` is idempotent — only the first call has effect.

Subnet CIDR accessors (`get_public_subnet_cidr()`, `get_private_subnet_cidr()`, `get_secure_subnet_cidr()`, `get_management_subnet_cidr()`) return `pulumi.Input[str]` — not plain `str` — so they work for both `Vcn` and `VcnRef`.

### Inheritance Hierarchy

```
pulumi.ComponentResource
└── BaseResource (src/core/base.py)
    ├── Vcn (src/blocks/vcn/network.py)
    ├── OkeCluster (src/blocks/oke/cluster.py)
    ├── ComputeInstance (src/blocks/compute/instance.py)
    ├── Bastion (src/blocks/compute/bastion.py)
    └── ScalableWorkload (src/blocks/autoscale/workload.py)
```

### Testing

Tests use Pulumi's mock framework. **Critical ordering requirement**: `set_mocks()` must be called before importing any infrastructure modules. All test files follow this pattern:

```python
from tests.mocks import set_mocks
set_mocks()  # Must come before infrastructure imports

from blocks.vcn.network import Vcn  # Import after mocks
```

The mock in `tests/mocks.py` intercepts OCI provider calls (`get_services`, `get_images`, `get_availability_domains`) and resource creation. Tests that use `@pulumi.runtime.test` are async and return a `pulumi.Output`; tests without the decorator run synchronously.

The `src/` directory is added to `sys.path` at the top of each test file so modules resolve correctly without a package install.

### Documentation Conventions

- **Google-style docstrings** throughout (`Args:`, `Returns:`, `Raises:`, `Example:`)
- Module-level docstrings on every file describing purpose and exports
- `__all__` defined in every `__init__.py`
- Class docstrings include `Attributes:` section for IDE hover support
- Private helpers have docstrings describing what they do and when to call them

#### Docstring markup — one format for VS Code and mkdocstrings

Use **pure Markdown** inside every docstring. This is the only syntax that renders correctly in both VS Code (Pylance hover) and mkdocstrings without any translation layer.

| Use | Avoid |
|-----|-------|
| `` `value` `` — inline code | ` ``value`` ` — RST double-backtick |
| ` ```\nblock\n``` ` — fenced code block | `pattern::` + indented block — RST code block |
| plain prose | `*italic*` for emphasis — RST italic renders as literal asterisks |

```python
# Correct
def create_resource_name(self, suffix: str) -> str:
    """Build a name following the pattern `{stack}-{resource}-{suffix}`.

    Args:
        suffix: Resource type suffix (e.g. `"vcn"`, `"igw"`).

    Returns:
        Fully-qualified resource name string.

    Example:
        >>> namer = ResourceNamer("prod", "lab")
        >>> namer.create_resource_name("vcn")
        'prod-lab-vcn'
    """
```

## Dependencies

- **Pulumi**: 3.204.0
- **pulumi_oci**: 3.9.0
- **Python**: 3.8+
- **Type checking**: pyright
- **Testing**: pytest

## Configuration

Infrastructure configuration is managed through Pulumi config (`Pulumi.<stack>.yaml`). Required config values:
- `compartment_ocid`: OCI compartment OCID
- `vcn_cidr_block`: CIDR block for the VCN

Example usage is demonstrated in `examples/__main__.py`.