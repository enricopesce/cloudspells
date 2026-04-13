"""Internal OCI utility helpers shared across provider modules.

This module is internal to `cloudspells.providers.oci` (leading underscore).
It is not part of the public API and must not be added to the package
`__init__.py`.  Import from here using relative imports only.

Exports:
    get_svc_cidr: Return the OCI All-Services CIDR as a `pulumi.Output[str]`.
"""

from __future__ import annotations

from typing import Any

import pulumi
import pulumi_oci as oci

__all__ = ["get_svc_cidr"]


def get_svc_cidr() -> pulumi.Output[str]:
    """Return the OCI All-Services CIDR as a `pulumi.Output[str]`.

    Calls `oci.core.get_services_output()` on every invocation so that
    each Pulumi resource-construction call gets a fresh `Output` bound to
    the current Pulumi context.  Must only be called from within Pulumi
    resource construction (i.e. inside a resource `__init__` or a method
    called from it), never at module scope.

    Returns:
        `pulumi.Output[str]` containing the OCI All-Services CIDR block
        (e.g. `"all-iad-services-in-oracle-services-network"`).

    Raises:
        RuntimeError: If the OCI services list contains no entry whose
            `cidr_block` starts with `"all-"`.  This should not occur in
            a correctly configured tenancy.  Verify that your OCI provider
            credentials are valid and that `oci.core.get_services_output()`
            returns a non-empty list of services for your region.
    """

    def _find_all_services(svcs: list[Any]) -> str:
        result = next((s.cidr_block for s in svcs if s.cidr_block.startswith("all-")), None)
        if result is None:
            raise RuntimeError(
                "OCI services list contains no 'all-*' CIDR entry. "
                "Verify that your OCI provider credentials are valid and that "
                "get_services_output() returns a non-empty list for your region."
            )
        return result

    return oci.core.get_services_output().services.apply(_find_all_services)
