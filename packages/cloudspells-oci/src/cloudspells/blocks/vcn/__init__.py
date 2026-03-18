"""VCN spell — backward-compatibility shim.

Re-exports from `providers.oci.network`. Existing imports such as
`from blocks.vcn import Vcn` continue to work unchanged.
"""

from cloudspells.providers.oci.network import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
    Vcn,
    VcnRef,
)

__all__ = [
    "SUBNET_MANAGEMENT",
    "SUBNET_PRIVATE",
    "SUBNET_PUBLIC",
    "SUBNET_SECURE",
    "SubnetTier",
    "Vcn",
    "VcnRef",
]
