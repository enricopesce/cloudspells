"""VCN (Virtual Cloud Network) building block implementation.

This module provides :class:`Vcn`, which creates a complete OCI network
topology using a *lazy initialisation* (builder) pattern:

1. Construct the ``Vcn`` object – the VCN, gateways, and route tables are
   created immediately.
2. Other blocks (OKE, Compute, ScalableWorkload) call
   :meth:`Vcn.add_security_list_rules` to accumulate their required rules.
3. The *first* block to finish calls :meth:`Vcn.finalize_network`, which
   creates the security lists with *all* accumulated rules and then creates
   the subnets.  Subsequent calls to ``finalize_network`` are no-ops.

This approach keeps the OCI security-list-per-subnet count at 1, leaving
the remaining 4 slots free for future services.

**Subnet layout**

The VCN CIDR is split into four contiguous, CIDR-aligned tiers using binary
subdivision.  The same formula applies regardless of the prefix length you
choose (``/16``, ``/20``, ``/24``, …):

.. code-block:: text

    VCN  (prefix/N)
    ├── Private     prefix/(N+1)  — 50 %  of VCN  — NAT + Service GW
    ├── Secure      prefix/(N+2)  — 25 %  of VCN  — Service GW only
    ├── Public      prefix/(N+3)  — 12.5% of VCN  — Internet GW
    └── Management  prefix/(N+3)  — 12.5% of VCN  — Service GW only

Examples for common prefix lengths:

+--------+------------------+------------------+------------------+------------------+
| VCN    | Private (/N+1)   | Secure (/N+2)    | Public (/N+3)    | Management (/N+3)|
+========+==================+==================+==================+==================+
| /16    | /17  (32 766 h)  | /18  (16 382 h)  | /19   (8 190 h)  | /19   (8 190 h)  |
+--------+------------------+------------------+------------------+------------------+
| /20    | /21   (2 046 h)  | /22   (1 022 h)  | /23     (510 h)  | /23     (510 h)  |
+--------+------------------+------------------+------------------+------------------+
| /24    | /25     (126 h)  | /26      (62 h)  | /27      (30 h)  | /27      (30 h)  |
+--------+------------------+------------------+------------------+------------------+

*(h = usable host IPs after subtracting the OCI-reserved 5 addresses per subnet)*

All four blocks together exactly cover the VCN CIDR — no gaps, no overlaps.
CIDR validation (canonical form, prefix length sanity) is delegated to OCI;
the Pulumi provider will reject malformed values at plan time.
"""

from __future__ import annotations

import ipaddress

from core.base import BaseResource
import pulumi
import pulumi_oci as oci
from typing import Any, Literal
from dataclasses import dataclass

# Subnet tier identifiers — use these constants instead of bare strings.
SubnetTier = Literal["public", "private", "secure", "management"]

SUBNET_PUBLIC: Literal["public"] = "public"
SUBNET_PRIVATE: Literal["private"] = "private"
SUBNET_SECURE: Literal["secure"] = "secure"
SUBNET_MANAGEMENT: Literal["management"] = "management"



class _SubnetRef:
    """Thin wrapper exposing only the ``id`` of an externally-managed subnet."""

    def __init__(self, subnet_id: pulumi.Input[str]) -> None:
        self.id: pulumi.Output[str] = pulumi.Output.from_input(subnet_id)


class _SecurityListRef:
    """Thin wrapper exposing only the ``id`` of an externally-managed security list."""

    def __init__(self, security_list_id: pulumi.Input[str]) -> None:
        self.id: pulumi.Output[str] = pulumi.Output.from_input(security_list_id)


@dataclass
class SubnetConfig:
    """Internal configuration record for a single subnet.

    Used by :meth:`Vcn._create_subnets` to hold the per-subnet parameters
    resolved during :meth:`Vcn.finalize_network`.

    Attributes:
        cidr: IPv4 CIDR block assigned to the subnet (e.g. ``"10.0.0.0/17"``).
        is_public: ``True`` for a public subnet (instances may receive public
            IPs); ``False`` for a private subnet.
        dns_label: Short DNS label prefix passed to
            :meth:`~core.base.BaseResource.create_dns_label`.
    """

    cidr: str
    is_public: bool
    dns_label: str


