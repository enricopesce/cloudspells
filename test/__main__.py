import pulumi
from blocks.vcn.network import Vcn
from blocks.oke.cluster import OkeCluster
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
vcn_network = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack()
)

# # Export important values
pulumi.export("vcn_id", vcn_network.id)
pulumi.export("public_subnet_id", vcn_network.public_subnet.id)
pulumi.export("private_subnet_id", vcn_network.private_subnet.id)
pulumi.export("cidr_block", vcn_network.cidr_block)
pulumi.export("public_subnet_cidr", vcn_network.public_subnet.cidr_block)
pulumi.export("private_subnet_cidr", vcn_network.private_subnet.cidr_block)

# create custom security lists using vcn object

oke = OkeCluster(
    "okeinfra",
    compartment_id=compartment_id,
    vcn=vcn_network,
    kubernetes_version="v1.31.1",
    shape="VM.Standard.A1.Flex",
    image="ocid1.image.oc1.eu-frankfurt-1.aaaaaaaahn6vygfxr6e5rzxbnz3kjrkey3mdwfjjctcjs4nb5dn7ba2cgdka",
    display_name="infra",
    memory_in_gbs=oke_memory_in_gbs,
    min_nodes=oke_min_nodes,
    ocpus=oke_ocpus,
    stack_name=pulumi.get_stack()
)