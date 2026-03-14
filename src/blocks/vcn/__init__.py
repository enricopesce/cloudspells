"""VCN building block — backward-compatibility shim.

Re-exports from `providers.oci.network`. Existing imports such as
`from blocks.vcn import Vcn` continue to work unchanged.
"""

from providers.oci.network import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
    Vcn,
    VcnRef,
    get_resources_by_tag,
)

__all__ = [
    "SUBNET_MANAGEMENT",
    "SUBNET_PRIVATE",
    "SUBNET_PUBLIC",
    "SUBNET_SECURE",
    "SubnetTier",
    "Vcn",
    "VcnRef",
    "get_resources_by_tag",
]
