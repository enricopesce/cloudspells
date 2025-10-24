"""Example usage of OCIBlocks for creating VCN and OKE cluster infrastructure."""

import pulumi
from blocks.vcn.network import Vcn
from blocks.oke.cluster import OkeCluster

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
vcn_cidr_block: str = config.require("vcn_cidr_block")
node_shape: str = config.require("node_shape")
kubernetes_version: str = config.require("kubernetes_version")
oke_min_nodes: int = int(config.require("oke_min_nodes"))
node_image_id: str = config.require("node_image_id")
oke_ocpus: float = float(config.require("oke_ocpus"))
oke_memory_in_gbs: float = float(config.require("oke_memory_in_gbs"))
ssh_key: str = config.require("ssh_key")


# Create VCN (does NOT create security lists or subnets yet)
vcn_network: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack()
)

# Create OKE cluster
# OKE will add its security rules and call vcn_network.finalize_network()
# which creates the security lists and subnets
oke: OkeCluster = OkeCluster(
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

# Export important values (after OKE has finalized the network)
pulumi.export("vcn_id", vcn_network.id)
pulumi.export("public_subnet_id", vcn_network.public_subnet.id)
pulumi.export("private_subnet_id", vcn_network.private_subnet.id)
pulumi.export("cidr_block", vcn_network.cidr_block)
pulumi.export("public_subnet_cidr", vcn_network.public_subnet.cidr_block)
pulumi.export("private_subnet_cidr", vcn_network.private_subnet.cidr_block)