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

:class:`VcnRef`
    Read-only proxy for a VCN that lives in a separate Pulumi stack.
    All OCIBlocks service blocks accept either ``Vcn`` or ``VcnRef``.

:class:`OkeCluster`
    Oracle Kubernetes Engine cluster with a node pool, VCN-native pod
    networking, and all required security rules.

:class:`ComputeInstance`
    Single OCI compute instance with one or more attached block volumes, each
    described by a :class:`VolumeSpec`, and optional auto-generated SSH keys.

:class:`Bastion`
    OCI Bastion Service endpoint for time-limited SSH sessions into
    private-subnet resources.

:class:`ScalableWorkload`
    Horizontally-scalable compute tier consisting of an OCI Load Balancer,
    Instance Configuration, Instance Pool, and Autoscaling Configuration.

Configuration helpers
---------------------
:class:`VolumeSpec`

:class:`LoadBalancerConfig`, :class:`MetricScalingPolicy`,
:class:`ScheduleScalingPolicy`, :class:`ScheduleEntry`,
:class:`ScalingMetric`, :class:`ScalingAction`

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

from .vcn.network import Vcn, VcnRef
from .oke.cluster import OkeCluster
from .compute.instance import ComputeInstance
from .compute.volume import VolumeSpec as VolumeSpec
from .compute.bastion import Bastion
from .autoscale.workload import ScalableWorkload, LoadBalancerConfig, MetricScalingPolicy, ScheduleScalingPolicy, ScheduleEntry, ScalingMetric, ScalingAction

__all__ = [
    "Vcn",
    "VcnRef",
    "OkeCluster",
    "ComputeInstance",
    "VolumeSpec",
    "Bastion",
    "ScalableWorkload",
    "LoadBalancerConfig",
    "MetricScalingPolicy",
    "ScheduleScalingPolicy",
    "ScheduleEntry",
    "ScalingMetric",
    "ScalingAction",
]
