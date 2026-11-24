"""Private helpers for resolving the regional OCI service gateway bundle."""

from __future__ import annotations

from collections.abc import Sequence

import pulumi
import pulumi_oci as oci

__all__ = ["get_all_services"]


def get_all_services(parent: pulumi.Resource) -> pulumi.Output[oci.core.outputs.GetServicesServiceResult]:
    """Find the OCI All Services bundle in the parent resource's region.

    Args:
        parent: Resource whose OCI provider should be used for the lookup.

    Returns:
        Regional bundle providing both the service OCID and CIDR label.
    """

    def find_bundle(
        services: Sequence[oci.core.outputs.GetServicesServiceResult],
    ) -> oci.core.outputs.GetServicesServiceResult:
        for service in services:
            if service.cidr_block.startswith("all-"):
                return service
        raise RuntimeError("OCI returned no All Services bundle for the configured provider region.")

    return oci.core.get_services_output(opts=pulumi.InvokeOptions(parent=parent)).services.apply(find_bundle)
