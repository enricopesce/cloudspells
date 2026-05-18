# Secure VCN Example

Deploys a monitored four-tier VCN with role-based NSGs, VCN Flow Logs, and IAM bindings for an existing app-tier compute instance.

The stack does not create compute instances. `app_instance_ocid` identifies the existing VM that should receive the app instance-principal grants.

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | - | OCI compartment OCID |
| `tenancy_ocid` | Yes | - | Tenancy root compartment OCID |
| `app_instance_ocid` | Yes | - | Existing app instance OCID for instance-principal grants |
| `vcn_cidr` | No | `10.0.0.0/18` | VCN CIDR block |
| `management_ingress_cidr` | No | `0.0.0.0/0` | CIDR allowed to SSH into the management NSG; restrict before production |
| `app_port` | No | `8080` | App-tier TCP port |
| `db_port` | No | `1521` | Database TCP port |
| `log_retention_days` | No | `90` | Flow log retention: 30, 60, 90, 120, 150, or 180 days |

## Deploy

```bash
cd examples/secure-vcn

pulumi stack init dev
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set tenancy_ocid <tenancy-ocid>
pulumi config set app_instance_ocid <app-instance-ocid>
pulumi config set management_ingress_cidr <ops-cidr>

pulumi preview
pulumi up
```

## Outputs

The stack exports VCN subnet outputs, `network_audit_log_group_id`, app instance-principal outputs, and ops group policy outputs.
