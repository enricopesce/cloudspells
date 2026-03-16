"""CloudSpells — backward-compatibility shim.

All existing imports (`from blocks import Vcn`, etc.) continue to work.
The canonical source for each symbol is now `providers.oci`.

For new code, import directly from `providers.oci` or from
`core.abstractions` to write cloud-neutral typed functions.
"""

from cloudspells.core.config import Config
from cloudspells.providers.oci.autoscale import (
    MetricScalingPolicy,
    OciLoadBalancerConfig,
    ScalableWorkload,
    ScalingAction,
    ScalingMetric,
    ScheduleEntry,
    ScheduleScalingPolicy,
)
from cloudspells.providers.oci.autoscale import (
    OciLoadBalancerConfig as LoadBalancerConfig,
)
from cloudspells.providers.oci.bastion import Bastion
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.kubernetes import OkeCluster
from cloudspells.providers.oci.network import Vcn, VcnRef
from cloudspells.providers.oci.volume import VolumeSpec

__all__ = [
    "Bastion",
    "ComputeInstance",
    "Config",
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
