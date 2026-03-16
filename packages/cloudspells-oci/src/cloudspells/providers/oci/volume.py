"""Volume specification dataclass for CloudSpells compute block volumes.

Provides `VolumeSpec`, a typed descriptor for a single OCI block volume to be
created and attached to a `ComputeInstance`.  Pass a list of specs to
`ComputeInstance(volumes=[...])` to attach multiple volumes at creation time.

Exports:
    VolumeSpec: Block-volume descriptor dataclass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class VolumeSpec:
    """Descriptor for a single OCI block volume attached to a compute instance.

    Each `VolumeSpec` produces one `oci.core.Volume` and one
    `oci.core.VolumeAttachment`.  Pass a list to
    `ComputeInstance(volumes=[...])`;  the block iterates over the list and
    creates resources for every entry.

    Performance is expressed via `vpus_per_gb` using the four OCI tiers
    exposed as class-level constants.

    Attributes:
        size_in_gbs: Volume size in GiB.  Minimum 50.
        label: Short slug used to derive the Pulumi resource name suffix
            (e.g. `"data"`, `"logs"`, `"db"`).  Must start with a lowercase
            letter and contain only lowercase letters, digits, or hyphens.
            Must be unique within the list passed to `ComputeInstance`.
        vpus_per_gb: OCI volume performance-unit tier.  Use the class
            constants `PERF_LOW` (0), `PERF_BALANCED` (10, default),
            `PERF_HIGH` (20), or `PERF_ULTRA` (120).
        is_read_only: Attach the volume read-only.  Defaults to `False`.

    Class Attributes:
        PERF_LOW: Low-cost tier — 0 VPUs/GB.
        PERF_BALANCED: Default balanced tier — 10 VPUs/GB.
        PERF_HIGH: High-performance tier — 20 VPUs/GB.
        PERF_ULTRA: Ultra-high-performance tier — 120 VPUs/GB.

    Raises:
        ValueError: If `size_in_gbs` < 50, `vpus_per_gb` is not a valid
            OCI tier, or `label` contains invalid characters.

    Example:
        ```python
        from blocks.compute.volume import VolumeSpec

        # Default balanced 100 GiB data volume (simplest usage)
        vol = VolumeSpec(size_in_gbs=100)

        # High-performance 500 GiB database volume
        db_vol = VolumeSpec(
            size_in_gbs=500,
            label="db",
            vpus_per_gb=VolumeSpec.PERF_HIGH,
        )

        # Read-only 50 GiB reference volume
        ref_vol = VolumeSpec(size_in_gbs=50, label="ref", is_read_only=True)
        ```
    """

    PERF_LOW: ClassVar[int] = 0
    PERF_BALANCED: ClassVar[int] = 10
    PERF_HIGH: ClassVar[int] = 20
    PERF_ULTRA: ClassVar[int] = 120

    _VALID_VPUS: ClassVar[frozenset[int]] = frozenset({0, 10, 20, 120})
    _LABEL_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]*$")

    size_in_gbs: int
    label: str = "data"
    vpus_per_gb: int = 10  # PERF_BALANCED
    is_read_only: bool = False

    def __post_init__(self) -> None:
        """Validate field values on construction.

        Raises:
            ValueError: If any field violates its constraint.
        """
        if self.size_in_gbs < 50:
            raise ValueError(f"size_in_gbs must be >= 50; got {self.size_in_gbs}")
        if self.vpus_per_gb not in self._VALID_VPUS:
            raise ValueError(
                f"vpus_per_gb must be one of {sorted(self._VALID_VPUS)} "
                f"(PERF_LOW=0, PERF_BALANCED=10, PERF_HIGH=20, PERF_ULTRA=120); "
                f"got {self.vpus_per_gb}"
            )
        if not self._LABEL_RE.match(self.label):
            raise ValueError(
                f"label must start with a lowercase letter and contain only "
                f"lowercase letters, digits, or hyphens; got {self.label!r}"
            )


__all__ = ["VolumeSpec"]
