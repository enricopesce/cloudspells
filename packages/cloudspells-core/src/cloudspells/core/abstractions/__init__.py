"""Cloud-neutral abstractions for CloudSpells multi-cloud support.

Defines the contracts (abstract base classes and data classes) that every
cloud provider must implement.  Code typed against these interfaces works
with any provider — OCI, AWS, GCP, or future additions — without
modification.

All symbols are re-exported flat so callers import directly from this
package rather than from the individual submodules:

- **Network**: `AbstractNetwork`, `AbstractNetworkRef`, `SecurityRules`,
  `IngressRule`, `EgressRule`
- **Compute**: `AbstractCompute`, `DiskSpec`, `SubnetTier`,
  `SUBNET_PUBLIC`, `SUBNET_PRIVATE`, `SUBNET_SECURE`, `SUBNET_MANAGEMENT`
- **Roles**: `Role`, `INTERNET_EDGE`, `APP_SERVER`, `DATABASE`, `CACHE`,
  `MANAGEMENT`
- **Kubernetes**: `AbstractKubernetes`
- **Bastion**: `AbstractBastion`
- **Autoscale**: `AbstractScalableWorkload`, `LoadBalancerConfig`,
  `ScalingMetric`, `ScalingAction`, `MetricScalingPolicy`,
  `ScheduleEntry`, `ScheduleScalingPolicy`

Example:
    ```python
    from cloudspells.core.abstractions import AbstractNetwork, SubnetTier, SUBNET_PRIVATE
    ```
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
from .roles import APP_SERVER, CACHE, DATABASE, INTERNET_EDGE, MANAGEMENT, Role

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
    # roles
    "Role",
    "INTERNET_EDGE",
    "APP_SERVER",
    "DATABASE",
    "CACHE",
    "MANAGEMENT",
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
