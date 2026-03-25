"""Volume specification dataclass for CloudSpells compute block volumes.

Provides `VolumeSpec`, a typed descriptor for a single OCI block volume to be
created and attached to a `ComputeInstance`.  Pass a list of specs to
`ComputeInstance(volumes=[...])` to attach multiple volumes at creation time.

`VolumeSpec` is a pure Python dataclass — it imports nothing from Pulumi
and can be constructed and validated in tests without a Pulumi context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True)  # frozen=True: descriptor is immutable after __post_init__ validates it
class VolumeSpec:
    """Descriptor for a single OCI block volume attached to a compute instance.

    Each `VolumeSpec` produces one `oci.core.Volume` and one
    `oci.core.VolumeAttachment`.  Pass a list to
    `ComputeInstance(volumes=[...])`;  the block iterates over the list and
    creates resources for every entry.

    Performance is expressed via `vpus_per_gb` using the four OCI tiers
    exposed as class-level constants.

    Attributes:
        size_in_gbs: Volume size in GiB.  Minimum 50, maximum 32,768
            (OCI block volume limit).
        label: Short slug used to derive the Pulumi resource name suffix
            (e.g. `"data"`, `"logs"`, `"db"`).  Must start with a lowercase
            letter, end with a lowercase letter or digit, and contain only
            lowercase letters, digits, or single hyphens — no trailing or
            consecutive hyphens.  Must be unique within the list passed to
            `ComputeInstance`.  Defaults to `"data"`.
        vpus_per_gb: OCI volume performance-unit tier.  Use the class
            constants `PERF_LOW` (0), `PERF_BALANCED` (10, default),
            `PERF_HIGH` (20), or `PERF_ULTRA` (120).
        is_read_only: Attach the volume read-only.  Defaults to `False`.
        device: Device path override for the paravirtualized attachment
            (e.g. `"/dev/oracleoci/oraclevdb"`).  When `None`, OCI assigns
            the next available device.
    Class Attributes:
        PERF_LOW: Low-cost tier — 0 VPUs/GB.
        PERF_BALANCED: Default balanced tier — 10 VPUs/GB.
        PERF_HIGH: High-performance tier — 20 VPUs/GB.
        PERF_ULTRA: Ultra-high-performance tier — 120 VPUs/GB.

    Raises:
        ValueError: If `size_in_gbs` is outside [50, 32768], `vpus_per_gb`
            is not a valid OCI tier, or `label` contains invalid characters.

    Example:
        ```python
        from cloudspells.providers.oci import VolumeSpec

        # Default balanced 100 GiB data volume (simplest usage)
        vol = VolumeSpec(size_in_gbs=100)

        # High-performance 500 GiB database volume with explicit device path
        db_vol = VolumeSpec(
            size_in_gbs=500,
            label="db",
            vpus_per_gb=VolumeSpec.PERF_HIGH,
            device="/dev/oracleoci/oraclevdb",
        )

        # Read-only 50 GiB reference volume
        ref_vol = VolumeSpec(size_in_gbs=50, label="ref", is_read_only=True)
        ```
    """

    # ------------------------------------------------------------------ #
    # Performance tier constants — use these instead of magic integers.   #
    # ------------------------------------------------------------------ #
    PERF_LOW: ClassVar[int] = 0
    PERF_BALANCED: ClassVar[int] = 10
    PERF_HIGH: ClassVar[int] = 20
    PERF_ULTRA: ClassVar[int] = 120

    # Valid VPU tiers — mirrors the four PERF_* constants above.
    # Declared with literal values because ClassVar defaults are evaluated
    # before the class body finishes, making PERF_* names inaccessible here.
    _VALID_VPUS: ClassVar[frozenset[int]] = frozenset({0, 10, 20, 120})

    # Label must start with a lowercase letter; may contain lowercase letters,
    # digits, or hyphens; segments separated by single hyphens (no trailing
    # or consecutive hyphens).
    _LABEL_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

    # OCI maximum block volume size in GiB.
    _MAX_SIZE_IN_GBS: ClassVar[int] = 32_768

    # ------------------------------------------------------------------ #
    # Instance fields                                                      #
    # ------------------------------------------------------------------ #
    size_in_gbs: int
    label: str = "data"
    # Default == PERF_BALANCED; field(default=...) must use a literal here
    # because ClassVar values are resolved after the class body, not during
    # it — so VolumeSpec.PERF_BALANCED is not accessible as a bare name when
    # field defaults are evaluated.
    vpus_per_gb: int = field(default=10)  # == PERF_BALANCED
    is_read_only: bool = False
    device: str | None = None

    def __post_init__(self) -> None:
        """Validate field values on construction.

        Raises:
            ValueError: If any field violates its constraint.
        """
        if self.size_in_gbs < 50:
            raise ValueError(f"size_in_gbs must be >= 50; got {self.size_in_gbs}")
        if self.size_in_gbs > self._MAX_SIZE_IN_GBS:
            raise ValueError(
                f"size_in_gbs must be <= {self._MAX_SIZE_IN_GBS} (OCI block volume limit); got {self.size_in_gbs}"
            )
        if self.vpus_per_gb not in self._VALID_VPUS:
            raise ValueError(
                f"vpus_per_gb must be one of {sorted(self._VALID_VPUS)} "
                f"(PERF_LOW=0, PERF_BALANCED=10, PERF_HIGH=20, PERF_ULTRA=120); "
                f"got {self.vpus_per_gb}"
            )
        if not self._LABEL_RE.match(self.label):
            raise ValueError(
                "label must start with a lowercase letter, end with a lowercase "
                "letter or digit, and contain only lowercase letters, digits, or "
                f"single hyphens (no trailing or consecutive hyphens); got {self.label!r}"
            )


__all__ = ["VolumeSpec"]
