# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Rules

- **High-level constructs, not low-level wrappers**: CloudSpells encodes fixed, opinionated reference architectures. It is not a Terraform replacement or a thin cloud-API layer — it is the opposite. Architecture decisions (topology, routing, security posture) are baked in, not left to the caller.
- **Minimal user input**: blocks must require only essential identifiers (name, compartment/project, network). Every value that can be derived, computed, or defaulted securely must be. Exposing unnecessary parameters — especially ones that just pass through underlying provider options — is a design defect.
- **Full documentation required**: every public class, method, and module must have a Google-style docstring with `Args:`, `Returns:`, `Raises:`, `Attributes:`, and `Example:` as applicable. No undocumented public API is acceptable.

## Design Philosophy

### What CloudSpells is — and is not

**CloudSpells is not a Terraform replacement or a low-level cloud-API wrapper.** It is the opposite: a collection of opinionated, high-level constructs that encode proven reference architectures as immutable, bulletproof building blocks.

CloudSpells started with OCI support and is designed from the ground up to be multi-cloud. The `src/core/abstractions/` layer defines cloud-neutral interfaces; `src/providers/<cloud>/` contains provider-specific implementations. Adding a new provider means implementing those interfaces — not changing the user-facing API.

- Terraform (and raw Pulumi provider resources) give you every knob and let you wire everything yourself. That freedom is also the source of every misconfigured security rule, missing route, and open subnet.
- CloudSpells makes the architecture the product. Network topology, subnet tiers, routing policy, gateway placement, and security posture are fixed by design — derived from cloud provider best practices — and are not negotiable at call time.

**The user's job is to name things and pick a location. The block's job is everything else.**

### Guiding rules

**Blocks must require minimal user input.** A block encapsulates a complete, well-architected design. The user supplies only essential identifiers (name, compartment/project, network) and the block handles all internal wiring. Sensible, secure defaults are never left to the caller.

When adding or modifying a block, ask: *can the user deploy this correctly with fewer parameters?* If a value can be derived, computed, or defaulted securely, it must be. Exposing unnecessary knobs is a design defect.

**Never expose a parameter just because the underlying provider resource accepts it.** Parameters that exist only to pass through a low-level option belong in raw Pulumi/Terraform, not here.

## Project Overview

CloudSpells is a Python-based infrastructure-as-code framework built on Pulumi that provides high-level, opinionated building blocks for cloud infrastructure. It is multi-cloud by design: a cloud-neutral abstraction layer sits above provider-specific implementations, starting with OCI. It extends Pulumi's `ComponentResource` model to encapsulate entire reference architectures behind minimal interfaces.

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

### Three-layer structure

```
src/core/abstractions/     — cloud-neutral interfaces (AbstractNetwork, AbstractScalableWorkload, …)
src/providers/<cloud>/     — provider implementations (oci/ today; future: aws/, gcp/, …)
src/blocks/                — backward-compat re-export shims only (do not add logic here)
```

New provider = implement the abstractions under a new `src/providers/<cloud>/` directory. No changes to core or blocks needed.

**New code imports from `providers.oci` directly.** `src/blocks/` exists only so old imports keep working.

### Core (`src/core/`)

- **`base.py`**: `BaseResource` — all blocks inherit this. Standardised naming, tagging, SSH key management.
- **`naming.py`**: `ResourceNamer` — names follow `{stack}-{resource}-{suffix}`.
- **`abstractions/`**: Cloud-neutral dataclasses and ABCs (`LoadBalancerConfig`, `MetricScalingPolicy`, `AbstractScalableWorkload`, …). Write provider-agnostic typed functions against these.

### OCI blocks (`src/providers/oci/`)

- **`network.py`** — `Vcn`: 4-tier subnet architecture, all gateways, fixed routing per tier.
  - Public (12.5%) → Internet GW. Private (50%) → NAT + Service GW. Secure (25%) → Service GW only. Management (12.5%) → Service GW only.
  - CIDR split: private=prefix+1, secure=prefix+2, public=prefix+3, management=prefix+3.
  - `VcnRef`: read-only handle to a VCN owned by another stack. All service blocks accept `Vcn | VcnRef`.
- **`kubernetes.py`** — `OkeCluster`: BASIC_CLUSTER, OCI_VCN_IP_NATIVE CNI, fixed pod/service CIDRs, nodes spread across all ADs.
- **`compute.py`** — `ComputeInstance`: single instance, auto SSH keys, block volumes, any subnet tier.
- **`bastion.py`** — `Bastion`: OCI Bastion service in the private subnet.
- **`autoscale.py`** — `ScalableWorkload`: LB in public subnet, instance pool in private, CPU autoscaling by default.
- **`nsg.py`** — `Nsg` + port constants (`SSH`, `HTTP`, `HTTPS`, …) for NSG-based security.
- **`roles.py`** — Semantic role constants (`APP_SERVER`, `DATABASE`, `INTERNET_EDGE`, …).

### Key pattern: VCN lazy initialisation

Services call `vcn.add_security_list_rules()` to accumulate rules, then `vcn.finalize_network()` to materialise security lists and subnets. `finalize_network()` is idempotent — only the first call has effect; service blocks call it automatically.

Subnet CIDR accessors return `pulumi.Input[str]` (not `str`) so they work for both `Vcn` and `VcnRef`.

### Testing

`set_mocks()` **must** be called before importing any infrastructure module:

```python
from tests.mocks import set_mocks
set_mocks()

from providers.oci.network import Vcn  # import after mocks
```

`tests/mocks.py` intercepts OCI provider calls (`get_services`, `get_images`, `get_availability_domains`). `src/` is on `sys.path` in every test file.

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

Example usage is demonstrated in `examples/` (one directory per block).