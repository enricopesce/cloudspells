# Web + Database Example

Deploys a three-tier OCI stack using role-based NSGs:

- Public tier: load-balancer VM with `INTERNET_EDGE`.
- Private tier: two web backend VMs with `APP_SERVER`.
- Secure tier: two database VMs with `DATABASE`.

The NSG relationships `lb_nsg.serves(web_nsg, port=app_port)` and `web_nsg.serves(db_nsg, port=db_port)` generate the matching NSG rules and cross-subnet security-list rules.

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | - | OCI compartment OCID |
| `availability_domain` | Yes | - | Availability domain for all demo VMs |
| `image_ocid` | Yes | - | Boot image OCID for all demo VMs |
| `ssh_key` | No | generated | Public SSH key installed on the VMs |
| `vcn_cidr` | No | `10.0.0.0/18` | VCN CIDR block |
| `app_port` | No | `8080` | Web backend application port |
| `db_port` | No | `5432` | Database listener port |

## Deploy

```bash
cd examples/web-db

pulumi stack init dev
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set availability_domain <availability-domain>
pulumi config set image_ocid <image-ocid>

pulumi preview
pulumi up
```

## Outputs

The stack exports the VCN outputs plus each compute instance's standard `ComputeInstance` outputs.
