"""Autoscaling spells — backward-compatibility shim.

Re-exports from `providers.oci.autoscale`.
The `LoadBalancerConfig` name maps to `OciLoadBalancerConfig` so that
existing callers using `LoadBalancerConfig(min_bandwidth_mbps=...)`
continue to work without modification.
"""

from providers.oci.autoscale import (
    MetricScalingPolicy,
    OciLoadBalancerConfig,
    ScalableWorkload,
    ScalingAction,
    ScalingMetric,
    ScheduleEntry,
    ScheduleScalingPolicy,
)
from providers.oci.autoscale import (
    OciLoadBalancerConfig as LoadBalancerConfig,
)

__all__ = [
    "LoadBalancerConfig",
    "MetricScalingPolicy",
    "OciLoadBalancerConfig",
    "ScalableWorkload",
    "ScalingAction",
    "ScalingMetric",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
