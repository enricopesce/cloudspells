"""OCI-specific utility helpers used internally by the OCI provider spells.

Keeps `pulumi_oci` imports confined to this package so that
`cloudspells.core` remains provider-agnostic.

Exports:
    `OciHelper`: Stateless helper with one method:

    - `get_ads` — convert the raw availability-domain list from
      `oci.identity.get_availability_domains()` into the
      `placement_configs` format expected by OKE node pools.
"""

from __future__ import annotations

from typing import Any


class OciHelper:
    """Stateless OCI utility methods used internally by provider spells.

    Example:
        ```python
        import pulumi_oci as oci
        helper = OciHelper()
        ad_result = oci.identity.get_availability_domains(compartment_id="ocid1.compartment.oc1..xxx")
        placements = helper.get_ads(
            [{"name": ad.name} for ad in ad_result.availability_domains],
            subnet_id="ocid1.subnet.oc1..yyy",
        )
        ```
    """

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
