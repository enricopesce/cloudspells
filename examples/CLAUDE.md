# examples — Reference Architectures

Each subdirectory is a standalone Pulumi stack. Run from within the example directory.

```bash
source ../../.venv/bin/activate
cd examples/<name>
pulumi preview   # dry run
pulumi up        # deploy
pulumi destroy   # tear down
```

## Examples

| Directory | Spells used | Teaches |
|-----------|-------------|---------|
| `vcn/` | `Vcn` | Standalone VCN; outputs consumed by `import-vcn` |
| `compute/` | `Vcn`, `ComputeInstance`, `Nsg` | NSG roles, role-inferred subnet placement, volumes |
| `autoscale/` | `Vcn`, `ScalableWorkload` | LB + instance pool + CPU autoscaling, cloud-init user data |
| `oke/` | `Vcn`, `OkeCluster` | Kubernetes on OCI, kubeconfig generation |
| `bastion/` | `Vcn`, `Bastion` | Bastion access pattern, client CIDR allow lists |
| `web-db/` | `Vcn`, `Nsg` ×3, `ComputeInstance` ×2 | 3-tier: INTERNET_EDGE → APP_SERVER → DATABASE; `nsg.serves()` |
| `import-vcn/` | `VcnRef` | Cross-stack VCN reference via `VcnRef.from_stack_reference()` |
| `secure-vcn/` | `Vcn`, `VcnFlowLogs` | Flow logs, advanced security rules |

## Config (Pulumi.\<stack\>.yaml)

Required keys for most examples:
- `compartment_ocid` — OCI compartment OCID
- `vcn_cidr_block` — CIDR block for the VCN (e.g. `"10.0.0.0/18"`)

## Rules
- Examples demonstrate usage patterns; they are not tests
- Keep each example minimal — one concept per directory
- Never add logic to examples that belongs in a spell
- `__main__.py` is the entry point for every Pulumi stack
