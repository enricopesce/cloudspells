"""VCN + ComputeInstance test — deploys a single compute instance in a VCN."""

import pulumi
from blocks.vcn.network import Vcn
from blocks.compute.instance import ComputeInstance

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")

ssh_key: str | None = config.get("ssh_key")
if ssh_key == "":
    ssh_key = None

# Create VCN
vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack(),
)

# ComputeInstance adds security rules and calls finalize_network()
web_server: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
)

# VCN outputs
pulumi.export("vcn_id", vcn.id)
pulumi.export("cidr_block", vcn.cidr_block)

assert vcn.public_subnet is not None
assert vcn.private_subnet is not None
pulumi.export("public_subnet_id", vcn.public_subnet.id)
pulumi.export("private_subnet_id", vcn.private_subnet.id)

# Compute outputs
pulumi.export("web_server_id", web_server.get_instance_id())
pulumi.export("web_server_private_ip", web_server.get_private_ip())
pulumi.export("web_server_data_volume_id", web_server.get_block_volume_id())

# SSH outputs
pulumi.export("ssh_public_key", web_server.get_ssh_public_key())
if web_server.auto_generated_keys:
    pulumi.export("ssh_private_key", pulumi.Output.secret(web_server.get_ssh_private_key()))
