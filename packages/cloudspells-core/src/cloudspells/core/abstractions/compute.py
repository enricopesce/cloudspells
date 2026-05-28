"""Cloud-neutral compute abstractions for CloudSpells multi-cloud support.

Defines the disk descriptor, subnet-tier constants, and the compute
interface that all provider implementations must satisfy.

Symbols defined here:

- `DiskSpec` — cloud-neutral block-disk descriptor.
- `SubnetTier` — type alias for subnet placement tier literals.
- `SUBNET_PUBLIC`, `SUBNET_PRIVATE`, `SUBNET_SECURE`, `SUBNET_MANAGEMENT`
  — tier constants shared by all providers.
- `AbstractCompute` — interface for a single VM with attached disks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import pulumi

from .tiers import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
)

# ---------------------------------------------------------------------------
# DiskSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiskSpec:
    """Cloud-neutral block-disk descriptor.

    Maps to OCI `VolumeSpec` (`vpus_per_gb`),
    AWS `EbsBlockDevice` (`volume_type` + IOPS), or GCP
    `AttachedDiskInitializeParams` (`disk_type`).

    Performance tiers map as follows:

    | Tier         | OCI          | AWS               | GCP         |
    |--------------|--------------|-------------------|-------------|
    | `"low"`      | 0 VPUs/GB    | gp3 3 000 IOPS    | pd-standard |
    | `"balanced"` | 10 VPUs/GB   | gp3 3 000 IOPS    | pd-balanced |
    | `"high"`     | 20 VPUs/GB   | io2 32 000 IOPS   | pd-ssd      |
    | `"ultra"`    | 120 VPUs/GB  | io2 64 000 IOPS   | pd-extreme  |

    Attributes:
        size_in_gbs: Disk capacity in GiB.
        label: Logical slug used by provider implementations for lookup
            helpers, outputs, and tags. Must be unique within the instance's
            disk list.
        performance_tier: Workload-tier hint.  Accepted values: `"low"`,
            `"balanced"` (default), `"high"`, `"ultra"`.  Pyright enforces
            valid values at call sites via the `Literal` type annotation.
        is_read_only: Mount the disk read-only.  Defaults to `False`.

    Example:
        ```python
        from cloudspells.core.abstractions.compute import DiskSpec

        data_disk = DiskSpec(size_in_gbs=200, label="data",
                             performance_tier="high")
        log_disk  = DiskSpec(size_in_gbs=50, label="logs")
        ```
    """

    size_in_gbs: int
    label: str = "data"
    performance_tier: Literal["low", "balanced", "high", "ultra"] = "balanced"
    is_read_only: bool = False


# ---------------------------------------------------------------------------
# AbstractCompute
# ---------------------------------------------------------------------------


class AbstractCompute(ABC):
    """Interface for a single cloud VM with attached block disks.

    All provider compute implementations (OCI `ComputeInstance`, AWS `AwsInstance`,
    GCP `GcpInstance`) satisfy this interface, allowing cross-cloud
    helpers and typed function signatures.

    Attributes:
        id: Provider resource ID of the instance.
        ssh_public_key: OpenSSH public key input installed in
            `~/.ssh/authorized_keys`.
        ssh_private_key: Corresponding PEM private key output, or `None`
            when the caller supplied their own public key.
        auto_generated_keys: `True` when the SSH key pair was auto-generated.

    Example:
        ```python
        def show_ips(vm: AbstractCompute, label: str) -> None:
            pulumi.export(f"{label}_private_ip", vm.get_private_ip())
            pulumi.export(f"{label}_id", vm.get_instance_id())

        show_ips(oci_vm,  "oci_app")
        show_ips(aws_vm,  "aws_app")
        ```
    """

    id: pulumi.Output[str]
    ssh_public_key: pulumi.Input[str]
    ssh_private_key: pulumi.Output[str] | None
    auto_generated_keys: bool

    @abstractmethod
    def get_private_ip(self) -> pulumi.Output[str]:
        """Return the private IP address of the instance.

        Returns:
            `pulumi.Output[str]` resolving to the private IP.
        """

    @abstractmethod
    def get_instance_id(self) -> pulumi.Output[str]:
        """Return the provider resource ID of the instance.

        Returns:
            `pulumi.Output[str]` resolving to the instance ID / OCID.
        """

    @abstractmethod
    def get_disk_id(self, label: str) -> pulumi.Output[str]:
        """Return the provider resource ID of the disk with the given label.

        Args:
            label: The `label` value of the target `DiskSpec`.

        Returns:
            `pulumi.Output[str]` resolving to the disk resource ID.

        Raises:
            KeyError: If no disk with the given label exists.
        """

    @abstractmethod
    def get_ssh_public_key(self) -> pulumi.Input[str]:
        """Return the SSH public key installed on the instance.

        Returns:
            OpenSSH public key input (auto-generated or caller-supplied).
        """

    @abstractmethod
    def get_ssh_private_key(self) -> pulumi.Output[str] | None:
        """Return the auto-generated SSH private key, or `None`.

        Returns:
            PEM-encoded private key output when auto-generated, `None`
            when the caller supplied their own public key.
        """

    @abstractmethod
    def export(self) -> None:
        """Publish standard compute stack outputs.

        Implementations must export at minimum:

        - `instance_id` — provider resource ID of the instance.
        - `private_ip` — private IP address of the instance.
        - `ssh_public_key` — OpenSSH public key (wrapped as a Pulumi secret).
        - `ssh_private_key` — PEM private key when auto-generated (wrapped as
          a Pulumi secret); omitted when the caller supplied their own key.
        """


__all__ = [
    "SUBNET_MANAGEMENT",
    "SUBNET_PRIVATE",
    "SUBNET_PUBLIC",
    "SUBNET_SECURE",
    "AbstractCompute",
    "DiskSpec",
    "SubnetTier",
]
