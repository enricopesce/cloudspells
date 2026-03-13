"""OKE building block — backward-compatibility shim.

Re-exports from :mod:`providers.oci.kubernetes`.
"""

from providers.oci.kubernetes import OkeCluster

__all__ = ["OkeCluster"]
