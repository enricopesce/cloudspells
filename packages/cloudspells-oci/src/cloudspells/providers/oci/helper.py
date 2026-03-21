"""OCI-specific utility helpers used internally by the OCI provider spells.

Keeps `pulumi_oci` imports confined to this package so that
`cloudspells.core` remains provider-agnostic.

Exports:
    `OciHelper`: Stateless helper with two methods:

    - `resolve_image_id` — return an explicit OCID as-is, or look up the
      most recent platform image matching a friendly OS name and compute
      shape.
    - `get_ads` — convert the raw availability-domain list from
      `oci.identity.get_availability_domains()` into the
      `placement_configs` format expected by OKE node pools.
"""

from __future__ import annotations

from typing import Any, ClassVar


class OciHelper:
    """Stateless OCI utility methods used internally by provider spells.

    All methods are side-effect-free with respect to Pulumi state — they
    either return a value derived from their arguments or query the OCI
    read-only data API. Safe to call multiple times.

    Example:
        ```python
        helper = OciHelper()

        # Resolve an image OCID for a given shape
        image_id = helper.resolve_image_id(
            compartment_id="ocid1.compartment.oc1..xxx",
            shape="VM.Standard.E4.Flex",
        )

        # Build OKE placement configs from raw AD data
        import pulumi_oci as oci
        ad_result = oci.identity.get_availability_domains(compartment_id="ocid1.compartment.oc1..xxx")
        placements = helper.get_ads(
            [{"name": ad.name} for ad in ad_result.availability_domains],
            subnet_id="ocid1.subnet.oc1..yyy",
        )
        ```
    """

    # Maps friendly OS names to (operating_system, operating_system_version)
    # tuples as expected by the OCI images API.
    _OS_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "oracle": ("Oracle Linux", "8"),
        "ubuntu": ("Canonical Ubuntu", "22.04"),
        "windows": ("Windows", "Server 2022 Standard"),
    }

    def resolve_image_id(
        self,
        compartment_id: str,
        shape: str,
        image_id: str | None = None,
        os_name: str = "oracle",
    ) -> str:
        """Resolve the compute image OCID to use for an OCI instance.

        When `image_id` is provided it is returned immediately.  Otherwise
        the method queries the OCI API for the most recently created image
        matching `os_name` that is compatible with `shape`.

        Args:
            compartment_id: OCID of the compartment to search for images.
            shape: Compute shape name used to filter compatible images
                (e.g. `"VM.Standard.E4.Flex"`).
            image_id: Optional explicit image OCID.  When provided the OCI
                API is not queried and this value is returned as-is.
            os_name: Friendly OS identifier.  Supported values:

                - `"oracle"` — Oracle Linux 8 (default)
                - `"ubuntu"` — Canonical Ubuntu 22.04
                - `"windows"` — Windows Server 2022 Standard

        Returns:
            The image OCID string to use for instance creation.

        Raises:
            ValueError: If `os_name` is not one of the supported values.

        Example:
            ```python
            ocid = OciHelper().resolve_image_id(
                compartment_id="ocid1.compartment.oc1..xxx",
                shape="VM.Standard.E4.Flex",
                os_name="oracle",
            )
            ```
        """
        if image_id is not None:
            return image_id
        if os_name not in self._OS_MAP:
            supported = ", ".join(f'"{k}"' for k in self._OS_MAP)
            raise ValueError(f"Unsupported os_name {os_name!r}. Supported values: {supported}")
        operating_system, operating_system_version = self._OS_MAP[os_name]
        import pulumi_oci as oci

        images = oci.core.get_images(
            compartment_id=compartment_id,
            operating_system=operating_system,
            operating_system_version=operating_system_version,
            shape=shape,
            sort_by="TIMECREATED",
            sort_order="DESC",
        )
        return images.images[0].id

    def get_ads(
        self,
        ads: list[dict[str, Any]],
        subnet_id: str,
    ) -> list[dict[str, str]]:
        """Convert OCI availability-domain data into OKE placement configs.

        Transforms the raw list returned by
        `oci.identity.get_availability_domains()` into the format expected
        by the OKE node pool `placement_configs` argument.

        Args:
            ads: List of availability domain dictionaries, each containing
                at least a `"name"` key (e.g. `[{"name": "AD-1"}, ...]`).
            subnet_id: Subnet OCID to assign to every placement entry.

        Returns:
            List of `{"availability_domain": str, "subnet_id": str}` dicts,
            one entry per availability domain.

        Example:
            ```python
            h = OciHelper()
            ads = [{"name": "Uocm:PHX-AD-1"}, {"name": "Uocm:PHX-AD-2"}]
            h.get_ads(ads, "ocid1.subnet.oc1...")
            # [{'availability_domain': 'Uocm:PHX-AD-1',
            #   'subnet_id': 'ocid1.subnet.oc1...'},
            #  {'availability_domain': 'Uocm:PHX-AD-2',
            #   'subnet_id': 'ocid1.subnet.oc1...'}]
            ```
        """
        return [{"availability_domain": str(ad["name"]), "subnet_id": subnet_id} for ad in ads]


__all__ = ["OciHelper"]
