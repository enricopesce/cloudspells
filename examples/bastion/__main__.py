"""VCN + private ComputeInstance + Bastion — secure SSH access to a private instance.

Architecture
============

.. code-block:: text

    Internet
       │  (OCI Bastion service — no public IP on instance)
       ▼
    ┌─────────────────────────────────────────────────────┐
    │ Private subnet (/17) — NAT GW + Service GW routes   │
    │  web-server  [app-nsg · APP_SERVER]                 │
    │  mgmt bastion  ← OCI Bastion service                │
    └─────────────────────────────────────────────────────┘

The ``APP_SERVER`` role places the instance in the private subnet and
auto-generates service + internet egress rules.  SSH management access is
provided entirely through the OCI Bastion service; no SSH ingress from an
upstream NSG is needed.

Configuration
-------------
Required:

    ``compartment_ocid``   OCID of the target compartment.

Optional:

    ``ssh_key``            SSH public key installed on the VM.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi

from providers.oci.bastion import Bastion
from providers.oci.compute import ComputeInstance
from providers.oci.network import Vcn
from providers.oci.nsg import Nsg
from providers.oci.roles import APP_SERVER

config: pulumi.Config = pulumi.Config()
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

# ── 3. Compute instance (private subnet inferred from APP_SERVER role) ────────

instance: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=config.get("ssh_key"),
    ocpus=1,
    memory_in_gbs=4,
    os_name="ubuntu",
    nsg=app_nsg,  # subnet=SUBNET_PRIVATE inferred from role
)

# ── 4. Bastion (OCI managed service, attached to private subnet) ──────────────
#
# Constructed after ComputeInstance so the VCN is already finalized and the
# private subnet exists. Bastion reuses the SSH rule added by ComputeInstance.

bastion: Bastion = Bastion(
    name="mgmt",
    compartment_id=compartment_id,
    vcn=vcn,
    max_session_ttl_in_seconds=10800,
    client_cidr_block_allow_list=["0.0.0.0/0"],
)

vcn.export()
instance.export()
bastion.export()

# Sessions are ephemeral (max 3 h TTL) and created on demand via the OCI CLI:
#
#   oci bastion session create-managed-ssh \
#       --bastion-id $(pulumi stack output mgmt_bastion_id) \
#       --target-resource-id $(pulumi stack output web_server_id) \
#       --target-os-username ubuntu \
#       --ssh-public-key-file ~/.ssh/id_rsa.pub
