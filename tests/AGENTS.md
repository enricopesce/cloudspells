# Test Instructions

## Pulumi Mock Order

Always call `set_mocks()` before importing infrastructure modules. The OCI provider will not be intercepted if the order is reversed.

```python
from tests.mocks import set_mocks

set_mocks()

from cloudspells.providers.oci.network import Vcn
```

Do not add manual `sys.path` manipulation. `pyproject.toml` already configures `pythonpath`.

## Test Pattern

Use `@pulumi.runtime.test` for Pulumi resource tests and extract `pulumi.Output` values with `.apply()`.

```python
@pulumi.runtime.test
async def test_something(self):
    vcn = Vcn("test", "ocid1.compartment.oc1...", "test-stack")

    def check(value):
        self.assertEqual(value, "expected")

    vcn.some_output.apply(check)
```

Do not add `-> None` return annotations to Pulumi runtime test methods.

## Commands

```bash
.venv/bin/pytest
.venv/bin/pytest tests/test_vcn.py
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_vcn_creates_base_resources
```
