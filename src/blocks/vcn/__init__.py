"""VCN building block — backward-compatibility shim.

Re-exports from :mod:`providers.oci.network`.  Existing imports such as
``from blocks.vcn import Vcn`` continue to work unchanged.
"""

from providers.oci.network import (  # noqa: F401
    Vcn,
    VcnRef,
    get_resources_by_tag,
    SUBNET_PUBLIC,
    SUBNET_PRIVATE,
    SUBNET_SECURE,
    SUBNET_MANAGEMENT,
    SubnetTier,
)

__all__ = [
    "Vcn",
    "VcnRef",
    "get_resources_by_tag",
    "SUBNET_PUBLIC",
    "SUBNET_PRIVATE",
    "SUBNET_SECURE",
    "SUBNET_MANAGEMENT",
    "SubnetTier",
]
