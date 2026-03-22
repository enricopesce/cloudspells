"""VCN + private ComputeInstance + Bastion — secure SSH access to a private instance.

## Architecture

```
Internet
   │  (OCI Bastion service — no public IP on instance)
   ▼
┌─────────────────────────────────────────────────────┐
│ Private subnet (/17) — NAT GW + Service GW routes   │
│  web-server  [app-nsg · APP_SERVER]                 │
│  mgmt bastion  ← OCI Bastion service                │
└─────────────────────────────────────────────────────┘
```

The `APP_SERVER` role places the instance in the private subnet and
auto-generates service + internet egress rules.  SSH management access is
provided entirely through the OCI Bastion service; no SSH ingress from an
upstream NSG is needed.

## Configuration

Required:

- `compartment_ocid` — OCID of the target compartment.

Optional:

- `ssh_key` — SSH public key installed on the VM.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.bastion import Bastion
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

config = Config()
compartment_id: str = config.require("compartment_ocid")

# ── 1. VCN ───────────────────────────────────────────────────────────────────

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# ── 2. NSG role ───────────────────────────────────────────────────────────────
#
# APP_SERVER: private subnet, egress to Oracle Services + internet via NAT GW.
# No serves() relationship needed — SSH arrives through the OCI Bastion service,
# not from an upstream NSG.

app_nsg: Nsg = Nsg(
    "app-server",
    role=APP_SERVER,
    vcn=vcn,
    compartment_id=compartment_id,
)

# ── 3. Bastion (OCI managed service, attached to private subnet) ──────────────
#
# Constructed before ComputeInstance so its SSH rule (0.0.0.0/0 → port 22 on
# the private security list) is registered before finalize_network() is called.
# OCI Bastion sessions originate from randomly-assigned managed IPs, so the
# rule must allow 0.0.0.0/0 — the public-subnet-CIDR rule that ComputeInstance
# would add is not sufficient.

bastion: Bastion = Bastion(
    name="mgmt",
    compartment_id=compartment_id,
    vcn=vcn,
    max_session_ttl_in_seconds=10800,
    client_cidr_block_allow_list=["0.0.0.0/0"],
)

# ── 4. Compute instance (private subnet inferred from APP_SERVER role) ────────
#
# ComputeInstance triggers finalize_network(). Bastion must come first (above).

instance: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    image_id=config.require("image_ocid"),
    ssh_public_key=config.get("ssh_key"),
    ocpus=1,
    memory_in_gbs=4,
    nsg=app_nsg,  # subnet=SUBNET_PRIVATE inferred from role
)

vcn.export()
bastion.export()
instance.export()

# Sessions are ephemeral (max 3 h TTL) and created on demand via the OCI CLI:
#
#   oci bastion session create-managed-ssh \
#       --bastion-id $(pulumi stack output mgmt_bastion_id) \
#       --target-resource-id $(pulumi stack output web_server_id) \
#       --target-os-username ubuntu \
#       --ssh-public-key-file ~/.ssh/id_rsa.pub
