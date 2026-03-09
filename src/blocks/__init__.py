"""OCIBlocks – reusable high-level building blocks for OCI infrastructure.

Each block is a ``pulumi.ComponentResource`` subclass that encapsulates
multiple OCI resources behind a simple, opinionated interface.  Blocks are
designed to be composed: a :class:`Vcn` is always constructed first; other
blocks receive it and add their security rules before the network is
finalised.

Available blocks
----------------
:class:`Vcn`
    Virtual Cloud Network with subnets, gateways, route tables, and security
    lists.  Uses a *lazy initialisation* pattern: security rules are
    accumulated by other blocks and the network is materialised only once via
    :meth:`~blocks.vcn.network.Vcn.finalize_network`.

:class:`OkeCluster`
    Oracle Kubernetes Engine cluster with a node pool, VCN-native pod
    networking, and all required security rules.

:class:`ComputeInstance`
    Single OCI compute instance (Oracle Linux 8 by default) with an attached
    block volume and optional auto-generated SSH keys.

:class:`ScalableWorkload`
    Horizontally-scalable compute tier consisting of an OCI Load Balancer,
    Instance Configuration, Instance Pool, and Autoscaling Configuration.

Quick-start example::

    import pulumi
    import pulumi_oci as oci
    from blocks import Vcn, ScalableWorkload, LoadBalancerConfig

    comp_id = oci.identity.get_compartment(...).id

    vcn = Vcn(name="app", compartment_id=comp_id, stack_name="prod")

    pool = ScalableWorkload(
        name="web",
        compartment_id=comp_id,
        vcn=vcn,
        min_instances=2,
        max_instances=10,
        load_balancer_config=LoadBalancerConfig(backend_port=8080),
    )

    pulumi.export("lb_ip", pool.get_load_balancer_ip())
"""

from .vcn.network import Vcn
from .oke.cluster import OkeCluster
from .compute.instance import ComputeInstance
from .autoscale.workload import ScalableWorkload

__all__ = [
    "Vcn",
    "OkeCluster",
    "ComputeInstance",
    "ScalableWorkload",
]
