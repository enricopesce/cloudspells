"""OKE spell — backward-compatibility shim.

Re-exports from :mod:`providers.oci.kubernetes`.
"""

from cloudspells.providers.oci.kubernetes import OkeCluster

__all__ = ["OkeCluster"]
