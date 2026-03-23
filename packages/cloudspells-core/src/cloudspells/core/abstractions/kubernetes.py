"""Cloud-neutral Kubernetes abstractions for CloudSpells multi-cloud support.

Defines the interface for managed Kubernetes cluster spells (OCI OKE,
AWS EKS, GCP GKE).  The abstraction covers cluster creation and kubeconfig
generation; node pool management is handled by provider-specific classes.
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
        """Publish standard Kubernetes cluster stack outputs.

        Implementations must export at minimum:

        - `cluster_id` — provider resource ID of the cluster.
        - `cluster_endpoint` — Kubernetes API server endpoint URL.
        - `kubeconfig` — kubectl-compatible kubeconfig (wrapped as a Pulumi
          secret).
        """

    @abstractmethod
    def create_kubeconfig(self, filename: str) -> None:
        """Write a kubectl-compatible kubeconfig YAML file for this cluster.

        The file is written in the standard kubeconfig format recognised by
        `kubectl`, `helm`, and other Kubernetes tooling.  The cluster endpoint,
        CA certificate, and authentication token or exec plugin are populated
        from the provider's cluster resource.

        Args:
            filename: Absolute or relative path where the kubeconfig file
                should be written (e.g. `"/tmp/kubeconfig"`).

        Raises:
            OSError: If the parent directory does not exist or the process
                lacks write permission for `filename`.
        """


__all__ = ["AbstractKubernetes"]
