"""OCI (Oracle Cloud Infrastructure) provider for OCIBlocks.

Implements all abstractions from :mod:`core.abstractions` using
``pulumi_oci`` resources.  This is the original and currently only
fully-implemented provider.

Available blocks
----------------
:class:`~providers.oci.network.Vcn`
    OCI Virtual Cloud Network with four-tier subnet layout, gateways,
    route tables, and security lists.  Implements
    :class:`~core.abstractions.network.AbstractNetwork`.

:class:`~providers.oci.network.VcnRef`
    Read-only reference to a VCN in another Pulumi stack.  Implements
    :class:`~core.abstractions.network.AbstractNetworkRef`.

:class:`~providers.oci.nsg.Nsg`
    Role-based Network Security Group.  Create one per service role (e.g.
    ``"load-balancer"``, ``"web-backend"``, ``"database"``), add rules with
    :meth:`~providers.oci.nsg.Nsg.add_rule`, and attach to VMs via
    ``nsg_ids``.

:class:`~providers.oci.network_logging.VcnFlowLogs`
    VCN Flow Logs for all four subnet tiers collected under one Log Group
    dedicated to network audit.

:class:`~providers.oci.kubernetes.OkeCluster`
    Oracle Kubernetes Engine cluster.  Implements
    :class:`~core.abstractions.kubernetes.AbstractKubernetes`.

:class:`~providers.oci.compute.ComputeInstance`
    OCI VM with attached block volumes.  Implements
    :class:`~core.abstractions.compute.AbstractCompute`.

:class:`~providers.oci.bastion.Bastion`
    OCI Bastion Service endpoint.  Implements
    :class:`~core.abstractions.bastion.AbstractBastion`.

:class:`~providers.oci.autoscale.ScalableWorkload`
    OCI Load Balancer + Instance Pool + Autoscaling.  Implements
    :class:`~core.abstractions.autoscale.AbstractScalableWorkload`.

OCI-specific helpers
--------------------
:class:`~providers.oci.volume.VolumeSpec`
    OCI block-volume descriptor with ``vpus_per_gb`` performance tier.

:class:`~providers.oci.autoscale.OciLoadBalancerConfig`
    OCI load balancer configuration with flexible-shape bandwidth fields.

:class:`~providers.oci.helper.OciHelper`
    OCI API utilities: image resolution and availability-domain mapping.
"""

from .autoscale import (
    LoadBalancerConfig,
    MetricScalingPolicy,
    OciLoadBalancerConfig,
    ScalableWorkload,
    ScalingAction,
    ScalingMetric,
    ScheduleEntry,
    ScheduleScalingPolicy,
)
from .bastion import Bastion
from .compute import ComputeInstance
from .kubernetes import OkeCluster
from .network import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
    Vcn,
    VcnRef,
    get_resources_by_tag,
)
from .network_logging import VcnFlowLogs
from .nsg import ALL, ICMP, SVC_CIDR, TCP, UDP, Nsg, icmp_opts, tcp_port, tcp_port_range
from .volume import VolumeSpec

__all__ = [
    # Network
    "Vcn",
    "VcnRef",
    "SubnetTier",
    "SUBNET_PUBLIC",
    "SUBNET_PRIVATE",
    "SUBNET_SECURE",
    "SUBNET_MANAGEMENT",
    "get_resources_by_tag",
    # Security
    "Nsg",
    "TCP",
    "UDP",
    "ICMP",
    "ALL",
    "SVC_CIDR",
    "tcp_port",
    "tcp_port_range",
    "icmp_opts",
    # Observability
    "VcnFlowLogs",
    # Kubernetes
    "OkeCluster",
    # Compute
    "ComputeInstance",
    "VolumeSpec",
    # Bastion
    "Bastion",
    # Autoscale
    "ScalableWorkload",
    "OciLoadBalancerConfig",
    "LoadBalancerConfig",
    "ScalingMetric",
    "ScalingAction",
    "MetricScalingPolicy",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
