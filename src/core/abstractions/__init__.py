"""Cloud-neutral abstractions for OCIBlocks multi-cloud support.

Defines the contracts (abstract base classes and data classes) that every
cloud provider must implement.  Blocks typed against these interfaces work
with any provider—OCI, AWS, GCP, or future additions—without modification.

Exports:
    network: AbstractNetwork, AbstractNetworkRef, SecurityRules,
        IngressRule, EgressRule.
    compute: AbstractCompute, DiskSpec, SubnetTier constants.
    kubernetes: AbstractKubernetes.
    bastion: AbstractBastion.
    autoscale: AbstractScalableWorkload, LoadBalancerConfig, ScalingMetric,
        ScalingAction, MetricScalingPolicy, ScheduleEntry,
        ScheduleScalingPolicy.
"""

from .network import (
    AbstractNetwork,
    AbstractNetworkRef,
    SecurityRules,
    IngressRule,
    EgressRule,
)
from .compute import (
    AbstractCompute,
    DiskSpec,
    SubnetTier,
    SUBNET_PUBLIC,
    SUBNET_PRIVATE,
    SUBNET_SECURE,
    SUBNET_MANAGEMENT,
)
from .kubernetes import AbstractKubernetes
from .bastion import AbstractBastion
from .autoscale import (
    AbstractScalableWorkload,
    LoadBalancerConfig,
    ScalingMetric,
    ScalingAction,
    MetricScalingPolicy,
    ScheduleEntry,
    ScheduleScalingPolicy,
)

__all__ = [
    # network
    "AbstractNetwork",
    "AbstractNetworkRef",
    "SecurityRules",
    "IngressRule",
    "EgressRule",
    # compute
    "AbstractCompute",
    "DiskSpec",
    "SubnetTier",
    "SUBNET_PUBLIC",
    "SUBNET_PRIVATE",
    "SUBNET_SECURE",
    "SUBNET_MANAGEMENT",
    # kubernetes
    "AbstractKubernetes",
    # bastion
    "AbstractBastion",
    # autoscale
    "AbstractScalableWorkload",
    "LoadBalancerConfig",
    "ScalingMetric",
    "ScalingAction",
    "MetricScalingPolicy",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
