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
| `oci:Core/internetGateway:InternetGateway` | `id` |
| `oci:Core/natGateway:NatGateway` | `id` |
| `oci:Core/serviceGateway:ServiceGateway` | `id` |
| `oci:Core/drg:Drg` | `id` |
| `oci:Core/drgAttachment:DrgAttachment` | `id` |
| `oci:Core/routeTable:RouteTable` | `id` |
| `oci:Core/securityList:SecurityList` | `id` |
| `oci:Core/defaultSecurityList:DefaultSecurityList` | `id` |
| `oci:Core/networkSecurityGroup:NetworkSecurityGroup` | `id` |
| `oci:Core/networkSecurityGroupSecurityRule:NetworkSecurityGroupSecurityRule` | `id` |
| `oci:Core/instance:Instance` | `privateIp="10.0.128.10"`, `publicIp=None` |
| `oci:Core/instanceConfiguration:InstanceConfiguration` | `id` |
| `oci:Core/instancePool:InstancePool` | `id` |
| `oci:Core/volume:Volume` | `id` |
| `oci:Core/volumeAttachment:VolumeAttachment` | `id` |
| `oci:AutoScaling/autoScalingConfiguration:AutoScalingConfiguration` | `id` |
| `oci:LoadBalancer/loadBalancer:LoadBalancer` | `ipAddressDetails=[{"ipAddress": "10.0.0.100", "isPublic": True}]` |
| `oci:LoadBalancer/backendSet:BackendSet` | `name` |
| `oci:LoadBalancer/ruleSet:RuleSet` | `name` |
| `oci:LoadBalancer/listener:Listener` | `name` |
| `oci:Bastion/bastion:Bastion` | `privateEndpointIpAddress="10.0.128.5"` |
| `oci:Identity/dynamicGroup:DynamicGroup` | `id` |
| `oci:Identity/policy:Policy` | `id` |
| `oci:Identity/group:Group` | `id` |
| `oci:ObjectStorage/bucket:Bucket` | `name` |
| `oci:ObjectStorage/objectLifecyclePolicy:ObjectLifecyclePolicy` | `id` |
| `oci:Logging/logGroup:LogGroup` | `id` |
| `oci:Logging/log:Log` | `id` |
| `oci:ContainerEngine/cluster:Cluster` | `id`, `endpoints`, `lifecycleState="ACTIVE"` |
| `oci:ContainerEngine/nodePool:NodePool` | `id`, `lifecycleState="ACTIVE"` |

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
- `test_iam.py` — ComputeInstancePrincipal, OkeNodePrincipal, CompartmentAdminGroup
- `test_loadbalancer.py` — LoadBalancer spells
- `test_network_logging.py` — network logging spells
- `test_nsg.py` — Nsg
- `test_roles.py` — role constants and helpers
- `test_storage.py` — bucket spells
- `test_volume.py` — BlockVolume
- `mocks.py` — shared mock infrastructure (not a test file)
