# Package conventions

- `cloudspells-core/src/cloudspells/core/abstractions/` holds cloud-neutral interfaces. Add a new provider in its own `cloudspells-<cloud>` package and reuse the core interfaces.
- `cloudspells-oci/src/cloudspells/providers/oci/` holds OCI implementations. Import new OCI code through `cloudspells.providers.oci` and its submodules.
- `cloudspells-cli/src/cloudspells/cli/` implements the Typer-based `cs` command for stack scaffolding and management. The CLI package requires Python 3.12 or later. Preserve Python 3.11 compatibility for core and OCI.
- Define `__all__` in package `__init__.py` files. Preserve existing semantic groupings where Ruff configuration exempts them from sorting.

## OCI spells

Follow the CS rules in [the root guidance](../AGENTS.md). A network-attached constructor accepts `Vcn | VcnRef`, calls `vcn.add_security_list_rules(...)`, and calls the idempotent `vcn.finalize_network()` before creating subnet-dependent resources. Subnet CIDR accessors return `pulumi.Input[str]` for both VCN types.
