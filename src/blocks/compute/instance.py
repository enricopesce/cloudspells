"""Compute Instance spell — backward-compatibility shim.

Re-exports from :mod:`providers.oci.compute`.
"""

from providers.oci.compute import ComputeInstance

__all__ = ["ComputeInstance"]
