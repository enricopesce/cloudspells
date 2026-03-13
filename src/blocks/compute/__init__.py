"""Compute building blocks — backward-compatibility shim.

Re-exports from :mod:`providers.oci`.
"""

from providers.oci.compute import ComputeInstance  # noqa: F401
from providers.oci.bastion import Bastion  # noqa: F401
from providers.oci.volume import VolumeSpec  # noqa: F401

__all__ = ["ComputeInstance", "Bastion", "VolumeSpec"]
