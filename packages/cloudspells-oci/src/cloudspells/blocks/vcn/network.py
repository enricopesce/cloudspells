"""Backward-compatibility shim: re-exports from `providers.oci.network`.

All imports that previously targeted `blocks.vcn.network` continue to work
without modification. New code should import directly from
`providers.oci.network`.
"""

from cloudspells.providers.oci.network import (  # noqa: F401
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetConfig,
    SubnetTier,
    Vcn,
    VcnRef,
    _SecurityListRef,
    _SubnetRef,
    get_resources_by_tag,
)

__all__ = [
    "SUBNET_MANAGEMENT",
    "SUBNET_PRIVATE",
    "SUBNET_PUBLIC",
    "SUBNET_SECURE",
    "SubnetConfig",
    "SubnetTier",
    "Vcn",
    "VcnRef",
    "get_resources_by_tag",
]
