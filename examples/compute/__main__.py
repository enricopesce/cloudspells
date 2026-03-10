"""VCN + ComputeInstance test — deploys a single compute instance in a VCN."""

import pulumi
from blocks.vcn import Vcn, SUBNET_PUBLIC
from blocks.compute.instance import ComputeInstance

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
ssh_key: str | None = config.get("ssh_key")


# Create VCN
vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# ComputeInstance adds security rules and calls finalize_network()
web_server: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    ocpus=1,
    memory_in_gbs=4,
    os_name="ubuntu",
    subnet=SUBNET_PUBLIC
)

vcn.export()
web_server.export()
