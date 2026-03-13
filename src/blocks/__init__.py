"""OCIBlocks — backward-compatibility shim.

All existing imports (``from blocks import Vcn``, etc.) continue to work.
The canonical source for each symbol is now :mod:`providers.oci`.

For new code, import directly from :mod:`providers.oci` or from
:mod:`core.abstractions` to write cloud-neutral typed functions.
"""

from providers.oci.network import Vcn, VcnRef  # noqa: F401
from providers.oci.kubernetes import OkeCluster  # noqa: F401
from providers.oci.compute import ComputeInstance  # noqa: F401
from providers.oci.volume import VolumeSpec  # noqa: F401
from providers.oci.bastion import Bastion  # noqa: F401
from providers.oci.autoscale import (  # noqa: F401
    ScalableWorkload,
    OciLoadBalancerConfig as LoadBalancerConfig,
    OciLoadBalancerConfig,
    MetricScalingPolicy,
    ScheduleScalingPolicy,
    ScheduleEntry,
    ScalingMetric,
    ScalingAction,
)

__all__ = [
    "Vcn",
    "VcnRef",
    "OkeCluster",
    "ComputeInstance",
    "VolumeSpec",
    "Bastion",
    "ScalableWorkload",
    "LoadBalancerConfig",
    "OciLoadBalancerConfig",
    "MetricScalingPolicy",
    "ScheduleScalingPolicy",
    "ScheduleEntry",
    "ScalingMetric",
    "ScalingAction",
]
