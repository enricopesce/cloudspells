"""OCIBlocks — backward-compatibility shim.

All existing imports (``from blocks import Vcn``, etc.) continue to work.
The canonical source for each symbol is now :mod:`providers.oci`.

For new code, import directly from :mod:`providers.oci` or from
:mod:`core.abstractions` to write cloud-neutral typed functions.
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
from providers.oci.bastion import Bastion
from providers.oci.compute import ComputeInstance
from providers.oci.kubernetes import OkeCluster
from providers.oci.network import Vcn, VcnRef
from providers.oci.volume import VolumeSpec

__all__ = [
    "Bastion",
    "ComputeInstance",
    "LoadBalancerConfig",
    "MetricScalingPolicy",
    "OciLoadBalancerConfig",
    "OkeCluster",
    "ScalableWorkload",
    "ScalingAction",
    "ScalingMetric",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
    "Vcn",
    "VcnRef",
    "VolumeSpec",
]
