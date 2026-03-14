"""Resource tagging utilities for CloudBlocks.

Provides `ResourceTagger`, which generates consistent OCI freeform tag
dictionaries.  Every resource created by an CloudBlocks component receives at
minimum these baseline tags, enabling cost reporting, governance queries, and
resource discovery:

- `Name`        — human-readable resource identifier.
- `ResourceType` — category of the resource (e.g. `"vcn"`, `"subnet"`).
- `Environment` — the Pulumi stack name.
- `CreatedBy`   — `"{stack_name}-{resource_name}"` identifying the block.

Specialised helpers add extra keys for network and gateway resources.
"""

from typing import Any, Dict, Optional


class ResourceTagger:
    """Generate standardised OCI freeform tag dictionaries.

    Every `BaseResource` owns a `ResourceTagger` instance
    and delegates tag creation to it via the `create_*_tags` methods.

    Attributes:
        stack_name: Pulumi stack name (e.g. `"prod"`).
        resource_name: Logical name of the building block (e.g. `"lab"`).
    """

    stack_name: str
    resource_name: str

    def __init__(self, stack_name: str, resource_name: str) -> None:
        """Initialise a tagger for a specific resource.

        Args:
            stack_name: Pulumi stack name used as the `Environment` tag value.
            resource_name: Logical name of the resource block, used in the
                `CreatedBy` tag.
        """
        self.stack_name = stack_name
        self.resource_name = resource_name

    def create_freeform_tags(
        self,
        resource_name: str,
        resource_type: str,
        additional_tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Create the standard freeform tag dictionary for an OCI resource.

        Every resource receives these baseline tags:

        - `Name`        — resource_name (the display name of the resource).
        - `ResourceType` — resource_type (e.g. `"vcn"`, `"subnet"`).
        - `Environment` — the Pulumi stack name.
        - `CreatedBy`   — `"{stack_name}-{resource_name}"` string
          identifying the CloudBlocks component that created the resource.

        Args:
            resource_name: Display name for the `Name` tag (usually the
                fully-qualified OCI resource name, e.g. `"prod-lab-vcn"`).
            resource_type: Resource category for the `ResourceType` tag.
            additional_tags: Optional extra key/value pairs merged into the
                returned dict.  Values are cast to `str`; conflicting keys
                override the baseline defaults.

        Returns:
            Flat `dict[str, str]` suitable for the `freeform_tags=`
            argument on any OCI resource.

        Example:
            >>> tagger = ResourceTagger("prod", "lab")
            >>> tagger.create_freeform_tags("prod-lab-vcn", "vcn")
            {'Name': 'prod-lab-vcn', 'ResourceType': 'vcn', 'Environment': 'prod', 'CreatedBy': 'prod-lab'}
        """
        tags: Dict[str, str] = {
            "Name": resource_name,
            "ResourceType": resource_type,
            "Environment": self.stack_name,
            "CreatedBy": f"{self.stack_name}-{self.resource_name}",
        }

        if additional_tags:
            tags.update({k: str(v) for k, v in additional_tags.items()})

        return tags

    def create_network_resource_tags(
        self,
        resource_name: str,
        resource_type: str,
        network_type: str,
        subnet_group: Optional[str] = None,
        additional_tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Create freeform tags enriched with networking metadata.

        Extends the baseline tags from `create_freeform_tags` with:

        - `NetworkType`  — `"public"` or `"private"`.
        - `SubnetGroup`  — optional logical sub-group (e.g. `"public-a"`).

        Args:
            resource_name: Display name for the `Name` tag.
            resource_type: Resource category (e.g. `"subnet"`,
                `"security-list"`, `"route-table"`).
            network_type: Network tier — typically `"public"` or
                `"private"`.
            subnet_group: Optional sub-grouping label within the network tier.
            additional_tags: Optional extra key/value pairs to merge.

        Returns:
            Flat `dict[str, str]` with all baseline and networking tags.
        """
        extra: Dict[str, Any] = {"NetworkType": network_type}

        if subnet_group:
            extra["SubnetGroup"] = subnet_group

        if additional_tags:
            extra.update(additional_tags)

        return self.create_freeform_tags(resource_name, resource_type, extra)

    def create_gateway_tags(
        self,
        resource_name: str,
        gateway_type: str,
        additional_tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Create freeform tags for an OCI gateway resource.

        Extends the baseline tags from `create_freeform_tags` with:

        - `GatewayType` — e.g. `"internet"`, `"nat"`, `"service"`.

        Args:
            resource_name: Display name for the `Name` tag.
            gateway_type: Gateway category string (e.g. `"internet"`).
            additional_tags: Optional extra key/value pairs to merge.

        Returns:
            Flat `dict[str, str]` with all baseline tags and
            `GatewayType` included.
        """
        extra: Dict[str, Any] = {"GatewayType": gateway_type}

        if additional_tags:
            extra.update(additional_tags)

        return self.create_freeform_tags(resource_name, "gateway", extra)
