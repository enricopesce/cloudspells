"""Resource tagging utilities for CloudSpells.

Provides `ResourceTagger`, which generates consistent tag dictionaries for
any cloud provider.  Every resource created by a CloudSpells spell receives
these baseline tags automatically, enabling tenant-wide discovery, cost
reporting, and governance queries across OCI, AWS, GCP, and Azure:

- `managed-by`    — always `"cloudspells"`.  Filter any provider's resource
  inventory to show only CloudSpells-managed resources.
- `spell-type`    — the spell that created this resource
  (e.g. `"vcn"`, `"oke-cluster"`, `"compute-instance"`).
- `spell-name`    — the logical name passed by the caller (e.g. `"lab"`).
- `environment`   — the Pulumi stack name (e.g. `"prod"`, `"staging"`).
- `name`          — fully-qualified resource identifier
  (e.g. `"prod-lab-vcn"`).
- `resource-type` — cloud resource category
  (e.g. `"vcn"`, `"subnet"`, `"instance"`).

Keys use lowercase-hyphen format, which is valid on all four major cloud
providers including GCP (which requires lowercase label keys).

Specialised helpers add extra keys for network and gateway resources.
"""

from typing import Any, Dict, Optional


class ResourceTagger:
    """Generate standardised tag dictionaries for cloud resources.

    Every `BaseResource` owns a `ResourceTagger` instance and delegates
    tag creation to it via the `create_*_tags` methods.

    Attributes:
        stack_name: Pulumi stack name (e.g. `"prod"`).
        resource_name: Logical name of the spell (e.g. `"lab"`).
        spell_type: Kebab-case spell identifier derived from the Pulumi
            resource type URN (e.g. `"vcn"`, `"oke-cluster"`).
    """

    stack_name: str
    resource_name: str
    spell_type: str

    def __init__(self, stack_name: str, resource_name: str, spell_type: str) -> None:
        """Initialise a tagger for a specific resource.

        Args:
            stack_name: Pulumi stack name used as the `environment` tag value.
            resource_name: Logical name of the spell, used in the
                `spell-name` tag.
            spell_type: Kebab-case spell identifier used in the `spell-type`
                tag (e.g. `"vcn"`, `"oke-cluster"`, `"vcn-flow-logs"`).
        """
        self.stack_name = stack_name
        self.resource_name = resource_name
        self.spell_type = spell_type

    def create_freeform_tags(
        self,
        resource_name: str,
        resource_type: str,
        additional_tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Create the standard tag dictionary for a cloud resource.

        Every resource receives these baseline tags:

        - `managed-by`    — `"cloudspells"` (tenant-wide discovery sentinel).
        - `spell-type`    — kebab-case spell identifier.
        - `spell-name`    — logical name passed by the caller.
        - `environment`   — Pulumi stack name.
        - `name`          — fully-qualified resource display name.
        - `resource-type` — cloud resource category.

        Keys use lowercase-hyphen format, valid on OCI, AWS, Azure, and GCP.

        Args:
            resource_name: Display name for the `name` tag (usually the
                fully-qualified resource name, e.g. `"prod-lab-vcn"`).
            resource_type: Resource category for the `resource-type` tag
                (e.g. `"vcn"`, `"subnet"`, `"instance"`).
            additional_tags: Optional extra key/value pairs merged into the
                returned dict.  Values are cast to `str`; conflicting keys
                override the baseline.

        Returns:
            Flat `dict[str, str]` suitable for the `freeform_tags=` (OCI),
            `tags=` (AWS/Azure), or `labels=` (GCP) argument on any resource.

        Example:
            >>> tagger = ResourceTagger("prod", "lab", "vcn")
            >>> tagger.create_freeform_tags("prod-lab-vcn", "vcn")
            {'managed-by': 'cloudspells', 'spell-type': 'vcn', 'spell-name': 'lab',
             'environment': 'prod', 'name': 'prod-lab-vcn', 'resource-type': 'vcn'}
        """
        tags: Dict[str, str] = {
            "managed-by": "cloudspells",
            "spell-type": self.spell_type,
            "spell-name": self.resource_name,
            "environment": self.stack_name,
            "name": resource_name,
            "resource-type": resource_type,
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
        """Create tags enriched with networking metadata.

        Extends the baseline tags from `create_freeform_tags` with:

        - `network-type` — `"public"` or `"private"`.
        - `subnet-group` — optional logical sub-group (e.g. `"public-a"`).

        Args:
            resource_name: Display name for the `name` tag.
            resource_type: Resource category (e.g. `"subnet"`,
                `"security-list"`, `"route-table"`).
            network_type: Network tier — typically `"public"` or `"private"`.
            subnet_group: Optional sub-grouping label within the tier.
            additional_tags: Optional extra key/value pairs to merge.

        Returns:
            Flat `dict[str, str]` with all baseline and networking tags.
        """
        extra: Dict[str, Any] = {"network-type": network_type}

        if subnet_group:
            extra["subnet-group"] = subnet_group

        if additional_tags:
            extra.update(additional_tags)

        return self.create_freeform_tags(resource_name, resource_type, extra)

    def create_gateway_tags(
        self,
        resource_name: str,
        gateway_type: str,
        additional_tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Create tags for a network gateway resource.

        Extends the baseline tags from `create_freeform_tags` with:

        - `gateway-type` — e.g. `"internet"`, `"nat"`, `"service"`.

        Args:
            resource_name: Display name for the `name` tag.
            gateway_type: Gateway category string (e.g. `"internet"`).
            additional_tags: Optional extra key/value pairs to merge.

        Returns:
            Flat `dict[str, str]` with all baseline tags and
            `gateway-type` included.
        """
        extra: Dict[str, Any] = {"gateway-type": gateway_type}

        if additional_tags:
            extra.update(additional_tags)

        return self.create_freeform_tags(resource_name, "gateway", extra)
