from __future__ import annotations

from core.base import BaseResource
import pulumi
import pulumi_oci as oci
from typing import Any
from dataclasses import dataclass
from core.helper import Helper


@dataclass
class SubnetConfig:
    """Configuration for subnet creation."""

    cidr: str
    is_public: bool
    dns_label: str


class Vcn(BaseResource):
    """Virtual Cloud Network (VCN) resource with subnets, gateways, and routing.

    IMPORTANT: This class uses lazy initialization for security lists and subnets.
    They are created only when finalize_network() is called. This allows services
    like OKE to add their security rules before the security lists are created.

    Usage Patterns:

    1. With OKE or other services (automatic finalization):
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="banana")
        cluster = OkeCluster(vcn=vcn, ...)  # OKE calls vcn.finalize_network()
        # Subnets are now available: vcn.public_subnet, vcn.private_subnet
        ```

    2. Standalone VCN (manual finalization required):
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="banana")
        vcn.finalize_network()  # Must call this explicitly!
        # Now you can access: vcn.public_subnet, vcn.private_subnet
        ```
    """

    cidr_block: pulumi.Input[str]
    vcn: oci.core.Vcn
    internet_gateway: oci.core.InternetGateway
    nat_gateway: oci.core.NatGateway
    service_gateway: oci.core.ServiceGateway
    public_security_list: oci.core.SecurityList
    private_security_list: oci.core.SecurityList
    public_route_table: oci.core.RouteTable
    private_route_table: oci.core.RouteTable
    public_subnet: oci.core.Subnet | None
    private_subnet: oci.core.Subnet | None
    id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        stack_name: str,
        opts: pulumi.ResourceOptions | None = None,
        cidr_block: pulumi.Input[str] | None = None,
    ) -> None:
        super().__init__("custom:network:Vcn", name, compartment_id, stack_name, opts)
        self.cidr_block = cidr_block or "10.0.0.0/16"

        # Initialize the subnet properties
        self.public_subnet = None
        self.private_subnet = None

        # Storage for security list rules (builder pattern)
        # These will be populated by base rules + rules from services (OKE, databases, etc.)
        self._public_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = []
        self._public_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = []
        self._private_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = []
        self._private_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = []

        # Flag to track if security lists have been finalized
        self._security_lists_finalized: bool = False

        h: Helper = Helper()
        # Convert pulumi.Input[str] to str for subnet calculation
        cidr_str: str = str(self.cidr_block) if not isinstance(self.cidr_block, str) else self.cidr_block
        subnets: list[str] = h.calculate_subnets(cidr_str, 2)
        self._subnet_cidrs: list[str] = subnets  # Store for later use

        # Create base infrastructure (but NOT security lists or subnets yet)
        self._create_vcn()
        self._create_gateways()
        self._create_route_tables()

        # Note: Security lists and subnets will be created by finalize_network()
        # This allows services like OKE to add their rules before creation

    def _create_vcn(self) -> None:
        resource_name = self.create_resource_name("vcn")
        self.vcn = oci.core.Vcn(
            resource_name,
            compartment_id=self.compartment_id,
            cidr_blocks=[self.cidr_block],
            display_name=resource_name,
            dns_label=self.create_dns_label("vcn"),
            freeform_tags=self.create_freeform_tags(resource_name, "vcn", {"NetworkTier": "core"}),
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.id = self.vcn.id

    def _create_gateways(self) -> None:
        # Internet Gateway
        igw_name = self.create_resource_name("igw")
        self.internet_gateway = oci.core.InternetGateway(
            igw_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=igw_name,
            enabled=True,
            freeform_tags=self.create_gateway_tags(igw_name, "internet"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # NAT Gateway
        natgw_name = self.create_resource_name("natgw")
        self.nat_gateway = oci.core.NatGateway(
            natgw_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=natgw_name,
            freeform_tags=self.create_gateway_tags(natgw_name, "nat"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Service Gateway
        svcgw_name = self.create_resource_name("svcgw")
        self.service_gateway = oci.core.ServiceGateway(
            svcgw_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            services=[oci.core.ServiceGatewayServiceArgs(service_id=oci.core.get_services().services[0].id)],
            display_name=svcgw_name,
            freeform_tags=self.create_gateway_tags(svcgw_name, "service"),
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_security_lists(self) -> None:
        """Create security lists with all collected rules.

        This method is called by finalize_network() after all services have
        added their rules. It creates the security lists once with all the
        collected rules (base + OKE + databases + etc.).

        No versioning needed - security lists are created only once with
        all rules combined.
        """
        security_lists_config: dict[str, dict[str, Any]] = {
            "public": {
                "full_name": "public",
                "network_type": "public",
                "ingress_rules": self._public_ingress_rules,
                "egress_rules": self._public_egress_rules,
            },
            "private": {
                "full_name": "private",
                "network_type": "private",
                "ingress_rules": self._private_ingress_rules,
                "egress_rules": self._private_egress_rules,
            },
        }

        for short_name, config in security_lists_config.items():
            resource_name: str = self.create_resource_name(f"sl-{short_name}")
            full_name: str = str(config["full_name"])
            network_type: str = str(config["network_type"])
            ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = config["ingress_rules"]  # type: ignore[assignment]
            egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = config["egress_rules"]  # type: ignore[assignment]

            setattr(
                self,
                f"{full_name.replace('-', '_')}_security_list",
                oci.core.SecurityList(
                    resource_name,
                    compartment_id=self.compartment_id,
                    vcn_id=self.vcn.id,
                    display_name=resource_name,
                    ingress_security_rules=ingress_rules,
                    egress_security_rules=egress_rules,
                    freeform_tags=self.create_network_resource_tags(
                        resource_name, "security-list", network_type, full_name
                    ),
                    opts=pulumi.ResourceOptions(parent=self),
                ),
            )

    def _create_route_tables(self) -> None:
        private_route_rules = [
            oci.core.RouteTableRouteRuleArgs(
                destination="0.0.0.0/0",
                network_entity_id=self.nat_gateway.id,
            ),
            oci.core.RouteTableRouteRuleArgs(
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                network_entity_id=self.service_gateway.id,
            ),
        ]

        public_route_rules = [
            oci.core.RouteTableRouteRuleArgs(
                destination="0.0.0.0/0",
                network_entity_id=self.internet_gateway.id,
            ),
        ]

        route_tables = {
            ("public", "public"): (public_route_rules, "public"),
            ("private", "private"): (private_route_rules, "private"),
        }

        for (short_name, full_name), (rules, network_type) in route_tables.items():
            resource_name = self.create_resource_name(f"rt-{short_name}")
            setattr(
                self,
                f"{full_name.replace('-', '_')}_route_table",
                oci.core.RouteTable(
                    resource_name,
                    compartment_id=self.compartment_id,
                    vcn_id=self.vcn.id,
                    display_name=resource_name,
                    route_rules=rules,
                    freeform_tags=self.create_network_resource_tags(
                        resource_name, "route-table", network_type, full_name
                    ),
                    opts=pulumi.ResourceOptions(parent=self),
                ),
            )

    def _create_subnet(
        self,
        subnet_name: str,
        config: SubnetConfig,
        security_list: oci.core.SecurityList,
        route_table: oci.core.RouteTable,
    ) -> oci.core.Subnet:
        network_type: str = "public" if config.is_public else "private"
        subnet_group: str = f"{network_type}-{'a' if 'a' in config.dns_label else 'b'}"

        return oci.core.Subnet(
            subnet_name,
            compartment_id=self.compartment_id,
            security_list_ids=[security_list.id],
            vcn_id=self.vcn.id,
            cidr_block=config.cidr,
            display_name=subnet_name,
            dns_label=self.create_dns_label(config.dns_label),
            prohibit_public_ip_on_vnic=not config.is_public,
            route_table_id=route_table.id,
            freeform_tags=self.create_network_resource_tags(
                subnet_name, "subnet", network_type, subnet_group, {"CidrRange": config.cidr}
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_subnets(self, subnet_cidrs: list[str]) -> None:
        """Create public and private subnets from CIDR blocks.

        Args:
            subnet_cidrs: List of CIDR blocks for subnets.
        """
        public_subnet: str
        private_subnet: str
        public_subnet, private_subnet = subnet_cidrs[0], subnet_cidrs[1]

        subnet_configs: dict[tuple[str, str], SubnetConfig] = {
            ("public", "public"): SubnetConfig(public_subnet, True, "pub"),
            ("private", "private"): SubnetConfig(private_subnet, False, "priv"),
        }

        for (short_name, attr_name), config in subnet_configs.items():
            security_list: oci.core.SecurityList = getattr(self, f"{attr_name}_security_list")
            route_table: oci.core.RouteTable = getattr(self, f"{attr_name}_route_table")

            subnet_name: str = self.create_resource_name(f"sn-{short_name}")
            setattr(self, f"{attr_name}_subnet", self._create_subnet(subnet_name, config, security_list, route_table))

    def add_security_list_rules(
        self,
        public_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        public_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
        private_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        private_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
    ) -> None:
        """Add security list rules dynamically using the builder pattern.

        This method collects rules from different services (OKE, databases, etc.)
        before the security lists are created. This avoids the complexity of
        versioning and resource recreation.

        IMPORTANT: Must be called BEFORE finalize_network() is called.

        Args:
            public_ingress: Ingress rules to add to the public security list.
            public_egress: Egress rules to add to the public security list.
            private_ingress: Ingress rules to add to the private security list.
            private_egress: Egress rules to add to the private security list.

        Raises:
            RuntimeError: If called after security lists have been finalized.

        Example:
            ```python
            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="banana")

            # Services add their rules BEFORE finalization
            vcn.add_security_list_rules(
                public_ingress=[...oke_api_rules...],
                private_ingress=[...oke_worker_rules...],
            )

            # Then finalize to create security lists and subnets
            vcn.finalize_network()
            ```
        """
        if self._security_lists_finalized:
            raise RuntimeError(
                "Cannot add security list rules after network has been finalized. "
                "Call add_security_list_rules() before finalize_network()."
            )

        # Simply collect the rules - no resource creation yet
        if public_ingress:
            self._public_ingress_rules.extend(public_ingress)
        if public_egress:
            self._public_egress_rules.extend(public_egress)
        if private_ingress:
            self._private_ingress_rules.extend(private_ingress)
        if private_egress:
            self._private_egress_rules.extend(private_egress)

    def get_public_subnet_cidr(self) -> str:
        """Get the public subnet CIDR block.

        This method returns the calculated CIDR even before finalize_network()
        is called, allowing services to use it when building security rules.

        Returns:
            Public subnet CIDR block (e.g., "10.0.0.0/24")
        """
        return self._subnet_cidrs[0]

    def get_private_subnet_cidr(self) -> str:
        """Get the private subnet CIDR block.

        This method returns the calculated CIDR even before finalize_network()
        is called, allowing services to use it when building security rules.

        Returns:
            Private subnet CIDR block (e.g., "10.0.1.0/24")
        """
        return self._subnet_cidrs[1]

    def finalize_network(self) -> None:
        """Finalize the network by creating security lists and subnets.

        This method should be called after all services have added their
        security list rules via add_security_list_rules(). It creates the
        security lists with all collected rules and then creates the subnets.

        This method is automatically called at the end of __init__ if not
        called explicitly, but services like OKE should call it explicitly
        after adding their rules.

        Example:
            ```python
            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="banana")

            # OKE adds rules
            cluster = OkeCluster(vcn=vcn, ...)  # This calls vcn.add_security_list_rules()

            # Finalize network
            vcn.finalize_network()
            ```
        """
        if self._security_lists_finalized:
            return  # Already finalized, nothing to do

        # Create security lists with all collected rules
        self._create_security_lists()

        # Create subnets
        self._create_subnets(self._subnet_cidrs)

        # Mark as finalized
        self._security_lists_finalized = True

        # Register outputs
        self.register_outputs(
            {
                "public_subnet": self.public_subnet,
                "private_subnet": self.private_subnet,
                "cidr_block": self.cidr_block,
            }
        )


def get_resources_by_tag(vcn_instance: Vcn, tag_key: str, tag_value: str) -> list[Any]:
    """Get all resources from a VCN instance that match specific tag criteria.

    Args:
        vcn_instance: The VCN instance to search.
        tag_key: The tag key to match.
        tag_value: The tag value to match.

    Returns:
        List of resources that have matching tags.
    """
    resources: list[Any] = []
    for attr_name in dir(vcn_instance):
        if hasattr(getattr(vcn_instance, attr_name), "freeform_tags"):
            resource: Any = getattr(vcn_instance, attr_name)
            if resource.freeform_tags.get(tag_key) == tag_value:
                resources.append(resource)
    return resources
