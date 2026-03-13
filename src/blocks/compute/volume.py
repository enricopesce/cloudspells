"""VolumeSpec — backward-compatibility shim.

Re-exports from :mod:`providers.oci.volume`.
"""

from providers.oci.volume import VolumeSpec  # noqa: F401

__all__ = ["VolumeSpec"]