class Vcn(BaseResource):
    """OCI Virtual Cloud Network with subnets, gateways, and security lists.

    Creates the complete OCI network foundation required by all other
    OCIBlocks components:

    * One VCN with a configurable CIDR block (default ``"10.0.0.0/18"``).
    * Internet Gateway, NAT Gateway, and Service Gateway.
    * Four route tables — one per subnet tier — wired to the appropriate
      gateways (see module docstring for routing policy per tier).
    * Four security lists populated via the builder pattern.
    * Four contiguous, CIDR-aligned subnets auto-calculated by binary
      subdivision of the VCN CIDR (private 50 %, secure 25 %, public 12.5 %,
      management 12.5 %).  Any valid prefix length works — ``/16``, ``/20``,
      ``/24``, etc.  See the module docstring for a worked example table.

    .. important::

        Security lists and subnets are **not** created in ``__init__``.  They
        are created only when :meth:`finalize_network` is called.  Other
        blocks add their rules via :meth:`add_security_list_rules` **before**
        that call.

    Attributes:
        cidr_block: IPv4 CIDR block for the VCN.
        vcn: The underlying ``oci.core.Vcn`` resource.
        internet_gateway: Internet Gateway resource.
        nat_gateway: NAT Gateway resource.
        service_gateway: Service Gateway resource.
        public_security_list: Public-subnet security list (available after
            :meth:`finalize_network`).
        private_security_list: Private-subnet security list (available after
            :meth:`finalize_network`).
        public_route_table: Route table for the public subnet.
        private_route_table: Route table for the private subnet.
        public_subnet: Public subnet resource, or ``None`` before
            :meth:`finalize_network`.
        private_subnet: Private subnet resource, or ``None`` before
            :meth:`finalize_network`.
        secure_subnet: Secure (data) subnet resource, or ``None`` before
            :meth:`finalize_network`.  No internet path — Service Gateway only.
        secure_security_list: Secure-subnet security list (available after
            :meth:`finalize_network`).
        secure_route_table: Route table for the secure subnet (Service Gateway
            only — no default route, no NAT).
        management_subnet: Management subnet resource, or ``None`` before
            :meth:`finalize_network`.  No internet path — Service Gateway
            only.  For monitoring agents, bastion service, VPN endpoints,
            and internal tooling.
        management_security_list: Management-subnet security list (available
            after :meth:`finalize_network`).
        management_route_table: Route table for the management subnet
            (Service Gateway only — same isolation policy as secure).
        id: ``pulumi.Output[str]`` of the VCN OCID.

    Usage patterns:

    1. **Standalone VCN** (manual finalisation required)::

            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
            vcn.finalize_network()
            # vcn.public_subnet and vcn.private_subnet are now available

    2. **With other OCIBlocks components** (automatic finalisation)::

            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
            cluster = OkeCluster(vcn=vcn, ...)   # calls finalize_network internally
            # vcn.public_subnet and vcn.private_subnet are now available
    """

    SUBNET_PUBLIC: Literal["public"] = "public"
    SUBNET_PRIVATE: Literal["private"] = "private"
    SUBNET_SECURE: Literal["secure"] = "secure"
    SUBNET_MANAGEMENT: Literal["management"] = "management"

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
    secure_subnet: oci.core.Subnet | None
    secure_security_list: oci.core.SecurityList
    secure_route_table: oci.core.RouteTable
    management_subnet: oci.core.Subnet | None
    management_security_list: oci.core.SecurityList
    management_route_table: oci.core.RouteTable
    id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
        cidr_block: pulumi.Input[str] | None = None,
    ) -> None:
        """Create a VCN with gateways and route tables.

        Security lists and subnets are *not* created here; call
        :meth:`finalize_network` (directly or indirectly via another block)
        once all security rules have been accumulated.

        Args:
            name: Logical name for this VCN (e.g. ``"lab"``).
            compartment_id: OCID of the OCI compartment to deploy into.
            stack_name: Pulumi stack name.  Defaults to
                ``pulumi.get_stack()`` when ``None``.
            opts: Pulumi resource options forwarded to the component.
            cidr_block: IPv4 CIDR for the VCN in canonical form
                (no host bits set, e.g. ``"10.0.0.0/16"`` not
                ``"10.0.1.0/16"``).  Defaults to ``"10.0.0.0/18"``.
                Any prefix length is accepted; the four tier subnets are
                derived automatically by binary subdivision — private gets
                50 % (prefix+1), secure 25 % (prefix+2), public and
                management 12.5 % each (prefix+3).  See the module
                docstring for a full example table across common prefix
                lengths.
        """
        super().__init__("custom:network:Vcn", name, compartment_id, stack_name, opts)
        self.cidr_block = cidr_block or "10.0.0.0/18"

        # Initialize the subnet properties
        self.public_subnet = None
        self.private_subnet = None
        self.secure_subnet = None
        self.management_subnet = None

        # Storage for security list rules (builder pattern).
        # Populated by add_security_list_rules() calls from other blocks.
        self._public_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = []
        self._public_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = []
        self._private_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = []
        self._private_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = []
        self._secure_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = []
        self._secure_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = []
        self._management_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = []
        self._management_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = []

        # Flag to track whether finalize_network() has been called.
        self._security_lists_finalized: bool = False

        cidr_str: str = str(self.cidr_block) if not isinstance(self.cidr_block, str) else self.cidr_block
        self._subnet_cidrs: list[str] = self._split_tiers(cidr_str)

        # Create base infrastructure (NOT security lists or subnets yet).
        self._create_vcn()
        self._create_gateways()
        self._create_route_tables()

    @staticmethod
    def _split_tiers(cidr: str) -> list[str]:
        """Split a VCN CIDR into four contiguous, CIDR-aligned tier blocks.

        Uses binary subdivision — each tier takes exactly half of the
        remaining address space:

        .. code-block:: text

            VCN (prefix/N)  ──────────────────────────────────────── 100 %
            ├── Private  (prefix/N+1) ─────────────────────────────   50 %
            └── remainder (prefix/N+1)
                ├── Secure  (prefix/N+2) ──────────────────────────   25 %
                └── remainder (prefix/N+2)
                    ├── Public      (prefix/N+3) ───────────────────  12.5 %
                    └── Management  (prefix/N+3) ───────────────────  12.5 %

        The four blocks are placed in ascending address order so private
        occupies the naturally aligned lower half (guaranteed CIDR alignment).
        All four blocks together exactly reconstruct the original VCN CIDR —
        no gaps, no overlaps.

        The same formula applies for any prefix length:

        * ``/16`` → private ``/17``, secure ``/18``, public ``/19``, mgmt ``/19``
        * ``/20`` → private ``/21``, secure ``/22``, public ``/23``, mgmt ``/23``
        * ``/24`` → private ``/25``, secure ``/26``, public ``/27``, mgmt ``/27``

        Args:
            cidr: Canonical VCN CIDR string with no host bits set
                (e.g. ``"10.0.0.0/16"``).

        Returns:
            ``[public_cidr, private_cidr, secure_cidr, management_cidr]``
            matching the index convention used elsewhere in this class.

        Example::

            Vcn._split_tiers("10.0.0.0/16")
            # → ["10.0.192.0/19", "10.0.0.0/17", "10.0.128.0/18", "10.0.224.0/19"]
            #     public           private          secure           management

            Vcn._split_tiers("172.16.0.0/20")
            # → ["172.16.12.0/23", "172.16.0.0/21", "172.16.8.0/22", "172.16.14.0/23"]
            #     public            private           secure           management
        """
        net = ipaddress.ip_network(cidr, strict=True)
        halves = list(net.subnets(prefixlen_diff=1))
        private = halves[0]                                        # 50 %

        quarters = list(halves[1].subnets(prefixlen_diff=1))
        secure = quarters[0]                                       # 25 %

        eighths = list(quarters[1].subnets(prefixlen_diff=1))
        public = eighths[0]                                        # 12.5 %
        management = eighths[1]                                    # 12.5 %

        return [str(public), str(private), str(secure), str(management)]

    # ------------------------------------------------------------------
    # Private infrastructure creation helpers
    # ------------------------------------------------------------------

    def _create_vcn(self) -> None:
        """Create the ``oci.core.Vcn`` resource and store its OCID as ``self.id``."""
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
        """Create the Internet, NAT, and Service gateways for the VCN."""
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
        """Create public and private security lists with all accumulated rules.

        Called exactly once by :meth:`finalize_network`.  The security lists
        are built from the rules stored in the four ``_*_rules`` lists, which
        were populated by :meth:`add_security_list_rules` calls from other
        blocks.

        After this method returns, ``self.public_security_list`` and
        ``self.private_security_list`` are set.
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
            "secure": {
                "full_name": "secure",
                "network_type": "secure",
                "ingress_rules": self._secure_ingress_rules,
                "egress_rules": self._secure_egress_rules,
            },
            "management": {
                "full_name": "management",
                "network_type": "management",
                "ingress_rules": self._management_ingress_rules,
                "egress_rules": self._management_egress_rules,
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
        """Create public and private route tables wired to the correct gateways.

        * Public route table: default route (``0.0.0.0/0``) via the Internet
          Gateway.
        * Private route table: default route via the NAT Gateway; OCI service
          CIDR via the Service Gateway.
        * Secure route table: OCI service CIDR via the Service Gateway **only**.
          No default route — instances in the secure tier have no internet path.
        * Management route table: OCI service CIDR via the Service Gateway
          **only**.  Same isolation policy as the secure route table.
        """
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

        secure_route_rules = [
            oci.core.RouteTableRouteRuleArgs(
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                network_entity_id=self.service_gateway.id,
            ),
        ]

        management_route_rules = [
            oci.core.RouteTableRouteRuleArgs(
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                network_entity_id=self.service_gateway.id,
            ),
        ]

        route_tables = {
            ("public", "public"): (public_route_rules, "public"),
            ("private", "private"): (private_route_rules, "private"),
            ("secure", "secure"): (secure_route_rules, "secure"),
            ("management", "management"): (management_route_rules, "management"),
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
        """Create a single OCI subnet resource.

        Args:
            subnet_name: Fully-qualified OCI resource name for the subnet.
            config: :class:`SubnetConfig` carrying CIDR, visibility, and DNS
                label for this subnet.
            security_list: Security list to attach to the subnet.
            route_table: Route table to attach to the subnet.

        Returns:
            The newly created ``oci.core.Subnet`` resource.
        """
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
        """Create public, private, secure, and management subnets.

        Args:
            subnet_cidrs: Four CIDR strings from :meth:`_split_tiers`;
                indices 0/1/2/3 map to public/private/secure/management.
        """
        public_cidr, private_cidr, secure_cidr, management_cidr = (
            subnet_cidrs[0], subnet_cidrs[1], subnet_cidrs[2], subnet_cidrs[3]
        )

        subnet_configs: dict[tuple[str, str], SubnetConfig] = {
            ("public", "public"): SubnetConfig(public_cidr, True, "pub"),
            ("private", "private"): SubnetConfig(private_cidr, False, "priv"),
            ("secure", "secure"): SubnetConfig(secure_cidr, False, "sec"),
            ("management", "management"): SubnetConfig(management_cidr, False, "mgmt"),
        }

        for (short_name, attr_name), config in subnet_configs.items():
            security_list: oci.core.SecurityList = getattr(self, f"{attr_name}_security_list")
            route_table: oci.core.RouteTable = getattr(self, f"{attr_name}_route_table")

            subnet_name: str = self.create_resource_name(f"sn-{short_name}")
            setattr(self, f"{attr_name}_subnet", self._create_subnet(subnet_name, config, security_list, route_table))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export the canonical VCN stack outputs for cross-stack consumption.

        Publishes the fourteen keys that :meth:`VcnRef.from_stack_reference`
        expects, so any stack using a standalone ``Vcn`` can be referenced by
        another stack without additional configuration.

        Must be called **after** :meth:`finalize_network`.

        Raises:
            RuntimeError: If called before :meth:`finalize_network`.

        Example::

            vcn = Vcn(name="lab", compartment_id=comp_id)
            vcn.finalize_network()
            vcn.export()
        """
        if not self._security_lists_finalized:
            raise RuntimeError("Call finalize_network() before export().")
        assert self.public_subnet is not None
        assert self.private_subnet is not None
        assert self.secure_subnet is not None
        assert self.management_subnet is not None
        pulumi.export("vcn_id", self.id)
        pulumi.export("cidr_block", self.cidr_block)
        pulumi.export("public_subnet_id", self.public_subnet.id)
        pulumi.export("private_subnet_id", self.private_subnet.id)
        pulumi.export("secure_subnet_id", self.secure_subnet.id)
        pulumi.export("public_subnet_cidr", self.get_public_subnet_cidr())
        pulumi.export("private_subnet_cidr", self.get_private_subnet_cidr())
        pulumi.export("secure_subnet_cidr", self.get_secure_subnet_cidr())
        pulumi.export("public_security_list_id", self.public_security_list.id)
        pulumi.export("private_security_list_id", self.private_security_list.id)
        pulumi.export("secure_security_list_id", self.secure_security_list.id)
        pulumi.export("management_subnet_id", self.management_subnet.id)
        pulumi.export("management_subnet_cidr", self.get_management_subnet_cidr())
        pulumi.export("management_security_list_id", self.management_security_list.id)

    def add_security_list_rules(
        self,
        public_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        public_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
        private_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        private_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
        secure_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        secure_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
        management_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        management_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
    ) -> None:
        """Accumulate security list rules before the network is finalised.

        Uses the *builder* pattern: rules contributed by different blocks are
        collected here and applied together when :meth:`finalize_network` is
        called.  This ensures only a single security list per subnet is
        created, leaving the remaining OCI slots free for future services.

        .. important::

            This method **must** be called *before* :meth:`finalize_network`.

        Args:
            public_ingress: Ingress rules to add to the public security list.
            public_egress: Egress rules to add to the public security list.
            private_ingress: Ingress rules to add to the private security list.
            private_egress: Egress rules to add to the private security list.
            secure_ingress: Ingress rules to add to the secure security list.
            secure_egress: Egress rules to add to the secure security list.
            management_ingress: Ingress rules to add to the management security list.
            management_egress: Egress rules to add to the management security list.

        Raises:
            RuntimeError: If called after :meth:`finalize_network` has already
                been called.

        Example::

            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")

            vcn.add_security_list_rules(
                public_ingress=[...api_rules...],
                private_ingress=[...worker_rules...],
            )

            vcn.finalize_network()
        """
        if self._security_lists_finalized:
            raise RuntimeError(
                "Cannot add security list rules after network has been finalized. "
                "Call add_security_list_rules() before finalize_network()."
            )

        if public_ingress:
            self._public_ingress_rules.extend(public_ingress)
        if public_egress:
            self._public_egress_rules.extend(public_egress)
        if private_ingress:
            self._private_ingress_rules.extend(private_ingress)
        if private_egress:
            self._private_egress_rules.extend(private_egress)
        if secure_ingress:
            self._secure_ingress_rules.extend(secure_ingress)
        if secure_egress:
            self._secure_egress_rules.extend(secure_egress)
        if management_ingress:
            self._management_ingress_rules.extend(management_ingress)
        if management_egress:
            self._management_egress_rules.extend(management_egress)

    def get_public_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the public subnet CIDR block.

        Available immediately after construction (before
        :meth:`finalize_network`), so other blocks can use it when building
        their security rules.

        Returns:
            Public subnet CIDR (e.g. ``"10.0.0.0/17"``).
        """
        return self._subnet_cidrs[0]

    def get_private_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the private subnet CIDR block.

        Available immediately after construction (before
        :meth:`finalize_network`), so other blocks can use it when building
        their security rules.

        Returns:
            Private subnet CIDR (e.g. ``"10.0.128.0/17"``).
        """
        return self._subnet_cidrs[1]

    def get_secure_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the secure subnet CIDR block.

        Available immediately after construction (before
        :meth:`finalize_network`), so other blocks can use it when building
        their security rules.

        Returns:
            Secure subnet CIDR (e.g. ``"10.0.128.0/18"``).
        """
        return self._subnet_cidrs[2]

    def get_management_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the management subnet CIDR block.

        Returns:
            Management subnet CIDR (e.g. ``"10.0.56.0/21"``).
        """
        return self._subnet_cidrs[3]

    def finalize_network(self) -> None:
        """Create security lists and subnets with all accumulated rules.

        This method is **idempotent** – only the first call has any effect;
        subsequent calls return immediately.  It is invoked automatically by
        other OCIBlocks components (OKE, Compute, ScalableWorkload) at the
        end of their ``__init__`` methods.  Call it explicitly only when
        using ``Vcn`` in standalone mode (without other blocks).

        After this method returns:

        * ``self.public_security_list`` is set.
        * ``self.private_security_list`` is set.
        * ``self.secure_security_list`` is set.
        * ``self.management_security_list`` is set.
        * ``self.public_subnet`` is set.
        * ``self.private_subnet`` is set.
        * ``self.secure_subnet`` is set.
        * ``self.management_subnet`` is set.

        Example::

            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
            vcn.finalize_network()
            # vcn.public_subnet is now available
        """
        if self._security_lists_finalized:
            return

        self._create_security_lists()
        self._create_subnets(self._subnet_cidrs)

        self._security_lists_finalized = True

        self.register_outputs(
            {
                "public_subnet": self.public_subnet,
                "private_subnet": self.private_subnet,
                "secure_subnet": self.secure_subnet,
                "management_subnet": self.management_subnet,
                "cidr_block": self.cidr_block,
            }
        )


