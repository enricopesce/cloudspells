# src/core — Foundation Layer

Cloud-neutral foundation. No OCI imports anywhere in this directory.

## Files

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `BaseResource` | Base class for all blocks — naming, tagging, SSH keys |
| `naming.py` | `ResourceNamer` | `{stack}-{name}-{suffix}` names; DNS labels ≤15 chars |
| `tagging.py` | `ResourceTagger` | Freeform tags (Name, ResourceType, Environment, CreatedBy) |
| `helper.py` | `Helper` | Cloud-neutral utils: CIDR subdivision, SSH key-pair generation |
| `abstractions/` | ABCs + dataclasses | Cloud-neutral contracts; providers implement these |

## BaseResource

```python
BaseResource(resource_type, name, compartment_id, stack_name, opts, project_ref=None)
```

- Inherits `pulumi.ComponentResource`
- Convenience delegates: `create_resource_name(suffix)`, `create_freeform_tags(...)`, `create_network_resource_tags(...)`, `create_gateway_tags(...)`
- SSH keys: auto-generates RSA 4096-bit if not provided; stored as `self.ssh_public_key`, `self.ssh_private_key`; exported as Pulumi secrets via `_get_ssh_outputs()`
- Check `self.auto_generated_keys` before assuming private key is available

## abstractions/

### network.py
- `IngressRule`, `EgressRule`, `SecurityRules` dataclasses
- Factory functions: `tcp_ingress()`, `tcp_egress()`, `all_egress()`, `icmp_path_mtu_ingress()`, `icmp_path_mtu_egress()`
- Constants: `INTERNET = "0.0.0.0/0"`, `CLOUD_SERVICES = "cloud-services"` (symbolic — resolved by provider)
- `AbstractNetwork`: builder ABC — `add_security_rules()`, `finalize_network()`, CIDR accessors return `pulumi.Input[str]`
- `AbstractNetworkRef`: read-only cross-stack ABC — `add_security_rules()` and `finalize_network()` are intentional no-ops

### compute.py
- `DiskSpec`, `SUBNET_PUBLIC/PRIVATE/SECURE/MANAGEMENT` constants
- `AbstractCompute` ABC

### autoscale.py
- `ScalingMetric`, `ScalingAction` enums
- `MetricScalingPolicy`, `ScheduleScalingPolicy`, `LoadBalancerConfig` dataclasses
- `AbstractScalableWorkload` ABC

### kubernetes.py / bastion.py
- Minimal ABCs: `AbstractKubernetes`, `AbstractBastion`

## Rules
- Never add OCI-specific imports here — keep cloud-neutral
- `Helper.calculate_subnets(cidr, n)` does binary subdivision; always CIDR-aligned, no gaps
