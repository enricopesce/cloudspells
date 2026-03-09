"""OKE (Oracle Kubernetes Engine) building block for OCIBlocks.

Provides :class:`~blocks.oke.cluster.OkeCluster`, a high-level Pulumi
component that creates a complete OKE cluster with:

* Kubernetes control plane (``BASIC_CLUSTER`` type).
* Node pool spread across all availability domains in the region.
* OCI VCN-native pod networking (CNI type ``OCI_VCN_IP_NATIVE``).
* All required OCI security list rules automatically added to the VCN
  (API endpoint, load balancer, worker nodes, pods).

Typical usage::

    from blocks.vcn import Vcn
    from blocks.oke import OkeCluster

    vcn = Vcn(name="lab", compartment_id=compartment_id, stack_name="prod")
    cluster = OkeCluster(
        name="k8s",
        compartment_id=compartment_id,
        vcn=vcn,
        kubernetes_version="v1.30.1",
        shape="VM.Standard.E4.Flex",
        min_nodes=3,
        ocpus=2,
        memory_in_gbs=32,
        display_name="prod-k8s",
    )
"""

from .cluster import OkeCluster

__all__ = ["OkeCluster"]
