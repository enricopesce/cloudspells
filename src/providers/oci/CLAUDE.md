# src/providers/oci — OCI Implementation

All canonical block logic lives here. `src/blocks/` re-exports from here — never the other way.

## Files & Exports

| File | Key Class | One-liner |
|------|-----------|-----------|
| `network.py` | `Vcn`, `VcnRef` | 4-tier VCN with lazy-init builder |
| `compute.py` | `ComputeInstance` | Single VM, auto-SSH, block volumes |
| `kubernetes.py` | `OkeCluster` | BASIC_CLUSTER, OCI_VCN_IP_NATIVE CNI |
| `autoscale.py` | `ScalableWorkload` | LB (public) + instance pool (private) + autoscaling |
| `bastion.py` | `Bastion` | OCI Bastion service in private subnet |
| `nsg.py` | `Nsg` | NSG builder + port constants + role ambient rules |
| `roles.py` | `Role` + constants | Predefined security postures |
| `volume.py` | `VolumeSpec` | Block volume spec dataclass |
| `helper.py` | `OciHelper` | `resolve_image_id()`, `get_ads()` |
| `network_logging.py` | `VcnFlowLogs` | Optional VCN flow log group |

## Critical patterns

### VCN lazy-init builder

```python
vcn = Vcn("myvcn", compartment_id, stack_name)
vcn.add_security_list_rules(rules)   # accumulate (idempotent order matters)
vcn.finalize_network()               # materialises subnets + security lists — ONCE
```

- `finalize_network()` is idempotent (`_security_lists_finalized` flag); first call wins
- Service blocks (`OkeCluster`, `ComputeInstance`, `ScalableWorkload`, `Bastion`) call `finalize_network()` automatically — callers don't need to
- Subnet attributes (`public_subnet`, `private_subnet`, …) are `None` before finalization
- CIDR accessors return `pulumi.Input[str]`, not `str` — works for both `Vcn` and `VcnRef`

### 4-tier CIDR split (binary subdivision)

| Tier | Share | Routing |
|------|-------|---------|
| Private | 50% (prefix+1) | NAT GW + Service GW |
| Secure | 25% (prefix+2) | Service GW only |
| Public | 12.5% (prefix+3) | Internet GW |
| Management | 12.5% (prefix+3) | Service GW only |

### VcnRef (cross-stack)

```python
vcnref = VcnRef.from_stack_reference(stack_name)
```

- `add_security_rules()` and `finalize_network()` are deliberate no-ops
- CIDR accessors return `pulumi.Output[str]` pointing to cross-stack values
- All service blocks accept `Vcn | VcnRef` transparently

### NSG roles

```python
from providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE
nsg = Nsg("web", role=INTERNET_EDGE, vcn=vcn, compartment_id=cid, stack_name=stack)
instance = ComputeInstance("web", ..., nsg=nsg)  # subnet inferred from role
```

- `nsg.serves(target_nsg, port)` generates bilateral NSG + cross-subnet security list rules in one call
- Role ambient rules are accumulated into VCN security lists at `Nsg.__init__` time

### Predefined roles

| Constant | Tier | Egress |
|----------|------|--------|
| `INTERNET_EDGE` | public | none (entry point) |
| `APP_SERVER` | private | NAT + Services |
| `DATABASE` | secure | Services only |
| `CACHE` | private | NAT + Services (alias for APP_SERVER) |
| `MANAGEMENT` | management | Services only |

### Port constants (from nsg.py)

`SSH=22`, `HTTP=80`, `HTTPS=443`, `POSTGRES=5432`, `MYSQL=3306`, `ORACLE_DB=1521`, `REDIS=6379`, `KAFKA=9092`, `NFS=2049`

### VolumeSpec validation

- `size_in_gbs >= 50`
- `vpus_per_gb` ∈ {0, 10, 20, 120} (`PERF_LOW/BALANCED/HIGH/ULTRA`)
- `label` must match `^[a-z][a-z0-9-]*$`

### OciHelper

- `resolve_image_id(compartment_id, shape, image_id=None, os_name="oracle")` — queries OCI API; supported os_names: `"oracle"` (OL8), `"ubuntu"` (22.04), `"windows"` (Server 2022)
- `get_ads(ads, subnet_id)` — returns list of `{"availability_domain": str, "subnet_id": str}` for node pool placement

## Rules
- Every public class, method, module: Google-style docstring with `Args:`, `Returns:`, etc.
- Docstring markup: pure Markdown only — single backticks, fenced blocks. No RST.
- Do not expose parameters that just pass through OCI provider options
- Architecture decisions (topology, routing, security) are fixed — not user-configurable
