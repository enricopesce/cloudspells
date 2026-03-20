"""Cloud-neutral bastion abstractions for CloudSpells multi-cloud support.

Different providers implement secure shell access differently:

- OCI — `Bastion` uses the OCI Bastion Service (managed endpoint with
  ephemeral session tokens).
- AWS — AWS Systems Manager Session Manager or EC2 Instance Connect.
- GCP — Identity-Aware Proxy (IAP) TCP forwarding.

All implementations satisfy `AbstractBastion`.

Exports:
    AbstractBastion: Interface for a secure shell access mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pulumi


class AbstractBastion(ABC):
    """Interface for a provider-agnostic secure shell access mechanism.

    Provider implementations (OCI `Bastion`,
    AWS `AwsSessionManagerBastion`, GCP `GcpIapBastion`) satisfy this
    interface.

    Attributes:
        id: Provider resource ID of the bastion resource.

    Example:
        ```python
        def export_bastion(b: AbstractBastion, label: str) -> None:
            pulumi.export(f"{label}_bastion_endpoint",
                          b.get_access_endpoint())

        export_bastion(oci_bastion, "mgmt")
        ```
    """

    id: pulumi.Output[str]

    @abstractmethod
    def get_access_endpoint(self) -> pulumi.Output[str]:
        """Return the access endpoint for establishing SSH proxy sessions.

        For OCI this is the bastion's private endpoint IP.  For AWS it may
        be the SSM endpoint URL.  For GCP it is the IAP tunnel address.

        Returns:
            `pulumi.Output[str]` resolving to the endpoint address.
        """

    @abstractmethod
    def export(self) -> None:
        """Publish standard bastion stack outputs."""


__all__ = ["AbstractBastion"]
