import pulumi
from typing import Any, Optional
from .naming import ResourceNamer
from .tagging import ResourceTagger


class BaseResource(pulumi.ComponentResource):
    """Base class for all custom OCI resources providing common naming and tagging functionality."""

    compartment_id: pulumi.Input[str]
    stack_name: str
    name: str
    display_name: str
    namer: ResourceNamer
    tagger: ResourceTagger

    def __init__(
        self,
        resource_type: str,
        name: str,
        compartment_id: pulumi.Input[str],
        stack_name: str,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__(resource_type, f"{stack_name}-{name}", {}, opts)

        self.compartment_id = compartment_id
        self.stack_name = stack_name
        self.name = name
        self.display_name = f"{stack_name}-{name}"

        # Initialize helper classes
        self.namer = ResourceNamer(stack_name, name)
        self.tagger = ResourceTagger(stack_name, name)

    def create_resource_name(self, suffix: str) -> str:
        return self.namer.create_resource_name(suffix)

    def create_dns_label(self, prefix: str) -> str:
        return self.namer.create_dns_label(prefix)

    def create_freeform_tags(
        self,
        resource_name: str,
        resource_type: str,
        additional_tags: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        return self.tagger.create_freeform_tags(resource_name, resource_type, additional_tags)

    def create_network_resource_tags(
        self,
        resource_name: str,
        resource_type: str,
        network_type: str,
        subnet_group: str | None = None,
        additional_tags: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        return self.tagger.create_network_resource_tags(
            resource_name,
            resource_type,
            network_type,
            subnet_group,
            additional_tags,
        )

    def create_gateway_tags(
        self,
        resource_name: str,
        gateway_type: str,
        additional_tags: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        return self.tagger.create_gateway_tags(resource_name, gateway_type, additional_tags)

    def get_resource(self, resource_name: str) -> Any | None:
        """Get a child resource by name using generic attribute access.

        This is a generic approach to access any child resource of the component.
        Following Pulumi best practices for component resource introspection.

        Args:
            resource_name: The attribute name of the resource (e.g., 'public_subnet', 'nat_gateway').

        Returns:
            The requested resource object or None if not found.

        Example:
            vcn = Vcn(name="my-vcn", compartment_id="...", stack_name="my-stack")
            public_subnet = vcn.get_resource("public_subnet")
            nat_gateway = vcn.get_resource("nat_gateway")
        """
        return getattr(self, resource_name, None)
