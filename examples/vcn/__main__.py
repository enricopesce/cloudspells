"""Standalone VCN test — deploys only a VCN with subnets and gateways."""

import pulumi
from blocks.vcn.network import Vcn

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack(),
)

# No service block to trigger finalize, so call it manually
vcn.finalize_network()

pulumi.export("vcn_id", vcn.id)
pulumi.export("cidr_block", vcn.cidr_block)

assert vcn.public_subnet is not None
assert vcn.private_subnet is not None
pulumi.export("public_subnet_id", vcn.public_subnet.id)
pulumi.export("private_subnet_id", vcn.private_subnet.id)
pulumi.export("public_subnet_cidr", vcn.public_subnet.cidr_block)
pulumi.export("private_subnet_cidr", vcn.private_subnet.cidr_block)
