"""VCN + OKE test — deploys an Oracle Kubernetes Engine cluster in a VCN."""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.kubernetes import NodePoolConfig, OkeCluster
from cloudspells.providers.oci.network import Vcn

config = Config()
compartment_id: str = config.require("compartment_ocid")
kubernetes_version: str = config.require("kubernetes_version")

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
    display_name="infra",
    node_pools=[
        NodePoolConfig(
            name="default",
            shape=config.require("node_shape"),
            image=config.require("node_image_id"),
            node_count=config.require_int("node_count"),
            ocpus=config.require_float("oke_ocpus"),
            memory_in_gbs=config.require_float("oke_memory_in_gbs"),
        ),
    ],
)

vcn.export()
oke.export()

# Write kubeconfig to this directory so kubectl works without touching the
# system kubeconfig.  Use: KUBECONFIG=./kubeconfig kubectl get nodes
oke.create_kubeconfig(os.path.join(os.path.dirname(__file__), "kubeconfig"))
