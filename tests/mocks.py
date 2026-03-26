"""Shared Pulumi mocks for OCI resources.

Provides `OCIMocks` (a `pulumi.runtime.Mocks` implementation) and the
`set_mocks()` helper that activates it.  Every test file must call
`set_mocks()` before importing any infrastructure module so that the OCI
provider is intercepted before any resource is registered.

Mocked resource types and their injected computed outputs:

| Resource type | Injected outputs |
|---|---|
| `oci:Core/vcn:Vcn` | `defaultRouteTableId`, `defaultSecurityListId` |
| `oci:Core/subnet:Subnet` | `id` |
| `oci:Core/instance:Instance` | `privateIp`, `publicIp` |
| `oci:Core/volume:Volume` | `id` |
| `oci:LoadBalancer/loadBalancer:LoadBalancer` | `ipAddressDetails` |
| `oci:Bastion/bastion:Bastion` | `privateEndpointIpAddress` |
| `oci:ObjectStorage/bucket:Bucket` | `name` |

Mocked provider call tokens:

- `oci:Core/getServices:getServices`
- `oci:Core/getImages:getImages`
- `oci:Identity/getAvailabilityDomains:getAvailabilityDomains`
"""

from __future__ import annotations

from typing import Any

import pulumi


class OCIMocks(pulumi.runtime.Mocks):
    """Mock OCI provider calls and resource creation for unit tests.

    Intercepts every `new_resource` and `call` invocation that Pulumi makes
    during a test run and returns deterministic fake values so tests never
    require a live OCI account or network access.

    Example:
        ```python
        from tests.mocks import set_mocks
        set_mocks()  # must come before any infrastructure import

        from cloudspells.providers.oci.network import Vcn
        ```
    """

    def new_resource(self, args: pulumi.runtime.MockResourceArgs) -> tuple[str | None, dict[Any, Any]]:
        """Mock resource creation.

        Called by the Pulumi test runner for every resource registered during a
        `@pulumi.runtime.test` run.  Returns a deterministic resource ID and an
        output dictionary pre-populated with the resource's input values plus any
        provider-computed fields injected by `_inject_computed_outputs`.

        Args:
            args: Mock resource arguments including `args.name`, `args.typ`,
                and `args.inputs`.

        Returns:
            A two-tuple of `(resource_id, outputs)` where `resource_id` is
            `"{args.name}-id"` and `outputs` is inputs merged with computed
            fields.
        """
        outputs = args.inputs.copy()
        self._inject_computed_outputs(args, outputs)
        return (f"{args.name}-id", outputs)

    def _inject_computed_outputs(self, args: pulumi.runtime.MockResourceArgs, outputs: dict[Any, Any]) -> None:
        """Inject provider-computed output fields for each mocked resource type.

        OCI resources expose read-only attributes that the provider computes at
        apply time.  Without these injections `@pulumi.runtime.test` coroutines
        that read those attributes hang indefinitely waiting for a value that
        never resolves.

        Args:
            args: The mock resource arguments supplied by the Pulumi test runner.
            outputs: Mutable dict pre-populated with the resource's input values;
                computed outputs are added in-place.
        """
        typ = args.typ

        # ── Core ──────────────────────────────────────────────────────────────
        if typ == "oci:Core/vcn:Vcn":
            outputs["defaultRouteTableId"] = f"{args.name}-default-rt-id"
            outputs["defaultSecurityListId"] = f"{args.name}-default-sl-id"
        elif typ == "oci:Core/subnet:Subnet":
            outputs["id"] = f"{args.name}-id"
        elif typ == "oci:Core/instance:Instance":
            outputs["privateIp"] = "10.0.128.10"
            outputs["publicIp"] = None
        elif typ == "oci:Core/volume:Volume":
            outputs["id"] = f"{args.name}-id"

        # ── Load Balancer ─────────────────────────────────────────────────────
        elif typ == "oci:LoadBalancer/loadBalancer:LoadBalancer":
            outputs["ipAddressDetails"] = [{"ipAddress": "10.0.0.100", "isPublic": True}]
        elif typ in (
            "oci:LoadBalancer/backendSet:BackendSet",
            "oci:LoadBalancer/ruleSet:RuleSet",
            "oci:LoadBalancer/listener:Listener",
        ):
            outputs["name"] = args.inputs.get("name", args.name)

        # ── Bastion ───────────────────────────────────────────────────────────
        elif typ == "oci:Bastion/bastion:Bastion":
            outputs["privateEndpointIpAddress"] = "10.0.128.5"

        # ── Object Storage ────────────────────────────────────────────────────
        elif typ == "oci:ObjectStorage/bucket:Bucket":
            outputs["name"] = args.name
        elif typ in (
            "oci:ObjectStorage/objectLifecyclePolicy:ObjectLifecyclePolicy",
            "oci:Logging/logGroup:LogGroup",
            "oci:Logging/log:Log",
        ):
            outputs["id"] = f"{args.name}-id"

    def call(self, args: pulumi.runtime.MockCallArgs) -> tuple[dict[Any, Any], list[tuple[str, str]]]:
        """Mock OCI provider function calls (invoke operations).

        Intercepts `oci:Core/getServices`, `oci:Identity/getAvailabilityDomains`,
        and any other OCI data-source lookups so that tests run without a real
        OCI tenancy.

        Args:
            args: Pulumi mock call arguments containing the provider token and
                input values.

        Returns:
            A `(outputs, failures)` tuple.  `outputs` is a dict of mocked
            return values; `failures` is an empty list (no simulated errors).
        """

        # Mock get_services (for Service Gateway)
        if args.token == "oci:Core/getServices:getServices":
            return (
                {
                    "services": [
                        {
                            "id": "mock-all-services-id",
                            "name": "All FRA Services In Oracle Services Network",
                            "cidrBlock": "all-fra-services-in-oracle-services-network",
                        }
                    ]
                },
                [],
            )

        # Mock get_availability_domains
        if args.token == "oci:Identity/getAvailabilityDomains:getAvailabilityDomains":
            return (
                {
                    "availabilityDomains": [
                        {"name": "AD-1", "id": "mock-ad-1-id"},
                        {"name": "AD-2", "id": "mock-ad-2-id"},
                        {"name": "AD-3", "id": "mock-ad-3-id"},
                    ]
                },
                [],
            )

        return ({}, [])


def set_mocks():
    """Set up Pulumi mocks for testing."""
    pulumi.runtime.set_mocks(OCIMocks(), project="unittest", stack="unittest", preview=False)
