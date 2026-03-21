"""OCI (Oracle Cloud Infrastructure) provider for CloudSpells.

Implements all abstractions from `cloudspells.core.abstractions` using
`pulumi_oci` resources. This is the original and currently only
fully-implemented provider.

**Infrastructure spells** (create live cloud resources):

- `Vcn`: OCI Virtual Cloud Network with a four-tier subnet layout, all
  gateways, route tables, and security lists baked in.
- `VcnRef`: Read-only handle to a `Vcn` owned by another Pulumi stack.
  Accepts the same subnet CIDR accessors as `Vcn`.
- `Nsg`: Role-based Network Security Group. Create one per service role,
  add rules with `Nsg.add_rule`, then attach to resources via `nsg_ids`.
- `VcnFlowLogs`: Enables VCN Flow Logs for all four subnet tiers under a
  dedicated Log Group. Opt-in via `flow_logs=True` on `Vcn`.
- `OkeCluster`: Oracle Kubernetes Engine cluster (BASIC or ENHANCED) with
  OCI_VCN_IP_NATIVE CNI, fixed pod/service CIDRs, and nodes spread across
  all availability domains.
- `ComputeInstance`: OCI VM with auto-generated SSH keys and optional
  attached block volumes.
- `Bastion`: OCI Bastion Service endpoint in the private subnet.
- `ScalableWorkload`: OCI Load Balancer in the public subnet backed by an
  Instance Pool in the private subnet with CPU autoscaling.

**Configuration descriptors** (plain dataclasses, no cloud resources):

- `VolumeSpec`: Block-volume descriptor — size, performance tier
  (`vpus_per_gb`), label, and read-only flag.
- `LoadBalancerConfig`: Cloud-neutral load balancer settings (listener
  port, backend port, health check path).
- `OciLoadBalancerConfig`: OCI-specific extension of `LoadBalancerConfig`
  adding flexible-shape min/max bandwidth.
- `NodePoolConfig`: Configuration for a single OKE node pool — shape,
  image OCID, node count, and boot volume size. Pass one or more instances
  to `OkeCluster(node_pools=...)`.

**Autoscaling policy types**:

- `ScalingMetric`: Enum of supported autoscaling metrics (e.g. `CPU_UTILIZATION`).
- `ScalingAction`: Enum of autoscaling adjustment actions (e.g. `CHANGE_COUNT_BY`).
- `MetricScalingPolicy`: Metric-based autoscaling rule (threshold + action).
- `ScheduleEntry`: A single cron-based capacity adjustment.
- `ScheduleScalingPolicy`: Collection of `ScheduleEntry` items forming a
  scheduled autoscaling policy.

**Network security helpers**:

- `TCP`, `UDP`, `ALL`: Protocol constants for NSG rules.
- `SVC_CIDR`: Sentinel used in NSG rules to target the OCI Services CIDR.
- `tcp_port`: Build a single-port TCP NSG rule destination.
- `tcp_port_range`: Build a port-range TCP NSG rule destination.

**Role constants** (use with `Nsg` to express intent):

- `INTERNET_EDGE`, `APP_SERVER`, `DATABASE`, `CACHE`, `MANAGEMENT`: Pre-defined
  `Role` values. Pass to `Nsg(role=...)` to name the security group by its
  architectural purpose.

**Subnet tier constants**:

- `SUBNET_PUBLIC`, `SUBNET_PRIVATE`, `SUBNET_SECURE`, `SUBNET_MANAGEMENT`:
  `SubnetTier` enum members. Pass to spell constructors that accept a
  `subnet_tier` parameter to control which subnet tier a resource lands in.
"""

from cloudspells.core.config import Config

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
)
from .network_logging import VcnFlowLogs
from .nsg import ALL, SVC_CIDR, TCP, UDP, Nsg, tcp_port, tcp_port_range
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
    # Security — NSG
    "Nsg",
    "TCP",
    "UDP",
    "ALL",
    "SVC_CIDR",
    "tcp_port",
    "tcp_port_range",
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
