"""Cloud-neutral autoscaling abstractions for CloudSpells multi-cloud support.

Defines the scaling policy dataclasses and the scalable workload interface
shared across all providers.  Scaling concepts — CPU/memory thresholds and
cron-schedule-based rules — are cloud-neutral and map directly to OCI
Autoscaling Configurations, AWS Auto Scaling Groups, and GCP Managed
Instance Group autoscalers.

The base `LoadBalancerConfig` omits provider-specific bandwidth fields
(e.g. OCI flexible-shape Mbps).  Provider implementations extend it with
their own specialised subclass (e.g. `OciLoadBalancerConfig`).

Symbols defined here:

- `ScalingMetric` — enum of supported autoscaling metric types.
- `ScalingAction` — enum of scaling action kinds.
- `MetricScalingPolicy` — CPU/memory threshold-based scaling configuration.
- `ScheduleEntry` — a single cron-schedule scaling action.
- `ScheduleScalingPolicy` — schedule-based scaling configuration.
- `LoadBalancerConfig` — base cloud-neutral load balancer configuration.
- `AbstractScalableWorkload` — interface for a horizontally-scalable compute tier.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

import pulumi


class ScalingMetric(Enum):
    """Metrics available for autoscaling policies.

    Attributes:
        CPU_UTILIZATION: Scale based on average CPU utilisation (percent).
        MEMORY_UTILIZATION: Scale based on average memory utilisation (percent).
    """

    CPU_UTILIZATION = "CPU_UTILIZATION"
    MEMORY_UTILIZATION = "MEMORY_UTILIZATION"


class ScalingAction(Enum):
    """Action types for scheduled scaling policies.

    Attributes:
        CHANGE_COUNT_BY: Change the instance count by a relative delta
            (e.g. `+2` or `-1`).
        CHANGE_COUNT_TO: Set the instance count to an absolute target value.
    """

    CHANGE_COUNT_BY = "CHANGE_COUNT_BY"
    CHANGE_COUNT_TO = "CHANGE_COUNT_TO"


@dataclass
class MetricScalingPolicy:
    """Metric-based autoscaling policy configuration.

    Triggers scale-out when *scale_out_threshold* is exceeded and scale-in
    when the metric falls below *scale_in_threshold*.  Maps to OCI threshold
    autoscaling, AWS target tracking / step scaling, or GCP autoscaling
    policies.

    Attributes:
        scale_out_threshold: Percentage threshold to trigger scale-out
            (add instances).  Default: `80`.
        scale_in_threshold: Percentage threshold to trigger scale-in
            (remove instances).  Default: `20`.
        scale_out_value: Number of instances to add when scaling out.
            Default: `1`.
        scale_in_value: Number of instances to remove when scaling in
            (negative value).  Default: `-1`.
        cooldown_in_seconds: Minimum time between consecutive scaling
            actions (300-3600 s).  Default: `300`.
        metric: The metric to monitor.  Default:
            `ScalingMetric.CPU_UTILIZATION`.

    Example:
        ```python
        policy = MetricScalingPolicy(
            scale_out_threshold=70,
            scale_in_threshold=25,
            cooldown_in_seconds=600,
        )
        ```
    """

    scale_out_threshold: int = 80
    scale_in_threshold: int = 20
    scale_out_value: int = 1
    scale_in_value: int = -1
    cooldown_in_seconds: int = 300
    metric: ScalingMetric = ScalingMetric.CPU_UTILIZATION


@dataclass
class ScheduleEntry:
    """A single scheduled scaling action.

    Attributes:
        cron_expression: Quartz cron format expression in UTC
            (e.g. `"0 0 9 ? * MON-FRI *"`).
        action: `ScalingAction.CHANGE_COUNT_BY` to add or remove instances
            by a relative delta, or `ScalingAction.CHANGE_COUNT_TO` to set
            the instance count to an absolute target.
        value: Scaling magnitude.  For `CHANGE_COUNT_BY`, use a positive
            integer to add instances (e.g. `2`) or a negative integer to
            remove them (e.g. `-2`).  For `CHANGE_COUNT_TO`, use the
            desired absolute instance count (e.g. `10`).
        display_name: Human-readable label for this schedule entry.

    Example:
        ```python
        scale_up = ScheduleEntry(
            cron_expression="0 0 8 ? * MON-FRI *",
            action=ScalingAction.CHANGE_COUNT_TO,
            value=10,
            display_name="Business-hours scale-up",
        )
        ```
    """

    cron_expression: str
    action: ScalingAction
    value: int
    display_name: str


@dataclass
class ScheduleScalingPolicy:
    """Schedule-based autoscaling policy configuration.

    Attributes:
        schedules: Ordered list of `ScheduleEntry` objects
            (maximum 50 per policy on most providers).

    Example:
        ```python
        policy = ScheduleScalingPolicy(
            schedules=[
                ScheduleEntry("0 0 8 ? * MON-FRI *",
                              ScalingAction.CHANGE_COUNT_TO, 10,
                              "Scale up business hours"),
                ScheduleEntry("0 0 20 ? * MON-FRI *",
                              ScalingAction.CHANGE_COUNT_TO, 2,
                              "Scale down after hours"),
            ]
        )
        ```
    """

    schedules: list[ScheduleEntry] = field(default_factory=list)


@dataclass
class LoadBalancerConfig:
    """Base cloud-neutral load balancer configuration.

    Covers the properties that are meaningful on every major cloud
    provider.  Provider-specific subclasses add extra fields; for example
    `OciLoadBalancerConfig` adds `min_bandwidth_mbps` and `max_bandwidth_mbps`
    for OCI's flexible load-balancer shape.

    Attributes:
        backend_port: Port on backend instances to receive forwarded
            traffic and health-check probes.  Default: `80`.
        health_check_path: HTTP path for health checks.
            Default: `"/health"`.
        is_public: Whether the load balancer should have a public IP.
            This also drives subnet placement and ingress-rule topology:
            when `True` (default), the LB is placed in the public subnet
            and HTTP/HTTPS ingress is allowed from `0.0.0.0/0`; when
            `False`, the LB is placed in the private subnet and HTTP/HTTPS
            ingress is only allowed from within the VCN CIDR — no internet
            exposure.
            Default: `True`.
        ssl_certificate_name: Name of an SSL certificate for HTTPS
            termination.  When set, an HTTPS listener on port 443 is
            created in addition to HTTP on port 80.
            Default: `None` (HTTP only).

    Example:
        ```python
        lb_cfg = LoadBalancerConfig(
            backend_port=8080,
            health_check_path="/api/health",
        )
        ```
    """

    backend_port: int = 80
    health_check_path: str = "/health"
    is_public: bool = True
    ssl_certificate_name: str | None = None


class AbstractScalableWorkload(ABC):
    """Interface for a horizontally-scalable compute tier.

    Provider implementations (OCI `ScalableWorkload`, AWS
    `AwsScalableWorkload`, GCP `GcpScalableWorkload`) combine a load
    balancer, instance pool / auto scaling group, and autoscaling
    configuration behind this interface.

    Attributes:
        id: Provider resource ID of the instance pool / ASG.
        auto_generated_keys: `True` when SSH keys were auto-generated.

    Example:
        ```python
        def export_workload(wl: AbstractScalableWorkload,
                            label: str) -> None:
            pulumi.export(f"{label}_lb_ip", wl.get_load_balancer_ip())
            pulumi.export(f"{label}_pool_id", wl.get_instance_pool_id())

        export_workload(oci_pool, "web")
        ```
    """

    id: pulumi.Output[str]
    auto_generated_keys: bool

    @abstractmethod
    def get_load_balancer_ip(self) -> pulumi.Output[str]:
        """Return the public IP of the load balancer.

        Returns:
            `pulumi.Output[str]` resolving to the load balancer IP.
        """

    @abstractmethod
    def get_instance_pool_id(self) -> pulumi.Output[str]:
        """Return the provider resource ID of the instance pool.

        Returns:
            `pulumi.Output[str]` resolving to the pool resource ID.
        """

    @abstractmethod
    def get_load_balancer_id(self) -> pulumi.Output[str]:
        """Return the provider resource ID of the load balancer.

        Returns:
            `pulumi.Output[str]` resolving to the load balancer ID.
        """

    @abstractmethod
    def export(self) -> None:
        """Publish standard scalable workload stack outputs.

        Implementations must export at minimum:

        - `load_balancer_id` — provider resource ID of the load balancer.
        - `load_balancer_ip` — public IP address of the load balancer.
        - `instance_pool_id` — provider resource ID of the instance pool.
        """


__all__ = [
    "AbstractScalableWorkload",
    "LoadBalancerConfig",
    "MetricScalingPolicy",
    "ScalingAction",
    "ScalingMetric",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
