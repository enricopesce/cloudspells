"""Cloud-neutral compute abstractions for OCIBlocks multi-cloud support.

Defines the disk descriptor, subnet-tier constants, and the compute
interface that all provider implementations must satisfy.

Exports:
    DiskSpec: Cloud-neutral block-disk descriptor.
    SubnetTier: Type alias for subnet placement tier literals.
    SUBNET_PUBLIC, SUBNET_PRIVATE, SUBNET_SECURE, SUBNET_MANAGEMENT:
        Tier constants shared by all providers.
    AbstractCompute: Interface for a single VM with attached disks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pulumi

# ---------------------------------------------------------------------------
# Subnet tier constants
# ---------------------------------------------------------------------------

#: Type alias for the four subnet placement tiers.
SubnetTier = str

#: Public tier — load balancers and bastion hosts.  Route: internet gateway.
SUBNET_PUBLIC: SubnetTier = "public"

#: Private tier — app servers, Kubernetes nodes.  Route: NAT + service gateway.
SUBNET_PRIVATE: SubnetTier = "private"

#: Secure tier — databases, secrets.  Route: service gateway only.
SUBNET_SECURE: SubnetTier = "secure"

#: Management tier — monitoring, VPN endpoints.  Route: service gateway only.
SUBNET_MANAGEMENT: SubnetTier = "management"


# ---------------------------------------------------------------------------
# DiskSpec
# ---------------------------------------------------------------------------

@dataclass
class DiskSpec:
    """Cloud-neutral block-disk descriptor.

    Maps to OCI :class:`~providers.oci.volume.VolumeSpec` (``vpus_per_gb``),
    AWS ``EbsBlockDevice`` (``volume_type`` + IOPS), or GCP
    ``AttachedDiskInitializeParams`` (``disk_type``).

    Performance tiers map as follows:

    +-------------+------------------+--------------------------+------------------+
    | Tier        | OCI              | AWS                      | GCP              |
    +=============+==================+==========================+==================+
    | ``"low"``   | 0 VPUs/GB        | gp3 3 000 IOPS           | pd-standard      |
    | ``"balanced"``| 10 VPUs/GB    | gp3 3 000 IOPS           | pd-balanced      |
    | ``"high"``  | 20 VPUs/GB       | io2 32 000 IOPS          | pd-ssd           |
    | ``"ultra"`` | 120 VPUs/GB      | io2 64 000 IOPS          | pd-extreme       |
    +-------------+------------------+--------------------------+------------------+

    Attributes:
        size_in_gbs: Disk capacity in GiB.
        label: Logical slug used to derive the resource name suffix and to
            address the disk via :meth:`AbstractCompute.get_disk_id`.  Must
            be unique within the instance's disk list.
        performance_tier: Workload-tier hint.  Accepted values: ``"low"``,
            ``"balanced"`` (default), ``"high"``, ``"ultra"``.
        is_read_only: Mount the disk read-only.  Defaults to ``False``.

    Example::

        from core.abstractions.compute import DiskSpec

        data_disk = DiskSpec(size_in_gbs=200, label="data",
                             performance_tier="high")
        log_disk  = DiskSpec(size_in_gbs=50, label="logs")
    """

    size_in_gbs: int
    label: str = "data"
    performance_tier: str = "balanced"
    is_read_only: bool = False


# ---------------------------------------------------------------------------
# AbstractCompute
# ---------------------------------------------------------------------------

class AbstractCompute(ABC):
    """Interface for a single cloud VM with attached block disks.

    All provider compute implementations (OCI
    :class:`~providers.oci.compute.ComputeInstance`, AWS ``AwsInstance``,
    GCP ``GcpInstance``) satisfy this interface, allowing cross-cloud
    helpers and typed function signatures.

    Attributes:
        id: Provider resource ID of the instance.
        ssh_public_key: OpenSSH public key installed in
            ``~/.ssh/authorized_keys``.
        ssh_private_key: Corresponding PEM private key, or ``None`` when
            the caller supplied their own public key.
        auto_generated_keys: ``True`` when the SSH key pair was auto-generated.

    Example::

        def show_ips(vm: AbstractCompute, label: str) -> None:
            pulumi.export(f"{label}_private_ip", vm.get_private_ip())
            pulumi.export(f"{label}_id", vm.get_instance_id())

        show_ips(oci_vm,  "oci_app")
        show_ips(aws_vm,  "aws_app")
    """

    id: pulumi.Output[str]
    ssh_public_key: str
    ssh_private_key: str | None
    auto_generated_keys: bool

    @abstractmethod
    def get_private_ip(self) -> pulumi.Output[str]:
        """Return the private IP address of the instance.

        Returns:
            ``pulumi.Output[str]`` resolving to the private IP.
        """

    @abstractmethod
    def get_instance_id(self) -> pulumi.Output[str]:
        """Return the provider resource ID of the instance.

        Returns:
            ``pulumi.Output[str]`` resolving to the instance ID / OCID.
        """

    @abstractmethod
    def get_disk_id(self, label: str) -> pulumi.Output[str]:
        """Return the provider resource ID of the disk with *label*.

        Args:
            label: The ``label`` value of the target :class:`DiskSpec`.

        Returns:
            ``pulumi.Output[str]`` resolving to the disk resource ID.

        Raises:
            KeyError: If no disk with the given label exists.
        """

    @abstractmethod
    def get_ssh_public_key(self) -> str:
        """Return the SSH public key installed on the instance.

        Returns:
            OpenSSH public key string (auto-generated or caller-supplied).
        """

    @abstractmethod
    def get_ssh_private_key(self) -> str | None:
        """Return the auto-generated SSH private key, or ``None``.

        Returns:
            PEM-encoded private key when auto-generated, ``None``
            when the caller supplied their own public key.
        """

    @abstractmethod
    def export(self) -> None:
        """Publish standard compute stack outputs."""


__all__ = [
    "DiskSpec",
    "SubnetTier",
    "SUBNET_PUBLIC",
    "SUBNET_PRIVATE",
    "SUBNET_SECURE",
    "SUBNET_MANAGEMENT",
    "AbstractCompute",
]