class VcnRef:
    """Read-only reference to a VCN managed by another Pulumi stack.

    Lets you deploy OCIBlocks services (OKE, Compute, ScalableWorkload) into a
    VCN that was created by a *separate* Pulumi stack, without recreating or
    modifying any network resources.

    .. warning::

        :meth:`add_security_list_rules` and :meth:`finalize_network` are
        **no-ops** for ``VcnRef``.  Any security rules required by the services
        you deploy here must already exist in the source VCN stack.

    The source stack must export the following keys (all exported by the
    ``examples/vcn`` stack out of the box):

    - ``vcn_id``
    - ``cidr_block``
    - ``public_subnet_id``
    - ``private_subnet_id``
    - ``secure_subnet_id``
    - ``public_subnet_cidr``
    - ``private_subnet_cidr``
    - ``secure_subnet_cidr``
    - ``public_security_list_id``
    - ``private_security_list_id``
    - ``secure_security_list_id``
    - ``management_subnet_id``
    - ``management_subnet_cidr``
    - ``management_security_list_id``

    Attributes:
        id: ``pulumi.Output[str]`` OCID of the referenced VCN.
        cidr_block: ``pulumi.Output[str]`` CIDR of the referenced VCN.
        public_subnet: Stub whose ``.id`` is the public subnet OCID.
        private_subnet: Stub whose ``.id`` is the private subnet OCID.
        public_security_list: Stub whose ``.id`` is the public security list
            OCID, or ``None`` if not exported by the source stack.
        private_security_list: Stub whose ``.id`` is the private security list
            OCID, or ``None`` if not exported by the source stack.
        secure_subnet: Stub whose ``.id`` is the secure subnet OCID.
        secure_security_list: Stub whose ``.id`` is the secure security list
            OCID, or ``None`` if not exported by the source stack.
        management_subnet: Stub whose ``.id`` is the management subnet OCID,
            or ``None`` if not exported by the source stack.
        management_security_list: Stub whose ``.id`` is the management
            security list OCID, or ``None`` if not exported by the source stack.

    Example::

        vcn = VcnRef.from_stack_reference("acme/networking/prod")
        cluster = OkeCluster(name="app", vcn=vcn, compartment_id=comp_id, ...)
    """

    id: pulumi.Output[str]
    cidr_block: pulumi.Output[str]
    public_subnet: _SubnetRef
    private_subnet: _SubnetRef
    public_security_list: _SecurityListRef | None
    private_security_list: _SecurityListRef | None
    secure_subnet: _SubnetRef | None
    secure_security_list: _SecurityListRef | None
    management_subnet: _SubnetRef | None
    management_security_list: _SecurityListRef | None

    def __init__(
        self,
        vcn_id: pulumi.Input[str],
        public_subnet_id: pulumi.Input[str],
        private_subnet_id: pulumi.Input[str],
        public_subnet_cidr: pulumi.Input[str],
        private_subnet_cidr: pulumi.Input[str],
        cidr_block: pulumi.Input[str] | None = None,
        public_security_list_id: pulumi.Input[str] | None = None,
        private_security_list_id: pulumi.Input[str] | None = None,
        secure_subnet_id: pulumi.Input[str] | None = None,
        secure_subnet_cidr: pulumi.Input[str] | None = None,
        secure_security_list_id: pulumi.Input[str] | None = None,
        management_subnet_id: pulumi.Input[str] | None = None,
        management_subnet_cidr: pulumi.Input[str] | None = None,
        management_security_list_id: pulumi.Input[str] | None = None,
    ) -> None:
        """Wrap existing VCN resource IDs in an OCIBlocks-compatible interface.

        Args:
            vcn_id: OCID of the existing VCN.
            public_subnet_id: OCID of the existing public subnet.
            private_subnet_id: OCID of the existing private subnet.
            public_subnet_cidr: IPv4 CIDR of the public subnet
                (e.g. ``"10.0.0.0/17"``).  Used by blocks when building
                security rules — must match the actual subnet CIDR.
            private_subnet_cidr: IPv4 CIDR of the private subnet
                (e.g. ``"10.0.128.0/17"``).
            cidr_block: IPv4 CIDR of the VCN itself.  Optional; only used for
                informational exports.
            public_security_list_id: OCID of the public security list.
                Required when using
                :meth:`~blocks.oke.cluster.OkeCluster.get_public_security_list_ids`.
            private_security_list_id: OCID of the private security list.
        """
        self.id = pulumi.Output.from_input(vcn_id)
        self.cidr_block = pulumi.Output.from_input(cidr_block) if cidr_block else self.id
        self.public_subnet = _SubnetRef(public_subnet_id)
        self.private_subnet = _SubnetRef(private_subnet_id)
        self._public_subnet_cidr: pulumi.Input[str] = public_subnet_cidr
        self._private_subnet_cidr: pulumi.Input[str] = private_subnet_cidr
        self.public_security_list = (
            _SecurityListRef(public_security_list_id) if public_security_list_id else None
        )
        self.private_security_list = (
            _SecurityListRef(private_security_list_id) if private_security_list_id else None
        )
        self.secure_subnet = _SubnetRef(secure_subnet_id) if secure_subnet_id else None
        self._secure_subnet_cidr: pulumi.Input[str] = secure_subnet_cidr or ""
        self.secure_security_list = (
            _SecurityListRef(secure_security_list_id) if secure_security_list_id else None
        )
        self.management_subnet = _SubnetRef(management_subnet_id) if management_subnet_id else None
        self._management_subnet_cidr: pulumi.Input[str] = management_subnet_cidr or ""
        self.management_security_list = (
            _SecurityListRef(management_security_list_id) if management_security_list_id else None
        )

    @classmethod
    def from_stack_reference(cls, stack_name: str) -> "VcnRef":
        """Create a :class:`VcnRef` from outputs published by another Pulumi stack.

        Args:
            stack_name: Pulumi stack reference string.

                - Pulumi Cloud: ``"<organization>/<project>/<stack>"``
                - Local backend: ``"<project>/<stack>"``

        Returns:
            A :class:`VcnRef` populated from the referenced stack's outputs.

        Example::

            vcn = VcnRef.from_stack_reference("acme/networking/prod")
        """
        ref = pulumi.StackReference(stack_name)
        return cls(
            vcn_id=ref.get_output("vcn_id"),
            public_subnet_id=ref.get_output("public_subnet_id"),
            private_subnet_id=ref.get_output("private_subnet_id"),
            secure_subnet_id=ref.get_output("secure_subnet_id"),
            public_subnet_cidr=ref.get_output("public_subnet_cidr"),
            private_subnet_cidr=ref.get_output("private_subnet_cidr"),
            secure_subnet_cidr=ref.get_output("secure_subnet_cidr"),
            cidr_block=ref.get_output("cidr_block"),
            public_security_list_id=ref.get_output("public_security_list_id"),
            private_security_list_id=ref.get_output("private_security_list_id"),
            secure_security_list_id=ref.get_output("secure_security_list_id"),
            management_subnet_id=ref.get_output("management_subnet_id"),
            management_subnet_cidr=ref.get_output("management_subnet_cidr"),
            management_security_list_id=ref.get_output("management_security_list_id"),
        )

    def add_security_list_rules(
        self,
        public_ingress: list[Any] | None = None,
        public_egress: list[Any] | None = None,
        private_ingress: list[Any] | None = None,
        private_egress: list[Any] | None = None,
        secure_ingress: list[Any] | None = None,
        secure_egress: list[Any] | None = None,
        management_ingress: list[Any] | None = None,
        management_egress: list[Any] | None = None,
    ) -> None:
        """No-op — security rules must be managed in the source VCN stack.

        Emits a Pulumi warning to alert you that rules requested by a block
        (OKE, Compute, ScalableWorkload) are **not** being applied.  Ensure
        the referenced VCN already has all required rules before deploying
        services here.

        Args:
            public_ingress: Ignored.
            public_egress: Ignored.
            private_ingress: Ignored.
            private_egress: Ignored.
            secure_ingress: Ignored.
            secure_egress: Ignored.
            management_ingress: Ignored.
            management_egress: Ignored.
        """
        _ = (public_ingress, public_egress, private_ingress, private_egress, secure_ingress, secure_egress, management_ingress, management_egress)
        pulumi.log.warn(
            "VcnRef: security rules requested by this block are not applied to the "
            "imported VCN. Add the required rules to the source stack first."
        )

    def get_public_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the public subnet CIDR.

        Returns:
            Public subnet CIDR as a ``pulumi.Input[str]``.
        """
        return self._public_subnet_cidr

    def get_private_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the private subnet CIDR.

        Returns:
            Private subnet CIDR as a ``pulumi.Input[str]``.
        """
        return self._private_subnet_cidr

    def get_secure_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the secure subnet CIDR.

        Returns:
            Secure subnet CIDR as a ``pulumi.Input[str]``.
        """
        return self._secure_subnet_cidr

    def get_management_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the management subnet CIDR.

        Returns:
            Management subnet CIDR as a ``pulumi.Input[str]``.
        """
        return self._management_subnet_cidr

    def finalize_network(self) -> None:
        """No-op — the referenced VCN network is already finalized."""


def get_resources_by_tag(vcn_instance: Vcn, tag_key: str, tag_value: str) -> list[Any]:
    """Return all child resources of a VCN that match a specific freeform tag.

    Iterates over every attribute of *vcn_instance* that exposes a
    ``freeform_tags`` property and returns those whose tag value matches.

    Args:
        vcn_instance: The :class:`Vcn` instance to inspect.
        tag_key: The freeform tag key to filter on (e.g. ``"NetworkType"``).
        tag_value: The expected tag value (e.g. ``"public"``).

    Returns:
        List of resource objects whose ``freeform_tags[tag_key] == tag_value``.
        May be empty if no resources match.
    """
    resources: list[Any] = []
    for attr_name in dir(vcn_instance):
        if hasattr(getattr(vcn_instance, attr_name), "freeform_tags"):
            resource: Any = getattr(vcn_instance, attr_name)
            if resource.freeform_tags.get(tag_key) == tag_value:
                resources.append(resource)
    return resources
