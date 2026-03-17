"""VCN + OKE test — deploys an Oracle Kubernetes Engine cluster in a VCN."""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.kubernetes import OkeCluster
from cloudspells.providers.oci.network import Vcn

config = Config()
compartment_id: str = config.require("compartment_ocid")
node_shape: str = config.require("node_shape")
kubernetes_version: str = config.require("kubernetes_version")
node_image_id: str = config.require("node_image_id")
oke_min_nodes: int = config.require_int("oke_min_nodes")
oke_ocpus: float = config.require_float("oke_ocpus")
oke_memory_in_gbs: float = config.require_float("oke_memory_in_gbs")

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
    shape=node_shape,
    kubernetes_version=kubernetes_version,
    image=node_image_id,
    display_name="infra",
    memory_in_gbs=oke_memory_in_gbs,
    min_nodes=oke_min_nodes,
    ocpus=oke_ocpus,
)

vcn.export()
oke.export()

# Write kubeconfig to this directory so kubectl works without touching the
# system kubeconfig.  Use: KUBECONFIG=./kubeconfig kubectl get nodes
oke.create_kubeconfig(os.path.join(os.path.dirname(__file__), "kubeconfig"))
