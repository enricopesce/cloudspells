"""IAM example — instance principals and compartment admin group.

Demonstrates the three IAM spells for common workload patterns:

- `ComputeInstancePrincipal`: Dynamic group + policy so selected compute
  instances can authenticate as instance principals and read from Object
  Storage and Vault Secrets — no API keys on the VM needed.
- `OkeNodePrincipal`: Dynamic group + policy granting OKE node pool instances
  the full permission set required for cluster operation (networking, volumes,
  load balancers, container registry). This principal remains compartment-
  scoped; use a dedicated OKE node compartment until CloudSpells adds a worker
  node tag boundary.
- `CompartmentAdminGroup`: IAM group + policy delegating full compartment
  management to a human operator group without granting tenancy-level access.

## Architecture

```
Tenancy (root compartment)
 ├── DynamicGroup: {stack}-app-dg     ← matches app_instance_ocid exactly
 ├── DynamicGroup: {stack}-k8s-dg     ← matches all instances in compartment
 └── Group:        {stack}-ops-group

Compartment
 ├── Policy: {stack}-app-policy   → read object-family, read secret-family
 ├── Policy: {stack}-k8s-policy   → manage instance-family, use network, ...
 └── Policy: {stack}-ops-policy   → manage all-resources
```

## Configuration

Required:

- `compartment_ocid` — OCID of the workload compartment.
- `tenancy_ocid` — OCID of the tenancy root compartment (visible in OCI
  Console under Tenancy Details → OCID).
- `app_instance_ocid` — OCID of the compute instance that should receive the
  app instance-principal grants.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

import pulumi

from cloudspells.core import Config
from cloudspells.providers.oci.iam import (
    CompartmentAdminGroup,
    ComputeInstancePrincipal,
    IamGrant,
    OkeNodePrincipal,
)

config = Config()
compartment_id: str = config.require("compartment_ocid")
tenancy_id: str = config.require("tenancy_ocid")
app_instance_id: str = config.require("app_instance_ocid")

# ── 1. Compute instance principal ─────────────────────────────────────────────
#
# Only app_instance_ocid becomes a member of this dynamic group.
# Use IamGrant helpers for common CloudSpells permissions and
# IamGrant.raw("<verb> <resource-type>") for OCI grant fragments CloudSpells
# does not model.

app_principal: ComputeInstancePrincipal = ComputeInstancePrincipal(
    name="app",
    tenancy_id=tenancy_id,
    compartment_id=compartment_id,
    instance_ids=[app_instance_id],
    grants=[
        IamGrant.read_secrets(),  # fetch DB passwords and API keys from Vault
        IamGrant.read_objects(),  # read app config and assets from Object Storage
    ],
)

# ── 2. OKE node principal ─────────────────────────────────────────────────────
#
# OKE node pool instances need permissions to manage cluster resources:
# networking, block volumes, load balancers, and container registry pulls.
# This dynamic group + policy provides the full required permission set. It
# matches all compute instances in compartment_id, so keep OKE nodes isolated
# in a dedicated compartment when using this spell.

oke_principal: OkeNodePrincipal = OkeNodePrincipal(
    name="k8s",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
)

# ── 3. Compartment admin group ────────────────────────────────────────────────
#
# Empty group created at the tenancy level. Add human operators after deploy:
#
#   oci iam group add-user \
#       --group-id $(pulumi stack output ops_group_id) \
#       --user-id <user_ocid>

ops_group: CompartmentAdminGroup = CompartmentAdminGroup(
    name="ops",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
)

app_principal.export()
oke_principal.export()
ops_group.export()

pulumi.export("app_dynamic_group_id", app_principal.dynamic_group_id)
pulumi.export("k8s_dynamic_group_id", oke_principal.dynamic_group_id)
pulumi.export("ops_group_id", ops_group.group_id)
