# IAM Example

Creates common OCI IAM bindings for CloudSpells workloads:

- `ComputeInstancePrincipal` for one exact app instance.
- `OkeNodePrincipal` for OKE node compartments. This matches all compute
  instances in the configured compartment, so the example uses the required
  dedicated-node-compartment acknowledgement in code.
- `CompartmentAdminGroup` for human operators scoped to one compartment.

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | - | Workload compartment OCID |
| `tenancy_ocid` | Yes | - | Tenancy root compartment OCID |
| `app_instance_ocid` | Yes | - | Compute instance OCID that receives app instance-principal grants |

## Deploy

```bash
cd examples/iam

pulumi stack init dev
pulumi config set compartment_ocid <workload-compartment-ocid>
pulumi config set tenancy_ocid <tenancy-ocid>
pulumi config set app_instance_ocid <app-instance-ocid>

pulumi preview
pulumi up
```

## Outputs

| Output | Description |
|--------|-------------|
| `app_dynamic_group_id` | Dynamic group for the configured app instance |
| `k8s_dynamic_group_id` | Dynamic group for all compute instances in the dedicated OKE node compartment |
| `ops_group_id` | IAM group for compartment operators |
