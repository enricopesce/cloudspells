"""Cloud-neutral abstractions for CloudBlocks multi-cloud support.

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

from .autoscale import (
    AbstractScalableWorkload,
    LoadBalancerConfig,
    MetricScalingPolicy,
    ScalingAction,
    ScalingMetric,
    ScheduleEntry,
    ScheduleScalingPolicy,
)
from .bastion import AbstractBastion
from .compute import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    AbstractCompute,
    DiskSpec,
    SubnetTier,
)
from .kubernetes import AbstractKubernetes
from .network import (
    AbstractNetwork,
    AbstractNetworkRef,
    EgressRule,
    IngressRule,
    SecurityRules,
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
