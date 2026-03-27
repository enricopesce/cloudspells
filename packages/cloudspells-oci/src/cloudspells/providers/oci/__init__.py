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
- `ObjectStorageBucket`: Private OCI Object Storage bucket with secure
  defaults (no public access, standard tier).
- `BackupBucket`: Versioned Standard-tier bucket with lifecycle deletion for
  backup and disaster recovery workloads.
- `DataLakeBucket`: Standard-tier bucket with hot-to-archive-to-delete
  lifecycle for data lake and analytics workloads.
- `ArchiveBucket`: Archive-tier bucket with an immutable retention rule for
  long-term compliance and audit storage.
- `StaticWebsiteBucket`: Publicly readable Standard-tier bucket for static
  website hosting and content delivery.
- `LoadBalancer`: Internet-facing HTTPS load balancer in the VCN public
  subnet with TLS termination and automatic HTTP→HTTPS redirect.
- `InternalLoadBalancer`: Private HTTP load balancer in the VCN private
  subnet for internal service-to-service routing.

### Configuration descriptors (plain dataclasses, no cloud resources)

- `VolumeSpec`: Block-volume descriptor — size, performance tier
  (`vpus_per_gb`), label, and read-only flag.
- `OciLoadBalancerConfig`: OCI load balancer settings — listener port,
  backend port, health check path, and flexible-shape min/max bandwidth.
- `NodePoolConfig`: Configuration for a single OKE node pool — shape,
  image OCID, node count, and boot volume size. Pass one or more instances
  to `OkeCluster(node_pools=...)`.

### Autoscaling policy types

- `ScalingMetric`: Enum of supported autoscaling metrics (e.g. `CPU_UTILIZATION`).
- `ScalingAction`: Enum of autoscaling adjustment actions (e.g. `CHANGE_COUNT_BY`).
- `MetricScalingPolicy`: Metric-based autoscaling rule (threshold + action).
- `ScheduleEntry`: A single cron-based capacity adjustment.
- `ScheduleScalingPolicy`: Collection of `ScheduleEntry` items forming a
  scheduled autoscaling policy.

### Network security helpers

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
from .kubernetes import NodePoolConfig, OkeCluster
from .loadbalancer import InternalLoadBalancer, LoadBalancer
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
from .nsg import (
    ALL,
    ICMP,
    INTERNET,
    SVC_CIDR,
    TCP,
    UDP,
    Nsg,
    icmp_opts,
    tcp_port,
    tcp_port_range,
    udp_port,
    udp_port_range,
)
from .roles import APP_SERVER, CACHE, DATABASE, INTERNET_EDGE, MANAGEMENT, Role
from .storage import ArchiveBucket, BackupBucket, DataLakeBucket, ObjectStorageBucket, StaticWebsiteBucket
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
    "ICMP",
    "ALL",
    "SVC_CIDR",
    "INTERNET",
    "tcp_port",
    "tcp_port_range",
    "udp_port",
    "udp_port_range",
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
    "NodePoolConfig",
    # Compute
    "ComputeInstance",
    "VolumeSpec",
    # Bastion
    "Bastion",
    # Load Balancer
    "InternalLoadBalancer",
    "LoadBalancer",
    # Storage
    "ObjectStorageBucket",
    "BackupBucket",
    "DataLakeBucket",
    "ArchiveBucket",
    "StaticWebsiteBucket",
    # Autoscale
    "ScalableWorkload",
    "OciLoadBalancerConfig",
    "ScalingMetric",
    "ScalingAction",
    "MetricScalingPolicy",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
