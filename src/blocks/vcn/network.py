"""Backward-compatibility shim: re-exports from :mod:`providers.oci.network`.

All imports that previously targeted ``blocks.vcn.network`` continue to work
without modification.  New code should import directly from
``providers.oci.network``.
"""

from providers.oci.network import (  # noqa: F401
    Vcn,
    VcnRef,
    SubnetConfig,
    SubnetTier,
    SUBNET_PUBLIC,
    SUBNET_PRIVATE,
    SUBNET_SECURE,
    SUBNET_MANAGEMENT,
    get_resources_by_tag,
    _SubnetRef,
    _SecurityListRef,
)

__all__ = [
    "Vcn",
    "VcnRef",
    "SubnetConfig",
    "SubnetTier",
    "SUBNET_PUBLIC",
    "SUBNET_PRIVATE",
    "SUBNET_SECURE",
    "SUBNET_MANAGEMENT",
    "get_resources_by_tag",
]
