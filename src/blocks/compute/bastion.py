"""Bastion building block — backward-compatibility shim.

Re-exports from :mod:`providers.oci.bastion`.
"""

from providers.oci.bastion import Bastion  # noqa: F401

__all__ = ["Bastion"]
