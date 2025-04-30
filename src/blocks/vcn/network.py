from core.base import BaseResource
import pulumi
import pulumi_oci as oci
from typing import Optional
from dataclasses import dataclass
from core.helper import Helper


@dataclass
class SubnetConfig:
    cidr: str
    is_public: bool
    dns_label: str


class Vcn(BaseResource):
    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        stack_name: str,
        opts: Optional[pulumi.ResourceOptions] = None,
        cidr_block: Optional[pulumi.Input[str]] = None,
    ):
        super().__init__("custom:network:Vcn", name, compartment_id, stack_name, opts)
        self.cidr_block = cidr_block or "10.0.0.0/16"

        # Initialize the subnet properties
        self.public_subnet = None
        self.private_subnet = None

        h = Helper()
        subnets = h.calculate_subnets(self.cidr_block, 2)

        self._create_vcn()
        self._create_gateways()
        self._create_security_lists()
        self._create_route_tables()
        self._create_subnets(subnets)

        # Register the subnet properties in the outputs
        self.register_outputs(
            {
                "public_subnet": self.public_subnet,
                "private_subnet": self.private_subnet,
                "cidr_block": self.cidr_block,
            }
        )

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
        security_lists = {
            "public": ("public", "public"),
            "private": ("private", "private"),
        }

        for short_name, (full_name, network_type) in security_lists.items():
            resource_name = self.create_resource_name(f"sl-{short_name}")
            setattr(
                self,
                f"{full_name.replace('-', '_')}_security_list",
                oci.core.SecurityList(
                    resource_name,
                    compartment_id=self.compartment_id,
                    vcn_id=self.vcn.id,
                    display_name=resource_name,
                    ingress_security_rules=[],
                    egress_security_rules=[],
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
        network_type = "public" if config.is_public else "private"
        subnet_group = f"{network_type}-{'a' if 'a' in config.dns_label else 'b'}"

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

    def _create_subnets(self, subnet_cidrs: tuple) -> None:
        public_subnet, private_subnet = subnet_cidrs

        subnet_configs = {
            ("public", "public"): SubnetConfig(public_subnet, True, "pub"),
            ("private", "private"): SubnetConfig(private_subnet, False, "priv"),
        }

        for (short_name, attr_name), config in subnet_configs.items():
            security_list = getattr(self, f"{attr_name}_security_list")
            route_table = getattr(self, f"{attr_name}_route_table")

            subnet_name = self.create_resource_name(f"sn-{short_name}")
            setattr(self, f"{attr_name}_subnet", self._create_subnet(subnet_name, config, security_list, route_table))

    def banana(self):
        self.public_subnet


def get_resources_by_tag(vcn_instance, tag_key: str, tag_value: str):
    resources = []
    for attr_name in dir(vcn_instance):
        if hasattr(getattr(vcn_instance, attr_name), "freeform_tags"):
            resource = getattr(vcn_instance, attr_name)
            if resource.freeform_tags.get(tag_key) == tag_value:
                resources.append(resource)
    return resources
