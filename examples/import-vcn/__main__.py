"""Deploy services into a VCN managed by another Pulumi stack.

Uses `VcnRef` to import a VCN from a separately-managed stack
(e.g. `examples/vcn`) and then deploys a compute instance into it.

No network resources are created or modified here.

> **Note:** `VcnRef` is read-only. Role-bearing NSGs created here still add
> their own NSG rules, but any matching subnet security list rules required by
> the role must already exist in the source VCN stack.

## Prerequisites

The referenced VCN stack must already have run `pulumi up` and export:

- `vcn_id`
- `cidr_block`
- `public_subnet_id`
- `private_subnet_id`
- `secure_subnet_id`
- `management_subnet_id`
- `public_subnet_cidr`
- `private_subnet_cidr`
- `secure_subnet_cidr`
- `management_subnet_cidr`
- `public_security_list_id`
- `private_security_list_id`
- `secure_security_list_id`
- `management_security_list_id`
- `drg_id`
- `cloudspells_network_schema`
- `cloudspells_network_profiles`

All values are exported by `examples/vcn` via `vcn.export()`.

## Quick start

```bash
cd examples/import-vcn
pulumi stack init <stack-name>
pulumi config set compartment_ocid  <COMPARTMENT_OCID>
pulumi config set vcn_stack         <STACK_REFERENCE>
```

## Stack reference format

- Pulumi Cloud: `"<organization>/<project>/<stack>"`
- Local file backend: `"<project>/<stack>"`
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import VcnRef
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

config = Config()
compartment_id: str = config.require("compartment_ocid")
vcn_stack: str = config.require("vcn_stack")
availability_domain: str = config.require("availability_domain")

ssh_key: str | None = config.get("ssh_key") or None

vcn: VcnRef = VcnRef.from_stack_reference(vcn_stack)

app_nsg: Nsg = Nsg(
    "app-server",
    role=APP_SERVER,
    vcn=vcn,
    compartment_id=compartment_id,
)

instance: ComputeInstance = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    availability_domain=availability_domain,
    ssh_public_key=ssh_key,
    nsg=app_nsg,
)

instance.export()
