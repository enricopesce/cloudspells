# Package Instructions

These rules apply under `packages/`.

## Layout

```text
packages/cloudspells-core/src/cloudspells/core/          # cloud-neutral primitives
packages/cloudspells-core/src/cloudspells/core/abstractions/  # cloud-neutral interfaces
packages/cloudspells-oci/src/cloudspells/providers/oci/ # OCI spell implementations
packages/cloudspells-cli/src/cloudspells/cli/           # Typer-based CLI
```

New OCI code imports from `cloudspells.providers.oci` directly. A new cloud provider belongs in a new `packages/cloudspells-<cloud>/` package.

## Python And Pulumi

- Use `from __future__ import annotations` in new Python modules.
- Keep public APIs typed with `pulumi.Input[T]` and `pulumi.Output[T]` where appropriate.
- Prefer dataclasses or typed structures over raw dictionaries for reusable public shapes.
- Use `Output.all()` for multi-value Pulumi transformations instead of deeply chained `.apply()` calls.
- Guard real provider lookup behavior carefully and keep normal `pulumi up` reproducible.
- Complete `register_outputs()` for each `ComponentResource`.

## VCN Pattern

For VCN-attached spells:

```python
def __init__(self, name: str, compartment_id: pulumi.Input[str], vcn: Vcn | VcnRef, ...) -> None:
    super().__init__(...)
    vcn.add_security_rules(SecurityRules(...))
    vcn.finalize_network()
    # Subnet IDs and CIDRs are safe to use here.
```

`finalize_network()` is idempotent. Subnet CIDR accessors return Pulumi-compatible input values for both `Vcn` and `VcnRef`.

## Docstrings

- Use Google-style docstrings on public modules, classes, and methods.
- Use Markdown code formatting: `` `value` `` and fenced code blocks.
- Do not use RST double-backticks, `::` blocks, or italic markup in docstrings.
- Define `__all__` for package exports.

## Shared Logic

When two or more spell classes in one module share identical `get_*()` or `export()` logic, extract a private mixin named `_<Resource>Mixin`. The mixin is not exported.
