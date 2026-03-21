# Contributing to CloudSpells

Thank you for your interest in contributing to CloudSpells. This document explains how to set up a development environment, how contributions are evaluated, and what we are — and are not — looking for.

---

## Project philosophy — read this first

CloudSpells is **not** a Terraform replacement. It is not a thin wrapper around OCI APIs. It is the opposite: a collection of opinionated, high-level constructs that encode proven reference architectures as immutable spells.

When Terraform (or raw Pulumi resources) give you every knob, the freedom to misconfigure is just as available as the freedom to configure correctly. CloudSpells removes that freedom deliberately. Network topology, subnet tiers, routing policy, gateway placement, and security posture are baked in — derived from OCI best practices — and are not negotiable at call time.

**The user's job is to name things and pick a location. The spell's job is everything else.**

### What this means for contributors

Every proposed parameter must earn its place. Before adding a parameter, ask:

- Can this value be derived from something the user already provides?
- Can a secure, correct default be chosen?
- Does exposing this parameter give the caller a way to produce a broken or insecure configuration?

If a value can be derived, computed, or defaulted securely, it **must** be. Parameters that exist only to pass through an underlying OCI resource option belong in raw Pulumi — not here.

**Thin wrappers and pass-through parameters will not be merged.** This is not a quality bar; it is a design constraint.

---

## Prerequisites

