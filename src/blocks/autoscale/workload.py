"""Scalable Workload building block — backward-compatibility shim.

Re-exports from :mod:`providers.oci.autoscale`.
The ``LoadBalancerConfig`` name maps to ``OciLoadBalancerConfig`` so that
existing callers using ``LoadBalancerConfig(min_bandwidth_mbps=...)``
continue to work without modification.
"""

from providers.oci.autoscale import (  # noqa: F401
    ScalableWorkload,
    OciLoadBalancerConfig as LoadBalancerConfig,
    OciLoadBalancerConfig,
    ScalingMetric,
    ScalingAction,
    MetricScalingPolicy,
    ScheduleEntry,
    ScheduleScalingPolicy,
)

__all__ = [
    "ScalableWorkload",
    "LoadBalancerConfig",
    "OciLoadBalancerConfig",
    "ScalingMetric",
    "ScalingAction",
    "MetricScalingPolicy",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
