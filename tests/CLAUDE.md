# tests — Test Conventions

## Critical: mock setup order

`set_mocks()` **must** be called before importing any infrastructure module, or the OCI provider won't be intercepted.

```python
from tests.mocks import set_mocks
set_mocks()  # ← BEFORE infrastructure imports

from cloudspells.providers.oci.network import Vcn  # ← AFTER
```

Both packages are on `sys.path` via `pythonpath` in `pyproject.toml` — no manual `sys.path` manipulation needed.

## mocks.py — what's mocked

| Resource type | Injected outputs |
|---------------|-----------------|
| `oci:Core/vcn:Vcn` | `defaultRouteTableId`, `defaultSecurityListId` |
| `oci:Core/subnet:Subnet` | `id` |
| `oci:Core/instance:Instance` | `privateIp="10.0.128.10"`, `publicIp=None` |
| `oci:Core/volume:Volume` | `id` |
| `oci:LoadBalancer/loadBalancer:LoadBalancer` | `ipAddressDetails=[{"ipAddress": "10.0.0.100", "isPublic": True}]` |
| `oci:Bastion/bastion:Bastion` | `privateEndpointIpAddress="10.0.128.5"` |

| Provider call | Returns |
|--------------|---------|
| `oci:Core/getServices:getServices` | Mock service CIDR |
| `oci:Core/getImages:getImages` | Mock Oracle Linux 8 image |
| `oci:Identity/getAvailabilityDomains:getAvailabilityDomains` | 3 mock ADs |

## Test pattern

```python
@pulumi.runtime.test
async def test_something(self):
    vcn = Vcn("test", "ocid1.compartment.oc1...", "test-stack")
    # use .apply() to extract values from pulumi.Output
    def check(value):
        self.assertEqual(value, "expected")
    vcn.some_output.apply(check)
```

## Running tests

```bash
source .venv/bin/activate
pytest                          # all tests with coverage
pytest tests/test_vcn.py        # single file
pytest tests/test_vcn.py::TestVcn::test_vcn_creates_base_resources  # single case
```

## Files
- `test_vcn.py` — Vcn and VcnRef
- `test_oke.py` — OkeCluster
- `test_compute.py` — ComputeInstance
- `test_autoscale.py` — ScalableWorkload
- `test_bastion.py` — Bastion
- `mocks.py` — shared mock infrastructure (not a test file)
