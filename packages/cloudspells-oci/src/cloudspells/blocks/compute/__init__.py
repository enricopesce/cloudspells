"""Compute spells — backward-compatibility shim.

Re-exports from :mod:`providers.oci`.
"""

from cloudspells.providers.oci.bastion import Bastion
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.volume import VolumeSpec

__all__ = ["Bastion", "ComputeInstance", "VolumeSpec"]
