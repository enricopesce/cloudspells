"""Internal OCI utility helpers shared across provider modules.

This module is internal to `cloudspells.providers.oci` (leading underscore).
It is not part of the public API and must not be added to the package
`__init__.py`.  Import from here using relative imports only.

Exports:
    get_svc_cidr: Return the OCI All-Services CIDR as a `pulumi.Output[str]`.
"""

from __future__ import annotations

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
        StopIteration: Propagated from `next()` inside the `apply()` callback
            if the OCI services list contains no entry whose `cidr_block`
            starts with `"all-"`.  This should not occur in a correctly
            configured tenancy, but will surface as an opaque error inside
            a Pulumi `apply()` if the services API returns unexpected data.
    """
    return oci.core.get_services_output().services.apply(
        lambda svcs: next(s.cidr_block for s in svcs if s.cidr_block.startswith("all-"))
    )
