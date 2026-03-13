"""VCN + private ComputeInstance + Bastion — secure SSH access to a private instance."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi
from providers.oci.network import Vcn
from providers.oci.compute import ComputeInstance
from providers.oci.bastion import Bastion
from providers.oci import SUBNET_PRIVATE

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")

# ── 1. VCN ───────────────────────────────────────────────────────────────────
vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# ── 2. Compute instance (deployed to private subnet) ─────────────────────────
instance: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=config.get("ssh_key"),
    ocpus=1,
    memory_in_gbs=4,
    os_name="ubuntu",
    subnet=SUBNET_PRIVATE
)

# ── 3. Bastion (OCI managed service, attached to private subnet) ──────────────
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
