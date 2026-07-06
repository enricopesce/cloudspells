"""Landing zone + application VM in one stack — the layered model, same-stack form.

The `LandingZone` provides the foundation (4-tier VCN with flow logs, Bastion,
IAM baseline); the `ComputeInstance` is the real service deployed inside it.
The VM lives in the private subnet with zero public surface — SSH access goes
exclusively through the landing zone's Bastion.

```
Internet
   │  (OCI Bastion service — no public IP on instance)
   ▼
┌───────────────────────────────────────────────────────┐
│ LandingZone "foundation"                              │
│  Private subnet — NAT GW + Service GW routes          │
│   app-server  [app-nsg · APP_SERVER]                  │
│   foundation bastion  ← OCI Bastion service           │
│  Flow logs on every tier · compartment admin group    │
└───────────────────────────────────────────────────────┘
```

Ordering matters: workload spells are declared between `LandingZone(...)` and
`lz.export()`, so their security rules are registered before the network is
materialised.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.landing_zone import LandingZone
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

config = Config()
compartment_id: str = config.require("compartment_ocid")
tenancy_id: str = config.require("tenancy_ocid")
bastion_client_cidr: str = config.require("bastion_client_cidr")
availability_domain: str = config.require("availability_domain")

# 1. The foundation — network, audit logging, bastion access, IAM baseline.
lz: LandingZone = LandingZone(
    name="foundation",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
    allowed_client_cidrs=[bastion_client_cidr],
)

# 2. The service inside it — a private application server. The APP_SERVER
#    role places it in the private subnet; SSH arrives only via the Bastion.
app_nsg: Nsg = Nsg(
    "app-server",
    role=APP_SERVER,
    vcn=lz.vcn,
    compartment_id=compartment_id,
)

app: ComputeInstance = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    availability_domain=availability_domain,
    ssh_public_key=config.get("ssh_key"),
    nsg=app_nsg,
    ocpus=1,
    memory_in_gbs=4,
)

# 3. Materialise the foundation and publish the contract.
lz.export()
app.export()
