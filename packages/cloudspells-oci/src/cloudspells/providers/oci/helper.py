"""OCI-specific utility helpers used internally by the OCI provider spells.

Keeps `pulumi_oci` imports confined to this package so that
`cloudspells.core` remains provider-agnostic.

Exports:
    `get_ads` — convert the raw availability-domain list from
    `oci.identity.get_availability_domains_output()` into the
    `placement_configs` format expected by OKE node pools.
"""

from __future__ import annotations

from typing import Any


def get_ads(
    ads: list[dict[str, Any]],
    subnet_id: str,
) -> list[dict[str, str]]:
    """Convert OCI availability-domain data into OKE placement configs.

    Transforms the raw list returned by
    `oci.identity.get_availability_domains_output()` into the format expected
    by the OKE node pool `placement_configs` argument.

    Args:
        ads: List of availability domain entries.  In production, the OCI SDK
            deserialises these into typed objects where `ad.name` is an
            attribute; in tests, plain dicts with a `"name"` key are returned.
            Both access patterns (`getattr` and `.get`) are handled internally.
        subnet_id: Subnet OCID to assign to every placement entry.

    Returns:
        List of `{"availability_domain": str, "subnet_id": str}` dicts,
        one entry per availability domain.

    Raises:
        RuntimeError: If any entry in `ads` is missing a `"name"` key.
            Verify that `oci.identity.get_availability_domains_output()`
            returns valid data for your tenancy and region.

    Example:
        ```python
        ads = [{"name": "Uocm:PHX-AD-1"}, {"name": "Uocm:PHX-AD-2"}]
        get_ads(ads, "ocid1.subnet.oc1...")
        # [{'availability_domain': 'Uocm:PHX-AD-1',
        #   'subnet_id': 'ocid1.subnet.oc1...'},
        #  {'availability_domain': 'Uocm:PHX-AD-2',
        #   'subnet_id': 'ocid1.subnet.oc1...'}]
        ```
    """
    result = []
    for ad in ads:
        ad_name = getattr(ad, "name", None) or ad.get("name")
        if not ad_name:
            raise RuntimeError(
                f"Availability domain entry is missing a 'name' key: {ad!r}. "
                "Verify that oci.identity.get_availability_domains_output() returns "
                "valid data for your tenancy and region."
            )
        result.append({"availability_domain": str(ad_name), "subnet_id": subnet_id})
    return result


__all__ = ["get_ads"]