- **Python 3.8 or later**
- **Pulumi CLI** — [install guide](https://www.pulumi.com/docs/install/)
- **OCI account** — required only for live end-to-end tests against real infrastructure (not needed for the unit test suite)
- A working virtualenv — the project uses `.venv/` by convention

---

## Local setup

```bash
# 1. Clone the repository
git clone https://github.com/enricopesce/cloudspells.git
cd cloudspells

# 2. Create and activate a virtualenv
python -m venv .venv
source .venv/bin/activate

# 3. Install all dependencies (including dev tools)
pip install -r requirements.txt
```

---

## Quality gate

Every pull request must pass the full quality gate before review. Run it locally before pushing:

```bash
source .venv/bin/activate
make
```

`make` with no arguments runs the full gate — lint, format check, type check, and tests — identical to what CI runs on every push.

### All make targets

| Target | What it does |
|--------|--------------|
| `make` / `make check` | Full quality gate (lint + format-check + typecheck + test) |
| `make lint` | `ruff check` — report errors only |
| `make lint-fix` | `ruff check --fix` — auto-fix where possible |
| `make format` | `ruff format` — apply formatting |
| `make format-check` | `ruff format --check` — verify formatting without changes |
| `make typecheck` | `pyright` |
| `make test` | `pytest` with coverage |
| `make deadcode` | `vulture` dead-code scan (informational) |

The Makefile invokes tools from `.venv/bin/` directly, so the virtualenv must be active.

---

## Running tests

```bash
source .venv/bin/activate
pytest
```

Run a single file:

```bash
pytest tests/test_vcn.py
```

Run a single test case:

```bash
pytest tests/test_vcn.py::TestVcn::test_vcn_creates_base_resources
```

### Testing conventions

`set_mocks()` **must** be called before importing any infrastructure module. This intercepts OCI provider calls so tests run without real OCI credentials:

```python
from tests.mocks import set_mocks
set_mocks()

from providers.oci.network import Vcn  # import after mocks are set
```

`src/` is on `sys.path` in every test file. Import from `providers.oci.*` directly — not from `blocks.*`.

---

## How to add a new spell

Adding a spell requires changes in four places. Follow all four steps.

### 1. Define the abstraction

Add a cloud-neutral interface (dataclass or ABC) in `src/core/abstractions/`. This is the contract that all provider implementations must satisfy.

```python
# src/core/abstractions/my_spell.py
from abc import ABC, abstractmethod

class AbstractMySpell(ABC):
    """Cloud-neutral interface for MySpell.

    Attributes:
        name: Logical name of the spell.
    """

    @abstractmethod
    def some_method(self) -> None:
        """Do the thing."""
        ...
```

Export it from `src/core/abstractions/__init__.py` and add it to `__all__`.

### 2. Implement the OCI provider

Add the implementation in `src/providers/oci/my_spell.py`. Inherit from both the abstraction and `BaseResource`:

```python
# src/providers/oci/my_spell.py
from core.base import BaseResource
from core.abstractions.my_spell import AbstractMySpell
from providers.oci.network import Vcn, VcnRef

class MySpell(BaseResource, AbstractMySpell):
    """OCI implementation of MySpell.

    Args:
        name: Logical name used for all child resources.
        compartment_id: OCID of the target compartment.
        vcn: A `Vcn` or `VcnRef` instance providing network context.
        stack_name: Pulumi stack name for resource naming.
        opts: Optional Pulumi resource options.

    Attributes:
        ...

    Example:
        ```python
        spell = MySpell(
            name="example",
            compartment_id=compartment_id,
            vcn=vcn,
            stack_name=stack_name,
        )
        ```
    """
```

Export it from `src/providers/oci/__init__.py`.

### 3. Add a backward-compat shim

Add a re-export shim in `src/blocks/` so that any existing code using the old import path keeps working. **Do not add logic here** — only re-exports.

```python
# src/blocks/my_spell.py
from providers.oci.my_spell import MySpell

__all__ = ["MySpell"]
```

### 4. Write tests

Add `tests/test_my_spell.py`. Cover:

- All resources are created
- Names follow the `{stack}-{resource}-{suffix}` pattern
- Security list / NSG rules are registered correctly
- Edge cases relevant to your spell

### 5. Add an example

Add `examples/my-spell/__main__.py` demonstrating minimal usage. Follow the pattern in existing examples.

---

## Docstring rules

All public classes, methods, and modules require Google-style docstrings. No undocumented public API is acceptable.

### Automated enforcement

Docstring quality is enforced automatically by `make lint` via two ruff rule sets:

| Rule set | What it checks |
|----------|----------------|
| `D` (pydocstyle, `convention = "google"`) | Presence and structure of docstrings; `D417` catches parameters present in the signature but missing from `Args:` |
| `DOC201` | Function has a `return` statement but no `Returns:` section |
| `DOC402` | Function has a `yield` statement but no `Yields:` section |
| `DOC501` | Exception is explicitly raised but not listed in `Raises:` |

Violations are reported as lint errors and will fail CI. There is no separate tool to install — ruff handles everything.

### Markup format

Use **pure Markdown** inside docstrings. This is the only format that renders correctly in both VS Code (Pylance hover) and mkdocstrings.

| Use | Avoid |
|-----|-------|
| `` `value` `` for inline code | ` ``value`` ` (RST double-backtick) |
| ` ``` ` fenced code blocks | `pattern::` + indented block (RST code block) |
| plain prose | `*italic*` for emphasis (RST italic) |

### Required sections

Include all sections that apply:

```python
def example(self, name: str) -> str:
    """Short one-line summary.

    Longer description if needed.

    Args:
        name: What this argument is.

    Returns:
        What the return value contains.

    Raises:
        ValueError: When `name` is empty.

    Example:
        ```python
        result = obj.example("foo")
        ```
    """
```

Classes also require an `Attributes:` section for IDE hover support.

---

## Pull request guidelines

- **Keep PRs small and focused.** One spell, one fix, one improvement — not a combination.
- **Link to an issue.** Every PR should reference an open issue: `Closes #123`.
- **Explain the "why", not just the "what".** The PR description should explain the motivation, not just list the files changed.
- **All quality gate checks must pass.** CI will verify this; do not open a PR expecting to fix failures there.
- **New spells require tests and an example.** PRs missing either will be sent back.

---

## What NOT to contribute

The following will not be merged, regardless of code quality:

- **Thin wrappers** that expose OCI resource properties without an architectural opinion
- **Pass-through parameters** that exist only to forward a low-level option to the underlying resource
- **Parameters that reduce abstraction** — if adding a parameter lets the caller misconfigure something the spell currently prevents, it will not be accepted
- **Undocumented public APIs** — every public symbol must have a full Google-style docstring
- **Direct additions to `src/blocks/`** — that package is backward-compat shims only; no logic goes there

---

## Roadmap items welcomed

These areas are actively looking for contributors:

- **AWS provider** — implement `src/providers/aws/` against the existing abstractions in `src/core/abstractions/`
- **GCP provider** — implement `src/providers/gcp/`
- **Additional OCI spells** — Database, Object Storage, API Gateway, Functions, Streaming
- **CLI tool** — CloudSpells-specific commands for stack scaffolding and management
- **Enhanced observability** — VCN Flow Logs, monitoring alarms as first-class spell features

If you want to work on any of these, open an issue first so we can align on the design before you invest significant time.

---

## Issue labels guide

| Label | Meaning |
|-------|---------|
| `bug` | Something is broken |
| `enhancement` | Improvement to an existing spell or feature |
| `new-block` | Proposal or implementation of a new spell |
| `new-provider` | Work toward a new cloud provider |
| `documentation` | Docs-only change |
| `good first issue` | Suitable for first-time contributors |
| `needs-triage` | Not yet reviewed by a maintainer |
| `wontfix` | Outside the project's scope or philosophy |

---

## Thank you

CloudSpells exists because people care about infrastructure that is correct by construction, not just correct by convention. Every thoughtful issue, well-scoped PR, and honest review makes it better for everyone who uses it. We are glad you are here.
