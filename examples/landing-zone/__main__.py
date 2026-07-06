"""Landing zone — the reusable OCI foundation, deployed on its own.

Creates the complete CloudSpells foundation in one call: four-tier VCN with
flow logs always on, an OCI Bastion for session-based SSH, and the
compartment-admin IAM baseline.

Workload stacks (`OkeCluster`, `ComputeInstance`, `ScalableWorkload`, ...)
consume this foundation via `VcnRef.from_stack_reference()` — see
`examples/import-vcn` for the consumer side.

Uncomment the `enable_oke_profile()` line (or register role NSGs) before
`export()` to pre-authorise the workloads your teams will deploy.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.landing_zone import LandingZone

config = Config()
compartment_id: str = config.require("compartment_ocid")
tenancy_id: str = config.require("tenancy_ocid")
bastion_client_cidr: str = config.require("bastion_client_cidr")

lz: LandingZone = LandingZone(
    name="foundation",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
    allowed_client_cidrs=[bastion_client_cidr],
)

# Pre-authorise workload profiles for consumer stacks, e.g.:
# lz.vcn.enable_oke_profile(kubectl_allowed_cidrs=[bastion_client_cidr])

lz.export()
