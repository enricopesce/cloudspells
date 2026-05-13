# CloudSpells Spell Patterns

## Source Responsibilities

```text
packages/cloudspells-core/src/cloudspells/core/base.py
    BaseResource, ResourceNamer, ResourceTagger

packages/cloudspells-core/src/cloudspells/core/abstractions/
    cloud-neutral interfaces

packages/cloudspells-oci/src/cloudspells/providers/oci/<module>.py
    OCI spell implementation

packages/cloudspells-oci/src/cloudspells/providers/oci/__init__.py
    public OCI exports

tests/mocks.py
    Pulumi mock output injection

tests/test_<module>.py
    unit tests for the spell module

docs/api/providers/<module>.md
    mkdocstrings API entry

docs/how-to/ or docs/tutorials/
    usage docs when an existing page should be updated
```

## Canonical Existing Modules

- `bastion.py`: minimal single-class VCN-attached spell.
- `storage.py`: multi-class spell with a private mixin.
- `network.py`: `Vcn`, `VcnRef`, subnet tier constants, and lazy network finalization.
- `compute.py`: create-time-only placement input pattern.
- `kubernetes.py`: multi-resource spell with internally managed OCI outputs.

## Module Structure

```python
"""One-line module summary.

Short Markdown description of what the module provisions and what it exports.

Exports:
    ExampleSpell: One-line description.
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from cloudspells.core.base import BaseResource

from .network import Vcn, VcnRef


class ExampleSpell(BaseResource):
    """Provision an example OCI resource.

    Resources created:

    - `oci.example.Resource`

    Attributes:
        resource: The underlying OCI resource.

    Example:
        ```python
        spell = ExampleSpell("demo", compartment_id)
        spell.export()
        ```
    """

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Provision the example resource.

        Args:
            name: Logical resource name.
            compartment_id: OCID of the OCI compartment.
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`.
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:cloudspells:ExampleSpell", name, compartment_id, stack_name, opts)
```

## Pulumi And OCI Rules

- Use `self.create_resource_name("suffix")` for all underlying resource names.
- Use `pulumi.Output.all()` when a value depends on multiple outputs.
- Prefer `get_*_output()` provider helpers over blocking `get_*()` helpers.
- Treat image IDs and Kubernetes versions as explicit caller choices.
- Treat `availability_domain` and `fault_domain` as optional create-time placement overrides that may auto-resolve internally.
- Call `register_outputs()` with every output consumers need.

## Test Rules

- Call `set_mocks()` before importing spell modules.
- Add mock output entries for every new Pulumi OCI resource type used by the spell.
- Use `@pulumi.runtime.test`.
- Do not add `-> None` annotations to Pulumi runtime test methods.
- Match the existing `tests/test_<module>.py` style for assertions.

## Documentation Rules

- Update existing docs before creating new pages.
- API docs under `docs/api/providers/` use mkdocstrings `:::` directives.
- How-to and tutorial pages must show copy-pasteable imports from `cloudspells.providers.oci.<module>`.
- Keep docstrings pure Markdown.
