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
| `oci:Core/internetGateway:InternetGateway` | `id` |
| `oci:Core/natGateway:NatGateway` | `id` |
| `oci:Core/serviceGateway:ServiceGateway` | `id` |
| `oci:Core/drg:Drg` | `id` |
| `oci:Core/drgAttachment:DrgAttachment` | `id` |
| `oci:Core/routeTable:RouteTable` | `id` |
| `oci:Core/securityList:SecurityList` | `id` |
| `oci:Core/defaultSecurityList:DefaultSecurityList` | `id` |
| `oci:Core/networkSecurityGroup:NetworkSecurityGroup` | `id` |
| `oci:Core/networkSecurityGroupSecurityRule:NetworkSecurityGroupSecurityRule` | `id` |
| `oci:Core/instance:Instance` | `privateIp`, `publicIp` |
| `pulumi-python:dynamic/cloudspells:SshKeyPair` | `publicKey`, `privateKey` |
| `oci:Core/instanceConfiguration:InstanceConfiguration` | `id` |
| `oci:Core/instancePool:InstancePool` | `id` |
| `oci:Core/volume:Volume` | `id` |
| `oci:Core/volumeAttachment:VolumeAttachment` | `id` |
| `oci:AutoScaling/autoScalingConfiguration:AutoScalingConfiguration` | `id` |
| `oci:LoadBalancer/loadBalancer:LoadBalancer` | `ipAddressDetails` |
| `oci:LoadBalancer/backendSet:BackendSet` | `name` |
| `oci:LoadBalancer/ruleSet:RuleSet` | `name` |
| `oci:LoadBalancer/listener:Listener` | `name` |
| `oci:Bastion/bastion:Bastion` | `privateEndpointIpAddress` |
| `oci:Identity/dynamicGroup:DynamicGroup` | `id` |
| `oci:Identity/policy:Policy` | `id` |
| `oci:Identity/group:Group` | `id` |
| `oci:ObjectStorage/bucket:Bucket` | `name` |
| `oci:ObjectStorage/objectLifecyclePolicy:ObjectLifecyclePolicy` | `id` |
| `oci:Logging/logGroup:LogGroup` | `id` |
| `oci:Logging/log:Log` | `id` |
| `oci:ContainerEngine/cluster:Cluster` | `id`, `endpoints`, `lifecycle_state` |
| `oci:ContainerEngine/nodePool:NodePool` | `id`, `lifecycle_state` |
| `oci:GenerativeAi/agentKnowledgeBase:AgentKnowledgeBase` | `id`, `state` |
| `oci:GenerativeAi/agentDataSource:AgentDataSource` | `id`, `state` |
| `oci:GenerativeAi/agentAgent:AgentAgent` | `id`, `state` |
| `oci:GenerativeAi/agentTool:AgentTool` | `id`, `state` |
| `oci:GenerativeAi/agentAgentEndpoint:AgentAgentEndpoint` | `id`, `state` |

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
            outputs["ipv6cidr_blocks"] = ["2001:db8::/56"]
        elif typ in (
            "oci:Core/subnet:Subnet",
            "oci:Core/internetGateway:InternetGateway",
            "oci:Core/natGateway:NatGateway",
            "oci:Core/serviceGateway:ServiceGateway",
            "oci:Core/drg:Drg",
            "oci:Core/drgAttachment:DrgAttachment",
            "oci:Core/routeTable:RouteTable",
            "oci:Core/securityList:SecurityList",
            "oci:Core/defaultSecurityList:DefaultSecurityList",
            "oci:Core/networkSecurityGroup:NetworkSecurityGroup",
            "oci:Core/networkSecurityGroupSecurityRule:NetworkSecurityGroupSecurityRule",
            "oci:Core/instanceConfiguration:InstanceConfiguration",
            "oci:Core/instancePool:InstancePool",
            "oci:Core/volume:Volume",
            "oci:Core/volumeAttachment:VolumeAttachment",
        ):
            outputs["id"] = f"{args.name}-id"
        elif typ == "oci:Core/instance:Instance":
            outputs["privateIp"] = "10.0.128.10"
            outputs["publicIp"] = None
        elif typ == "pulumi-python:dynamic/cloudspells:SshKeyPair":
            outputs["publicKey"] = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCtest generated@cloudspells"
            outputs["public_key"] = outputs["publicKey"]
            outputs["privateKey"] = "-----BEGIN OPENSSH PRIVATE KEY-----\nmock\n-----END OPENSSH PRIVATE KEY-----\n"
            outputs["private_key"] = outputs["privateKey"]

        # ── AutoScaling ───────────────────────────────────────────────────────
        elif typ == "oci:AutoScaling/autoScalingConfiguration:AutoScalingConfiguration":
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

        # ── IAM ───────────────────────────────────────────────────────────────
        elif typ in (
            "oci:Identity/dynamicGroup:DynamicGroup",
            "oci:Identity/policy:Policy",
            "oci:Identity/group:Group",
        ):
            outputs["id"] = f"{args.name}-id"

        # ── Object Storage ────────────────────────────────────────────────────
        elif typ == "oci:ObjectStorage/bucket:Bucket":
            outputs["name"] = args.name
        elif typ in (
            "oci:ObjectStorage/objectLifecyclePolicy:ObjectLifecyclePolicy",
            "oci:Logging/logGroup:LogGroup",
            "oci:Logging/log:Log",
        ):
            outputs["id"] = f"{args.name}-id"

        # ── Container Engine ──────────────────────────────────────────────────
        elif typ == "oci:ContainerEngine/cluster:Cluster":
            outputs["id"] = f"{args.name}-id"
            outputs["endpoints"] = [{"kubernetes": f"https://{args.name}.k8s.example.com:6443"}]
            outputs["lifecycleState"] = "ACTIVE"
        elif typ == "oci:ContainerEngine/nodePool:NodePool":
            outputs["id"] = f"{args.name}-id"
            outputs["lifecycleState"] = "ACTIVE"

        # ── Generative AI ─────────────────────────────────────────────────────
        elif typ in (
            "oci:GenerativeAi/agentKnowledgeBase:AgentKnowledgeBase",
            "oci:GenerativeAi/agentDataSource:AgentDataSource",
            "oci:GenerativeAi/agentAgent:AgentAgent",
            "oci:GenerativeAi/agentTool:AgentTool",
            "oci:GenerativeAi/agentAgentEndpoint:AgentAgentEndpoint",
        ):
            outputs["id"] = f"{args.name}-id"
            outputs["state"] = "ACTIVE"

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

        # Mock get_availability_domains — Pulumi's SDK deserialises these dicts
        # into typed objects where `ad.name` is accessible.  Returning
        # `SimpleNamespace` here breaks the mock RPC serializer, so the mock
        # must stay as plain dicts; production code reads `ad.name` on the
        # deserialised typed object.
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


def set_mocks() -> None:
    """Activate the `OCIMocks` runtime for a Pulumi unit test.

    Must be called before importing any infrastructure module.  The Pulumi
    test runner intercepts all `new_resource` and `call` invocations from the
    moment mocks are installed, so any import that triggers resource
    registration must happen after this call.

    Example:
        ```python
        from tests.mocks import set_mocks
        set_mocks()  # must come before any infrastructure import

        from cloudspells.providers.oci.network import Vcn

        @pulumi.runtime.test
        async def test_vcn_creates_base_resources(self):
            vcn = Vcn("test", "ocid1.compartment.oc1...", "test-stack")
            ...
        ```
    """
    pulumi.runtime.set_mocks(OCIMocks(), project="unittest", stack="unittest", preview=False)
