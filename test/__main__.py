import pulumi
from blocks.vcn.network import Vcn
from typing import Dict

config = pulumi.Config()
compartment_id = config.require("compartment_ocid")
vcn_cidr_block = config.require("vcn_cidr_block")
node_shape = config.require("node_shape")
kubernetes_version = config.require("kubernetes_version")
oke_min_nodes = int(config.require("oke_min_nodes"))
node_image_id = config.require("node_image_id")
oke_ocpus = float(config.require("oke_ocpus"))
oke_memory_in_gbs = float(config.require("oke_memory_in_gbs"))
ssh_key = config.require("ssh_key")


# Create VCN
network = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack()
)

# Export important values
pulumi.export("vcn_id", network.id)
pulumi.export("public_subnet_id", network.public_subnet.id)
pulumi.export("private_subnet_id", network.private_subnet.id)


# infra = ociblocks.CreateCluster(
#     "okeinfra",
#     compartment_id=compartment_id,
#     kubernetes_version="v1.30.1",
#     shape="VM.Standard.A1.Flex",
#     cidr_block=vcn_cidr_block,
#     display_name="infra",
#     memory_in_gbs=oke_memory_in_gbs,
#     min_nodes=oke_min_nodes,
#     ocpus=oke_ocpus,
#     oke_image=node_image_id
# )

