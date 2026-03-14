"""Cloud-neutral Kubernetes abstractions for CloudBlocks multi-cloud support.

Exports:
    AbstractKubernetes: Interface for a managed Kubernetes cluster.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pulumi


class AbstractKubernetes(ABC):
    """Interface for a managed Kubernetes cluster.

    Provider implementations (OCI `OkeCluster`,
    AWS `EksCluster`, GCP `GkeCluster`) satisfy this interface.

    Attributes:
        id: Provider resource ID of the cluster.

    Example:
        ```python
        def export_cluster(cluster: AbstractKubernetes, label: str) -> None:
            pulumi.export(f"{label}_cluster_id", cluster.id)

        export_cluster(oke_cluster, "oci_k8s")
        ```
    """

    id: pulumi.Output[str]

    @abstractmethod
    def export(self) -> None:
        """Publish standard Kubernetes cluster stack outputs."""

    @abstractmethod
    def create_kubeconfig(self, filename: str) -> None:
        """Write a kubeconfig file for this cluster.

        Args:
            filename: Absolute or relative path where the kubeconfig file
                should be written (e.g. `"/tmp/kubeconfig"`).
        """


__all__ = ["AbstractKubernetes"]
