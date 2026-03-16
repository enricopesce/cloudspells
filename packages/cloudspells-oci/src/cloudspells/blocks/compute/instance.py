"""Compute Instance spell — backward-compatibility shim.

Re-exports from :mod:`providers.oci.compute`.
"""

from cloudspells.providers.oci.compute import ComputeInstance

__all__ = ["ComputeInstance"]
