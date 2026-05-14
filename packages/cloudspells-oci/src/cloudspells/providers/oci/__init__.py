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
  add rules with opinionated helpers, then pass the role-bearing NSG to
  `ComputeInstance` via its required `nsg=` argument.
- `VcnFlowLogs`: Enables VCN Flow Logs for all four subnet tiers under a
  dedicated Log Group. Opt-in via `flow_logs=True` on `Vcn`.
- `OkeCluster`: Oracle Kubernetes Engine BASIC cluster with OCI_VCN_IP_NATIVE
  CNI, fixed pod/service CIDRs, and nodes spread across all availability
  domains.
- `OkeClusterEnhanced`: Oracle Kubernetes Engine ENHANCED cluster — adds OCI
  Workload Identity, cluster add-on lifecycle management, and OCI DevOps
  integration on top of `OkeCluster`.
- `ComputeInstance`: OCI VM attached through a required role-bearing NSG,
  with auto-generated SSH keys and optional attached block volumes.
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
- `ComputeInstancePrincipal`: Dynamic group and policy granting selected
  compute instances access to OCI services. Pass `instances=[...]` for
  CloudSpells-managed VMs or `instance_ids=[...]` with `compartment_id=...` for
  pre-existing VMs. Use `IamGrant` helpers or `IamGrant.raw(...)` for custom
  OCI IAM grant fragments.
- `OkeNodePrincipal`: Dynamic group and policy granting OKE node pool instances
  the full permission set required for OKE cluster operation.
- `CompartmentAdminGroup`: IAM group and policy granting human operators full
  `manage all-resources` access within a compartment.

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

- `INTERNET`: CIDR constant for internet-facing allow helpers.
- `TCP`, `UDP`, `ICMP`, `ALL`, `SVC_CIDR`: Protocol and service constants
  retained for import compatibility.

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
from .genai_agent_rag import GenAiAgentRag
from .iam import CompartmentAdminGroup, ComputeInstancePrincipal, IamGrant, OkeNodePrincipal
from .kubernetes import NodePoolConfig, OkeCluster, OkeClusterEnhanced
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
    "OkeClusterEnhanced",
    "NodePoolConfig",
    # Compute
    "ComputeInstance",
    "VolumeSpec",
    # Bastion
    "Bastion",
    # Load Balancer
    "InternalLoadBalancer",
    "LoadBalancer",
    # IAM
    "CompartmentAdminGroup",
    "ComputeInstancePrincipal",
    "IamGrant",
    "OkeNodePrincipal",
    # Generative AI
    "GenAiAgentRag",
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
