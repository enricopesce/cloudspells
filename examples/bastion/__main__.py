"""VCN + private ComputeInstance + Bastion — secure SSH access to a private instance."""

import pulumi
from blocks.vcn.network import Vcn
from blocks.compute.instance import ComputeInstance
from blocks.compute.bastion import Bastion

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")

ssh_key: str | None = config.get("ssh_key")
if ssh_key == "":
    ssh_key = None

# ── 1. VCN ───────────────────────────────────────────────────────────────────
vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# ── 2. Compute instance (deployed to private subnet) ─────────────────────────
# Adds SSH ingress from public subnet → private subnet (port 22)
# Calls vcn.finalize_network() — creates subnets and security lists
instance: ComputeInstance = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    shape="VM.Standard.E4.Flex",
    ocpus=1,
    memory_in_gbs=16,
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
