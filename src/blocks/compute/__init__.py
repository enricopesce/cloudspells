"""Compute building blocks — backward-compatibility shim.

Re-exports from :mod:`providers.oci`.
"""

from providers.oci.bastion import Bastion
from providers.oci.compute import ComputeInstance
from providers.oci.volume import VolumeSpec

__all__ = ["Bastion", "ComputeInstance", "VolumeSpec"]
