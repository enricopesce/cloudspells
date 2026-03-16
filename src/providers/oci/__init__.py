"""OCI (Oracle Cloud Infrastructure) provider for CloudSpells.

Implements all abstractions from `core.abstractions` using `pulumi_oci`
resources.  This is the original and currently only fully-implemented
provider.

Available blocks:

- `Vcn`: OCI Virtual Cloud Network with four-tier subnet layout, gateways,
  route tables, and security lists.
- `VcnRef`: Read-only reference to a VCN in another Pulumi stack.
- `Nsg`: Role-based Network Security Group.  Create one per service role
  (e.g. `"load-balancer"`, `"web-backend"`, `"database"`), add rules with
  `Nsg.add_rule`, and attach to VMs via `nsg_ids`.
- `VcnFlowLogs`: VCN Flow Logs for all four subnet tiers collected under one
  Log Group dedicated to network audit.
- `OkeCluster`: Oracle Kubernetes Engine cluster.
- `ComputeInstance`: OCI VM with attached block volumes.
- `Bastion`: OCI Bastion Service endpoint.
- `ScalableWorkload`: OCI Load Balancer + Instance Pool + Autoscaling.

OCI-specific helpers:

- `VolumeSpec`: OCI block-volume descriptor with `vpus_per_gb` performance tier.
- `OciLoadBalancerConfig`: OCI load balancer configuration with flexible-shape
  bandwidth fields.
- `OciHelper`: OCI API utilities: image resolution and availability-domain
  mapping.
"""

from core.config import Config

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
from .roles import APP_SERVER, CACHE, DATABASE, INTERNET_EDGE, MANAGEMENT, Role
from .volume import VolumeSpec

__all__ = [
    # Config
    "Config",
    # Network
    "Vcn",
    "VcnRef",
    "SubnetTier",
    "SUBNET_PUBLIC",
    "SUBNET_PRIVATE",
    "SUBNET_SECURE",
    "SUBNET_MANAGEMENT",
    "get_resources_by_tag",
    # Security — NSG
    "Nsg",
    "TCP",
    "UDP",
    "ICMP",
    "ALL",
    "SVC_CIDR",
    "tcp_port",
    "tcp_port_range",
    "icmp_opts",
    # Security — Roles
    "Role",
    "INTERNET_EDGE",
    "APP_SERVER",
    "DATABASE",
    "CACHE",
    "MANAGEMENT",
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
