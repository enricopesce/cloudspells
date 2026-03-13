"""Compute Instance building block — backward-compatibility shim.

Re-exports from :mod:`providers.oci.compute`.
"""

from providers.oci.compute import ComputeInstance  # noqa: F401

__all__ = ["ComputeInstance"]
