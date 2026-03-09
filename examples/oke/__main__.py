"""VCN + OKE test — deploys an Oracle Kubernetes Engine cluster in a VCN."""

import pulumi
from blocks.vcn.network import Vcn
from blocks.oke.cluster import OkeCluster

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
node_shape: str = config.require("node_shape")
kubernetes_version: str = config.require("kubernetes_version")
oke_min_nodes: int = int(config.require("oke_min_nodes"))
node_image_id: str = config.require("node_image_id")
oke_ocpus: float = float(config.require("oke_ocpus"))
oke_memory_in_gbs: float = float(config.require("oke_memory_in_gbs"))

# Create VCN
vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# OkeCluster adds security rules and calls finalize_network()
oke: OkeCluster = OkeCluster(
    name="okeinfra",
    compartment_id=compartment_id,
    vcn=vcn,
    kubernetes_version=kubernetes_version,
    shape=node_shape,
    image=node_image_id if node_image_id else None,
    display_name="infra",
    memory_in_gbs=oke_memory_in_gbs,
    min_nodes=oke_min_nodes,
    ocpus=oke_ocpus,
)

vcn.export()
oke.export()
