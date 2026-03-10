"""Autoscaling building blocks for OCIBlocks.

Provides :class:`~blocks.autoscale.workload.ScalableWorkload` and all
supporting configuration dataclasses for creating a horizontally-scalable
OCI compute tier.

Classes
-------
:class:`~blocks.autoscale.workload.ScalableWorkload`
    Top-level component: OCI Load Balancer + Instance Pool + Autoscaling.

:class:`~blocks.autoscale.workload.LoadBalancerConfig`
    Dataclass for customising the load balancer (port, health check,
    bandwidth, optional SSL).

:class:`~blocks.autoscale.workload.MetricScalingPolicy`
    CPU- or memory-based autoscaling (threshold trigger).

:class:`~blocks.autoscale.workload.ScheduleScalingPolicy`
    Cron-schedule-based autoscaling (predictable load patterns).

:class:`~blocks.autoscale.workload.ScheduleEntry`
    A single cron schedule entry used inside :class:`ScheduleScalingPolicy`.

:class:`~blocks.autoscale.workload.ScalingMetric`
    Enum of supported autoscaling metrics (``CPU_UTILIZATION``,
    ``MEMORY_UTILIZATION``).

:class:`~blocks.autoscale.workload.ScalingAction`
    Enum of scaling action types (``CHANGE_COUNT_BY``, ``CHANGE_COUNT_TO``).

Typical usage::

    from blocks.vcn import Vcn
    from blocks.autoscale import (
        ScalableWorkload,
        LoadBalancerConfig,
        MetricScalingPolicy,
    )

    vcn = Vcn(name="app", compartment_id=compartment_id, cidr_block="10.0.0.0/16")

    pool = ScalableWorkload(
        name="web",
        compartment_id=compartment_id,
        vcn=vcn,
        min_instances=2,
        max_instances=10,
        load_balancer_config=LoadBalancerConfig(
            backend_port=8080,
            health_check_path="/api/health",
        ),
        scaling_policy=MetricScalingPolicy(
            scale_out_threshold=70,
            scale_in_threshold=25,
        ),
    )
"""

from .workload import (
    ScalableWorkload,
    ScalingMetric,
    ScalingAction,
    MetricScalingPolicy,
    ScheduleEntry,
    ScheduleScalingPolicy,
    LoadBalancerConfig,
)

__all__ = [
    "ScalableWorkload",
    "ScalingMetric",
    "ScalingAction",
    "MetricScalingPolicy",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
    "LoadBalancerConfig",
]
