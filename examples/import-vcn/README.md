# Import VCN Example

Deploys a compute instance into a VCN owned by another Pulumi stack using `VcnRef.from_stack_reference()`.

`VcnRef` is read-only: this stack does not create or modify VCN security lists. The source VCN stack must already export the CloudSpells VCN outputs and the `APP_SERVER` network profile consumed by this example.

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | - | OCI compartment OCID |
| `vcn_stack` | Yes | - | Pulumi stack reference for the source VCN stack |
| `availability_domain` | Yes | - | Availability domain for the compute instance |
| `image_ocid` | Yes | - | Boot image OCID for the compute instance |
| `ssh_key` | No | generated | Public SSH key installed on the instance |

## Deploy

```bash
cd examples/import-vcn

pulumi stack init dev
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set vcn_stack <org/project/stack>
pulumi config set availability_domain <availability-domain>
pulumi config set image_ocid <image-ocid>

pulumi preview
pulumi up
```

## Source VCN Requirements

The referenced stack must export the standard outputs produced by `Vcn.export()`, including subnet IDs, subnet CIDRs, security-list IDs, `cidr_block`, `cloudspells_network_schema`, and `cloudspells_network_profiles`.

A bare VCN exports only the baseline network profile. Because this example
creates an `APP_SERVER` role NSG against a `VcnRef`, add a matching source-stack
NSG before `vcn.export()`:

```python
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

vcn = Vcn(name="shared", compartment_id=compartment_id)
Nsg("app-server-profile", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)
vcn.export()
```
