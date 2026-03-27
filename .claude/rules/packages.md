---
description: CloudSpells spell-file conventions — applied when editing packages/**/*.py
globs: packages/**/*.py
alwaysApply: false
---

# Package Coding Conventions

## Package Structure

```
packages/cloudspells-core/src/cloudspells/core/abstractions/  — cloud-neutral interfaces
packages/cloudspells-oci/src/cloudspells/providers/oci/       — OCI implementations
```

New code imports from `cloudspells.providers.oci` directly. New provider = new `packages/cloudspells-<cloud>/` package — no core changes needed.

## VCN Lazy Init Pattern

```python
def __init__(self, name: str, compartment_id: pulumi.Input[str], vcn: Vcn | VcnRef, ...):
    super().__init__(...)
    vcn.add_security_list_rules([...])   # accumulate rules during __init__
    vcn.finalize_network()               # materialise subnets — idempotent
    # safe to reference vcn.private_subnet_id etc. from here
```

`finalize_network()` is idempotent. Subnet CIDR accessors return `pulumi.Input[str]` — compatible with both `Vcn` and `VcnRef`.

## DRY via Private Mixin (CS-011)

When two or more spell classes in the same module share identical accessor logic (`get_X()`, `export()`), extract into a private `_<Resource>Mixin`. Not exported. Each spell inherits `(_<Resource>Mixin, BaseResource)`.

## Docstring Format

Google-style on all public classes, methods, and modules. `__all__` defined in every `__init__.py`.

**Pure Markdown only** (works in VS Code Pylance hover and mkdocstrings):
- `` `value` `` not `` ``value`` `` (RST double-backtick)
- Fenced code blocks, not `pattern::` + indented block
- No `*italic*` — renders as literal asterisks in RST
