"""OCI VCN (Virtual Cloud Network) provider implementation.

This module is the canonical implementation of
`AbstractNetwork` for Oracle Cloud
Infrastructure.  It provides `Vcn`, which creates a complete OCI
network topology using a lazy initialisation (builder) pattern:

1. Construct the `Vcn` object — the VCN, gateways, and route tables are
   created immediately.
2. Other spells (OKE, Compute, ScalableWorkload) call
   `Vcn.add_security_list_rules` to accumulate their required rules.
3. The first spell to finish calls `Vcn.finalize_network`, which creates
   the security lists with all accumulated rules and then creates the
   subnets.  Subsequent calls to `finalize_network` are no-ops.

This approach keeps the OCI security-list-per-subnet count at 1, leaving
the remaining 4 slots free for future services.

**Subnet layout**

The VCN CIDR is split into four contiguous, CIDR-aligned tiers using binary
subdivision.  The same formula applies regardless of the prefix length you
choose (`/16`, `/20`, `/24`, ...):

```text
VCN  (prefix/N)
├── Private     prefix/(N+1)  — 50 %  of VCN  — NAT + Service GW
├── Secure      prefix/(N+2)  — 25 %  of VCN  — Service GW only
├── Public      prefix/(N+3)  — 12.5% of VCN  — Internet GW
└── Management  prefix/(N+3)  — 12.5% of VCN  — Service GW only
```

Examples for common prefix lengths:

| VCN  | Private (/N+1)  | Secure (/N+2)   | Public (/N+3)   | Management (/N+3) |
|------|-----------------|-----------------|-----------------|-------------------|
| /16  | /17 (32 766 h)  | /18 (16 382 h)  | /19  (8 190 h)  | /19  (8 190 h)    |
| /20  | /21  (2 046 h)  | /22  (1 022 h)  | /23    (510 h)  | /23    (510 h)    |
| /24  | /25    (126 h)  | /26     (62 h)  | /27     (30 h)  | /27     (30 h)    |

(h = usable host IPs after subtracting the OCI-reserved 5 addresses per subnet)

All four subnet tiers together exactly cover the VCN CIDR — no gaps, no overlaps.
CIDR validation (canonical form, prefix length sanity) is delegated to OCI;
the Pulumi provider will reject malformed values at plan time.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.compute import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
)
from cloudspells.core.abstractions.network import (
    AbstractNetwork,
    AbstractNetworkRef,
    EgressRule,
    IngressRule,
    SecurityRules,
)
from cloudspells.core.base import BaseResource

# Maps cloud-neutral protocol names to OCI protocol numbers.
_PROTOCOL_MAP: dict[str, str] = {
    "tcp": "6",
    "udp": "17",
    "icmp": "1",
    "all": "all",
}


def _translate_ingress_rule(
    rule: IngressRule,
) -> oci.core.SecurityListIngressSecurityRuleArgs:
    """Translate a cloud-neutral `IngressRule` to OCI `SecurityList` ingress args.

    Args:
        rule: Cloud-neutral ingress rule descriptor.

    Returns:
        OCI-specific `SecurityListIngressSecurityRuleArgs` ready for use in
        a security list resource.
    """
    proto = _PROTOCOL_MAP.get(rule.protocol, rule.protocol)
    source = "0.0.0.0/0" if rule.source == "internet" else rule.source
    kwargs: dict[str, Any] = {
        "protocol": proto,
        "source": source,
        "source_type": "CIDR_BLOCK",
        "description": rule.description,
    }
    if rule.protocol == "tcp" and (rule.port_min is not None or rule.port_max is not None):
        kwargs["tcp_options"] = oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
            min=rule.port_min or 1,
            max=rule.port_max or 65535,
        )
    return oci.core.SecurityListIngressSecurityRuleArgs(**kwargs)


def _translate_egress_rule(
    rule: EgressRule,
    svc_cidr_block: pulumi.Output[str],
) -> oci.core.SecurityListEgressSecurityRuleArgs:
    """Translate a cloud-neutral `EgressRule` to OCI `SecurityList` egress args.

    Args:
        rule: Cloud-neutral egress rule descriptor.
        svc_cidr_block: OCI Service Gateway CIDR block used when
            `rule.destination == "cloud-services"`.

    Returns:
        OCI-specific `SecurityListEgressSecurityRuleArgs` ready for use in
        a security list resource.
    """
    proto = _PROTOCOL_MAP.get(rule.protocol, rule.protocol)
    is_service = rule.destination == "cloud-services"
    destination = (
        svc_cidr_block if is_service else ("0.0.0.0/0" if rule.destination == "internet" else rule.destination)
    )
    dest_type = "SERVICE_CIDR_BLOCK" if is_service else "CIDR_BLOCK"
    kwargs: dict[str, Any] = {
        "protocol": proto,
        "destination": destination,
        "destination_type": dest_type,
        "description": rule.description,
    }
    if rule.protocol == "tcp" and (rule.port_min is not None or rule.port_max is not None):
        kwargs["tcp_options"] = oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
            min=rule.port_min or 1,
            max=rule.port_max or 65535,
        )
    return oci.core.SecurityListEgressSecurityRuleArgs(**kwargs)


class _SubnetRef:
    """Thin wrapper exposing only the `id` of an externally-managed subnet.

    Used by `VcnRef` to present subnet stubs compatible with `oci.core.Subnet`
    for the purposes of reading `.id`.  Callers that receive a `VcnRef` will
    encounter `_SubnetRef` objects on `public_subnet`, `private_subnet`,
    `secure_subnet`, and `management_subnet`.

    Attributes:
        id: `pulumi.Output[str]` OCID of the subnet.
    """

    def __init__(self, subnet_id: pulumi.Input[str]) -> None:
        self.id: pulumi.Output[str] = pulumi.Output.from_input(subnet_id)


class _SecurityListRef:
    """Thin wrapper exposing only the `id` of an externally-managed security list.

    Used by `VcnRef` to present security-list stubs compatible with
    `oci.core.SecurityList` for the purposes of reading `.id`.  Callers that
    receive a `VcnRef` will encounter `_SecurityListRef` objects on
    `public_security_list`, `private_security_list`, `secure_security_list`,
    and `management_security_list` when those IDs were provided at construction.

    Attributes:
        id: `pulumi.Output[str]` OCID of the security list.
    """

    def __init__(self, security_list_id: pulumi.Input[str]) -> None:
        self.id: pulumi.Output[str] = pulumi.Output.from_input(security_list_id)


@dataclass
class SubnetConfig:
    """Internal configuration record for a single subnet.

    Used by `Vcn._create_subnets` to hold the per-subnet parameters
    resolved during `Vcn.finalize_network`.

    Attributes:
        cidr: IPv4 CIDR block assigned to the subnet (e.g. `"10.0.0.0/17"`).
        is_public: `True` for a public subnet (instances may receive public
            IPs); `False` for a private subnet.
        dns_label: Short DNS label prefix passed to
            `BaseResource.create_dns_label`.
        ipv6_cidr: IPv6 `/64` CIDR to assign to the subnet, or `None` for
            IPv4-only.  Set automatically by `Vcn._create_subnets` when
            `ipv6_enabled=True` was passed to `Vcn.__init__`.
    """

    cidr: str
    is_public: bool
    dns_label: str
    ipv6_cidr: pulumi.Input[str] | None = None


@dataclass
class _SubnetCidrs:
    """CIDR strings for the four VCN subnet tiers.

    Produced by `Vcn._split_tiers` and consumed by CIDR accessor methods
    and `_create_subnets`.  Named fields make the tier-to-CIDR mapping
    self-documenting and eliminate the implicit index contract.

    Attributes:
        public: CIDR for the public (internet-facing) tier.
        private: CIDR for the private (application) tier.
        secure: CIDR for the secure (data) tier.
        management: CIDR for the management tier.
    """

    public: str
    private: str
    secure: str
    management: str


class Vcn(BaseResource, AbstractNetwork):
    """OCI Virtual Cloud Network with subnets, gateways, and security lists.

    Creates the complete OCI network foundation required by all other
    CloudSpells components:

    - One VCN with a configurable CIDR block (default `"10.0.0.0/18"`).
    - Internet Gateway, NAT Gateway, and Service Gateway.
    - Four route tables — one per subnet tier — wired to the appropriate
      gateways (see module docstring for routing policy per tier).
    - Four security lists populated via the builder pattern.
    - Four contiguous, CIDR-aligned subnets auto-calculated by binary
      subdivision of the VCN CIDR (private 50 %, secure 25 %, public 12.5 %,
      management 12.5 %).  Any valid prefix length works — `/16`, `/20`,
      `/24`, etc.  See the module docstring for a worked example table.

    Security lists and subnets are **not** created in `__init__`.  They
    are created only when `finalize_network` is called.  Other spells add
    their rules via `add_security_list_rules` **before** that call.

    Attributes:
        cidr_block: Plain `str` IPv4 CIDR block for the VCN.  A `str` (not
            `pulumi.Output[str]`) is required because subnet CIDR splitting
            runs synchronously at construction time via `ipaddress.ip_network`.
        vcn: The underlying `oci.core.Vcn` resource.
        internet_gateway: Internet Gateway resource.
        nat_gateway: NAT Gateway resource.
        service_gateway: Service Gateway resource.
        drg: Dynamic Routing Gateway resource when `drg=True`, else `None`.
            Attach VPN IPsec connections or FastConnect virtual circuits to this
            resource to establish on-premise connectivity.
        drg_attachment: DRG–VCN attachment resource when `drg=True`, else `None`.
        public_security_list: Public-subnet security list (available after
            `finalize_network`).
        private_security_list: Private-subnet security list (available after
            `finalize_network`).
        public_route_table: Route table for the public subnet.
        private_route_table: Route table for the private subnet.
        public_subnet: Public subnet resource, or `None` before
            `finalize_network`.
        private_subnet: Private subnet resource, or `None` before
            `finalize_network`.
        secure_subnet: Secure (data) subnet resource, or `None` before
            `finalize_network`.  No internet path — Service Gateway only.
        secure_security_list: Secure-subnet security list (available after
            `finalize_network`).
        secure_route_table: Route table for the secure subnet (Service Gateway
            only — no default route, no NAT).
        management_subnet: Management subnet resource, or `None` before
            `finalize_network`.  No internet path — Service Gateway
            only.  For monitoring agents, bastion service, VPN endpoints,
            and internal tooling.
        management_security_list: Management-subnet security list (available
            after `finalize_network`).
        management_route_table: Route table for the management subnet
            (Service Gateway only — same isolation policy as secure).
        id: `pulumi.Output[str]` of the VCN OCID.
        default_security_list: The VCN's built-in default security list,
            overridden to have zero rules so it can never silently permit
            traffic.  OCI automatically attaches the default security list
            to every subnet; neutralising it means only the per-tier lists
            managed by the builder pattern are in effect.
        flow_logs: `VcnFlowLogs` component when `flow_logs=True` was passed
            to `__init__`, or `None` when flow logging is disabled.
            Available after `finalize_network` is called.

    Usage patterns:

    1. **Standalone VCN** (manual finalisation required):

        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
        vcn.finalize_network()
        # vcn.public_subnet and vcn.private_subnet are now available
        ```

    2. **With other CloudSpells spells** (automatic finalisation):

        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
        cluster = OkeCluster(vcn=vcn, ...)   # calls finalize_network internally
        # vcn.public_subnet and vcn.private_subnet are now available
        ```
    """

    SUBNET_PUBLIC: SubnetTier = "public"
    SUBNET_PRIVATE: SubnetTier = "private"
    SUBNET_SECURE: SubnetTier = "secure"
    SUBNET_MANAGEMENT: SubnetTier = "management"

    cidr_block: str
    vcn: oci.core.Vcn
    internet_gateway: oci.core.InternetGateway
    nat_gateway: oci.core.NatGateway
    service_gateway: oci.core.ServiceGateway
    drg: oci.core.Drg | None
    drg_attachment: oci.core.DrgAttachment | None
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
    default_security_list: oci.core.DefaultSecurityList
    id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
        cidr_block: str | None = None,
        additional_cidr_blocks: list[pulumi.Input[str]] | None = None,
        ipv6_enabled: bool = False,
        flow_logs: bool = False,
        flow_logs_retention: int = 90,
        drg: bool = False,
        on_premise_cidrs: list[str] | None = None,
        nat_public_ip_id: pulumi.Input[str] | None = None,
        nat_block_traffic: bool = False,
        dhcp_options_id: pulumi.Input[str] | None = None,
        defined_tags: pulumi.Input[dict[str, pulumi.Input[str]]] | None = None,
    ) -> None:
        """Create a VCN with gateways and route tables.

        Security lists and subnets are not created here; call
        `finalize_network` (directly or indirectly via another spell)
        once all security rules have been accumulated.

        Args:
            name: Logical name for this VCN (e.g. `"lab"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            opts: Pulumi resource options forwarded to the component.
            cidr_block: IPv4 CIDR for the VCN in canonical form
                (no host bits set, e.g. `"10.0.0.0/16"` not
                `"10.0.1.0/16"`).  Must be a plain Python `str`, not a
                `pulumi.Output[str]` — subnet CIDR splitting runs
                synchronously at construction time via `ipaddress.ip_network`
                and cannot accept an unresolved `Output`.
                Defaults to `"10.0.0.0/18"`.
                Any prefix length is accepted; the four tier subnets are
                derived automatically by binary subdivision — private gets
                50 % (prefix+1), secure 25 % (prefix+2), public and
                management 12.5 % each (prefix+3).  See the module
                docstring for a full example table across common prefix
                lengths.
            additional_cidr_blocks: Extra IPv4 CIDRs to attach to the VCN
                (e.g. `["172.16.0.0/24"]`).  OCI supports multiple
                non-overlapping CIDRs on a single VCN — useful when the
                primary CIDR overlaps with a VCN peer.  Only `cidr_block`
                drives subnet subdivision; additional CIDRs are attached to
                the VCN resource only.  Defaults to `None` (single-CIDR
                VCN).
            ipv6_enabled: When `True`, enables IPv6 on the VCN and assigns
                each subnet a `/64` block derived from the OCI-assigned
                `/56` prefix.  Tier slot assignments mirror the IPv4 layout
                — private gets `/64[0]`, secure `/64[1]`, public `/64[2]`,
                management `/64[3]`.  Defaults to `False`.
            flow_logs: When `True`, a `VcnFlowLogs` component is created
                automatically inside `finalize_network`, capturing accepted
                and rejected traffic on all four subnet tiers.  Defaults
                to `False`.  The created component is accessible via
                `self.flow_logs`.
            flow_logs_retention: Log retention in days when `flow_logs=True`.
                Accepted values are `30`, `60`, `90`, `120`, `150`, `180`.
                Defaults to `90`.
            drg: When `True`, a Dynamic Routing Gateway and its VCN
                attachment are created.  Required for Site-to-Site VPN and
                FastConnect on-premise connectivity.  Defaults to `False`.
                The created resources are accessible via `self.drg` and
                `self.drg_attachment`.
            on_premise_cidrs: List of on-premise IPv4 CIDRs to route via
                the DRG (e.g. `["10.10.0.0/16", "192.168.1.0/24"]`).
                Routes are added to the private, secure, and management
                route tables.  Ignored when `drg=False`.  When `drg=True`
                but this list is omitted, the DRG is created and attached
                but no static routes are injected — use this when routing
                will be handled dynamically by BGP (FastConnect) or static
                routes configured on the VPN gateway side.
            nat_public_ip_id: OCID of a reserved public IP to assign to
                the NAT Gateway.  When `None` (the default) OCI allocates
                an ephemeral public IP automatically.  Supply a reserved IP
                when a predictable, static egress address is required — for
                example, to whitelist the VCN's outbound traffic at a
                customer firewall or third-party API allow-list.
            nat_block_traffic: When `True`, the NAT Gateway blocks all
                outbound traffic without being deleted.  Defaults to
                `False`.  Use this to temporarily cut egress during a
                security incident or maintenance window — the gateway and
                its reserved IP are preserved so traffic can be restored
                instantly by re-deploying with `nat_block_traffic=False`.
            dhcp_options_id: OCID of a custom DHCP options set to attach
                to all four subnet tiers.  When `None` (the default) OCI
                uses the VCN's built-in defaults, which resolve DNS via the
                internet and the VCN resolver.  Supply a custom DHCP
                options set to redirect DNS queries to a private resolver —
                required for split-horizon DNS in hybrid (on-premise +
                cloud) environments.
            defined_tags: OCI defined tags applied to every resource in
                this VCN (VCN, gateways, route tables, security lists, and
                subnets), in `{"namespace": {"key": "value"}}` format.
                Defined tags are namespace-qualified key/value pairs managed
                by OCI Tag Namespaces and are required for enterprise cost
                tracking, policy enforcement, and governance.  When `None`
                (the default) no defined tags are applied.  Example:
                `{"Operations": {"CostCenter": "42"}, "Project": {"Env": "prod"}}`.

        Raises:
            ValueError: If `cidr_block` has host bits set (e.g.
                `"10.0.1.0/16"` instead of `"10.0.0.0/16"`).  OCI CIDR
                strings must be in canonical form — the address must be the
                network address for the given prefix length.
        """
        super().__init__("custom:network:Vcn", name, compartment_id, stack_name, opts)
        self.cidr_block = cidr_block or "10.0.0.0/18"
        self._additional_cidr_blocks: list[pulumi.Input[str]] = additional_cidr_blocks or []
        self._ipv6_enabled = ipv6_enabled
        self._flow_logs_enabled = flow_logs
        self._flow_logs_retention = flow_logs_retention
        self._drg_enabled = drg
        self._on_premise_cidrs: list[str] = on_premise_cidrs or []
        self._nat_public_ip_id = nat_public_ip_id
        self._nat_block_traffic = nat_block_traffic
        self._dhcp_options_id = dhcp_options_id
        self._defined_tags = defined_tags

        # Initialize the subnet and optional gateway properties
        self.public_subnet = None
        self.private_subnet = None
        self.secure_subnet = None
        self.management_subnet = None
        self.flow_logs = None
        self.drg = None
        self.drg_attachment = None

        # Storage for security list rules (builder pattern).
        # Populated by add_security_list_rules() calls from other spells.
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

        # Fingerprints of ambient security-list rules already added via
        # _add_unique_security_list_rules().  Prevents duplicate rules when
        # multiple NSGs of the same role are created (e.g. five APP_SERVER
        # NSGs should not add the services-egress rule five times).
        self._applied_ambient_rule_fingerprints: set[str] = set()

        self._subnet_cidrs: _SubnetCidrs = self._split_tiers(self.cidr_block)

        # Seed the standard OCI path-MTU and destination-unreachable ICMP rules
        # that the OCI VCN wizard adds to the public security list by default.
        self._public_ingress_rules.extend([
            oci.core.SecurityListIngressSecurityRuleArgs(
                protocol="1",
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                description="ICMP 3,4: Destination Unreachable / Fragmentation Needed",
                icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                    type=3,
                    code=4,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                protocol="1",
                source=self.cidr_block,
                source_type="CIDR_BLOCK",
                description="ICMP traffic for: 3 Destination Unreachable",
                icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                    type=3,
                ),
            ),
        ])

        # Resolve the OCI "All Services" bundle lazily via get_services_output()
        # so no blocking API call is made during __init__.  Both values are
        # pulumi.Output[str] and are accepted wherever pulumi.Input[str] is
        # expected (ServiceGateway, route rules, security-rule translation).
        all_services = oci.core.get_services_output()
        self._svc_service_id: pulumi.Output[str] = all_services.services.apply(
            lambda svcs: next(s.id for s in svcs if s.cidr_block.startswith("all-"))
        )
        self._svc_cidr_block: pulumi.Output[str] = all_services.services.apply(
            lambda svcs: next(s.cidr_block for s in svcs if s.cidr_block.startswith("all-"))
        )

        # Create base infrastructure (NOT security lists or subnets yet).
        self._create_vcn()
        self._create_gateways()
        self._create_route_tables()

    @staticmethod
    def _split_tiers(cidr: str) -> _SubnetCidrs:
        """Split a VCN CIDR into four contiguous, CIDR-aligned tiers.

        Uses binary subdivision — each tier takes exactly half of the
        remaining address space:

        ```text
        VCN (prefix/N)  ──────────────────────────────────────── 100 %
        ├── Private  (prefix/N+1) ─────────────────────────────   50 %
        └── remainder (prefix/N+1)
            ├── Secure  (prefix/N+2) ──────────────────────────   25 %
            └── remainder (prefix/N+2)
                ├── Public      (prefix/N+3) ───────────────────  12.5 %
                └── Management  (prefix/N+3) ───────────────────  12.5 %
        ```

        The four tiers are placed in ascending address order so private
        occupies the naturally aligned lower half (guaranteed CIDR alignment).
        All four tiers together exactly reconstruct the original VCN CIDR —
        no gaps, no overlaps.

        The same formula applies for any prefix length:

        - `/16` → private `/17`, secure `/18`, public `/19`, mgmt `/19`
        - `/20` → private `/21`, secure `/22`, public `/23`, mgmt `/23`
        - `/24` → private `/25`, secure `/26`, public `/27`, mgmt `/27`

        Args:
            cidr: Canonical VCN CIDR string with no host bits set
                (e.g. `"10.0.0.0/16"`).

        Returns:
            `_SubnetCidrs` with named fields `public`, `private`, `secure`,
            and `management`, each a CIDR string for the corresponding tier.

        Example:
            ```python
            Vcn._split_tiers("10.0.0.0/16")
            # _SubnetCidrs(public="10.0.192.0/19", private="10.0.0.0/17",
            #              secure="10.0.128.0/18", management="10.0.224.0/19")

            Vcn._split_tiers("172.16.0.0/20")
            # _SubnetCidrs(public="172.16.12.0/23", private="172.16.0.0/21",
            #              secure="172.16.8.0/22",  management="172.16.14.0/23")
            ```
        """
        net = ipaddress.ip_network(cidr, strict=True)
        halves = list(net.subnets(prefixlen_diff=1))
        private = halves[0]  # 50 %

        quarters = list(halves[1].subnets(prefixlen_diff=1))
        secure = quarters[0]  # 25 %

        eighths = list(quarters[1].subnets(prefixlen_diff=1))
        public = eighths[0]  # 12.5 %
        management = eighths[1]  # 12.5 %

        return _SubnetCidrs(
            public=str(public),
            private=str(private),
            secure=str(secure),
            management=str(management),
        )

    def _compute_ipv6_subnet_cidr(self, idx: int) -> pulumi.Output[str]:
        """Derive the `idx`-th `/64` block from the VCN's OCI-assigned IPv6 `/56`.

        Called by `_create_subnets` when `ipv6_enabled=True`.  Tier slot
        assignments are stable:

        ```text
        0 → private   (mirrors the IPv4 lower-half convention)
        1 → secure
        2 → public
        3 → management
        ```

        Args:
            idx: Zero-based index into the `/56` subnet list.  Must be in
                `[0, 255]` (a `/56` contains 256 `/64` blocks).

        Returns:
            A `pulumi.Output[str]` resolving to the IPv6 CIDR after the VCN
            has been created and OCI has assigned its IPv6 prefix.

        Raises:
            RuntimeError: If called when `ipv6_enabled=False`.
        """
        if not self._ipv6_enabled:
            raise RuntimeError("_compute_ipv6_subnet_cidr called when IPv6 is not enabled on this VCN")
        return self.vcn.ipv6cidr_blocks.apply(
            lambda blocks: str(list(ipaddress.ip_network(blocks[0]).subnets(new_prefix=64))[idx])
        )

    # ------------------------------------------------------------------
    # Private infrastructure creation helpers
    # ------------------------------------------------------------------

    def _create_vcn(self) -> None:
        """Create the `oci.core.Vcn` resource, neutralise its default security list, and store its OCID as `self.id`.

        OCI automatically attaches the VCN's built-in default security list to
        every subnet.  That list ships with a wide-open egress rule
        (`0.0.0.0/0`, all protocols) which would silently override the
        per-tier security posture managed by the builder pattern.  The
        `oci.core.DefaultSecurityList` resource takes ownership of the
        existing default list and replaces its rules with empty sets,
        ensuring only the per-tier lists constructed in `_create_security_lists`
        are in effect.
        """
        resource_name = self.create_resource_name("vcn")
        self.vcn = oci.core.Vcn(
            resource_name,
            compartment_id=self.compartment_id,
            cidr_blocks=[self.cidr_block, *self._additional_cidr_blocks],
            is_ipv6enabled=self._ipv6_enabled,
            display_name=resource_name,
            dns_label=self.create_dns_label("vcn"),
            freeform_tags=self.create_freeform_tags(resource_name, "vcn", {"NetworkTier": "core"}),
            defined_tags=self._defined_tags,
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.id = self.vcn.id

        # Neutralise the VCN default security list so it never contributes
        # traffic rules.  OCI attaches it to every subnet automatically;
        # overriding it with empty rule sets prevents it from shadowing the
        # per-tier lists we manage via the builder pattern.
        sl_default_name = self.create_resource_name("sl-default")
        self.default_security_list = oci.core.DefaultSecurityList(
            sl_default_name,
            compartment_id=self.compartment_id,
            manage_default_resource_id=self.vcn.default_security_list_id,
            ingress_security_rules=[],
            egress_security_rules=[],
            display_name=sl_default_name,
            freeform_tags=self.create_network_resource_tags(sl_default_name, "security-list", "default", "default"),
            defined_tags=self._defined_tags,
            opts=pulumi.ResourceOptions(parent=self, depends_on=[self.vcn]),
        )

    def _create_gateways(self) -> None:
        """Create Internet, NAT, Service, and (optionally) Dynamic Routing gateways."""
        # Internet Gateway
        igw_name = self.create_resource_name("igw")
        self.internet_gateway = oci.core.InternetGateway(
            igw_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=igw_name,
            enabled=True,
            freeform_tags=self.create_gateway_tags(igw_name, "internet"),
            defined_tags=self._defined_tags,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # NAT Gateway
        natgw_name = self.create_resource_name("natgw")
        self.nat_gateway = oci.core.NatGateway(
            natgw_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=natgw_name,
            block_traffic=self._nat_block_traffic,
            public_ip_id=self._nat_public_ip_id,
            freeform_tags=self.create_gateway_tags(natgw_name, "nat"),
            defined_tags=self._defined_tags,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Service Gateway
        svcgw_name = self.create_resource_name("svcgw")
        self.service_gateway = oci.core.ServiceGateway(
            svcgw_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            services=[oci.core.ServiceGatewayServiceArgs(service_id=self._svc_service_id)],
            display_name=svcgw_name,
            freeform_tags=self.create_gateway_tags(svcgw_name, "service"),
            defined_tags=self._defined_tags,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Dynamic Routing Gateway (opt-in — required for VPN / FastConnect)
        if self._drg_enabled:
            drg_name = self.create_resource_name("drg")
            self.drg = oci.core.Drg(
                drg_name,
                compartment_id=self.compartment_id,
                display_name=drg_name,
                freeform_tags=self.create_gateway_tags(drg_name, "drg"),
                defined_tags=self._defined_tags,
                opts=pulumi.ResourceOptions(parent=self),
            )

            drg_attach_name = self.create_resource_name("drg-attach")
            self.drg_attachment = oci.core.DrgAttachment(
                drg_attach_name,
                drg_id=self.drg.id,
                display_name=drg_attach_name,
                network_details=oci.core.DrgAttachmentNetworkDetailsArgs(
                    type="VCN",
                    id=self.vcn.id,
                ),
                freeform_tags=self.create_gateway_tags(drg_attach_name, "drg-attachment"),
                opts=pulumi.ResourceOptions(parent=self),
            )

    def _create_security_lists(self) -> None:
        """Create all four per-tier security lists with accumulated rules.

        Called exactly once by `finalize_network`.  Rules were accumulated
        in the four `_*_ingress_rules` / `_*_egress_rules` lists via
        `add_security_list_rules` calls from other spells.

        After this method returns all four `*_security_list` attributes are set.
        """

        def _make(
            tier: str,
            ingress: list[oci.core.SecurityListIngressSecurityRuleArgs],
            egress: list[oci.core.SecurityListEgressSecurityRuleArgs],
        ) -> oci.core.SecurityList:
            name = self.create_resource_name(f"sl-{tier}")
            return oci.core.SecurityList(
                name,
                compartment_id=self.compartment_id,
                vcn_id=self.vcn.id,
                display_name=name,
                ingress_security_rules=ingress,
                egress_security_rules=egress,
                freeform_tags=self.create_network_resource_tags(name, "security-list", tier, tier),
                defined_tags=self._defined_tags,
                opts=pulumi.ResourceOptions(parent=self),
            )

        self.public_security_list = _make("public", self._public_ingress_rules, self._public_egress_rules)
        self.private_security_list = _make("private", self._private_ingress_rules, self._private_egress_rules)
        self.secure_security_list = _make("secure", self._secure_ingress_rules, self._secure_egress_rules)
        self.management_security_list = _make(
            "management", self._management_ingress_rules, self._management_egress_rules
        )

    def _create_route_tables(self) -> None:
        """Create public and private route tables wired to the correct gateways.

        - Public route table: default route (`0.0.0.0/0`) via the Internet
          Gateway.
        - Private route table: default route via the NAT Gateway; OCI service
          CIDR via the Service Gateway; per-CIDR DRG routes when configured.
        - Secure route table: OCI service CIDR via the Service Gateway only;
          per-CIDR DRG routes when configured.
          No default route — instances in the secure tier have no internet path.
        - Management route table: OCI service CIDR via the Service Gateway;
          per-CIDR DRG routes when configured.  Same isolation policy as secure.
        """
        private_route_rules = [
            oci.core.RouteTableRouteRuleArgs(
                destination="0.0.0.0/0",
                network_entity_id=self.nat_gateway.id,
            ),
            oci.core.RouteTableRouteRuleArgs(
                destination=self._svc_cidr_block,
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
                destination=self._svc_cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                network_entity_id=self.service_gateway.id,
            ),
        ]

        management_route_rules = [
            oci.core.RouteTableRouteRuleArgs(
                destination=self._svc_cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                network_entity_id=self.service_gateway.id,
            ),
        ]

        # Inject per-CIDR DRG routes into private, secure, and management tiers.
        # Public subnet is intentionally excluded — on-premise traffic must not
        # enter or exit through the internet-facing tier.
        if self._drg_enabled and self._on_premise_cidrs and self.drg is not None:
            drg_id = self.drg.id
            for cidr in self._on_premise_cidrs:
                for route_rules in (private_route_rules, secure_route_rules, management_route_rules):
                    route_rules.append(
                        oci.core.RouteTableRouteRuleArgs(
                            destination=cidr,
                            network_entity_id=drg_id,
                        )
                    )

        def _make_rt(tier: str, rules: list[oci.core.RouteTableRouteRuleArgs]) -> oci.core.RouteTable:
            name = self.create_resource_name(f"rt-{tier}")
            return oci.core.RouteTable(
                name,
                compartment_id=self.compartment_id,
                vcn_id=self.vcn.id,
                display_name=name,
                route_rules=rules,
                freeform_tags=self.create_network_resource_tags(name, "route-table", tier, tier),
                defined_tags=self._defined_tags,
                opts=pulumi.ResourceOptions(parent=self),
            )

        self.public_route_table = _make_rt("public", public_route_rules)
        self.private_route_table = _make_rt("private", private_route_rules)
        self.secure_route_table = _make_rt("secure", secure_route_rules)
        self.management_route_table = _make_rt("management", management_route_rules)

    def _create_subnet(
        self,
        subnet_name: str,
        config: SubnetConfig,
        security_list: oci.core.SecurityList,
        route_table: oci.core.RouteTable,
        tier: str,
    ) -> oci.core.Subnet:
        """Create a single OCI subnet resource.

        Args:
            subnet_name: Fully-qualified OCI resource name for the subnet.
            config: `SubnetConfig` carrying CIDR, visibility, and DNS
                label for this subnet.
            security_list: Security list to attach to the subnet.
            route_table: Route table to attach to the subnet.
            tier: Subnet tier name — `"public"`, `"private"`, `"secure"`, or
                `"management"`.  Used for the `NetworkType` and `SubnetGroup`
                freeform tags so each tier is correctly identified in OCI
                tag-based queries.

        Returns:
            The newly created `oci.core.Subnet` resource.
        """
        return oci.core.Subnet(
            subnet_name,
            compartment_id=self.compartment_id,
            security_list_ids=[security_list.id],
            vcn_id=self.vcn.id,
            cidr_block=config.cidr,
            # IPv6 CIDR is None for IPv4-only VCNs; Pulumi ignores None args.
            ipv6cidr_block=config.ipv6_cidr,
            display_name=subnet_name,
            dns_label=self.create_dns_label(config.dns_label),
            prohibit_public_ip_on_vnic=not config.is_public,
            prohibit_internet_ingress=not config.is_public,
            route_table_id=route_table.id,
            dhcp_options_id=self._dhcp_options_id,
            freeform_tags=self.create_network_resource_tags(
                subnet_name, "subnet", tier, tier, {"CidrRange": config.cidr}
            ),
            defined_tags=self._defined_tags,
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_subnets(self, subnet_cidrs: _SubnetCidrs) -> None:
        """Create public, private, secure, and management subnets.

        Args:
            subnet_cidrs: Named CIDR strings from `_split_tiers`.
        """
        public_cidr, private_cidr, secure_cidr, management_cidr = (
            subnet_cidrs.public,
            subnet_cidrs.private,
            subnet_cidrs.secure,
            subnet_cidrs.management,
        )

        # IPv6 slot assignments mirror the IPv4 tier layout: private=0
        # (largest tier), secure=1, public=2, management=3.  Stable indices
        # ensure subnets always get the same /64 on re-plan.
        subnet_configs: dict[str, SubnetConfig] = {
            "public": SubnetConfig(
                public_cidr,
                True,
                "pub",
                self._compute_ipv6_subnet_cidr(2) if self._ipv6_enabled else None,
            ),
            "private": SubnetConfig(
                private_cidr,
                False,
                "priv",
                self._compute_ipv6_subnet_cidr(0) if self._ipv6_enabled else None,
            ),
            "secure": SubnetConfig(
                secure_cidr,
                False,
                "sec",
                self._compute_ipv6_subnet_cidr(1) if self._ipv6_enabled else None,
            ),
            "management": SubnetConfig(
                management_cidr,
                False,
                "mgmt",
                self._compute_ipv6_subnet_cidr(3) if self._ipv6_enabled else None,
            ),
        }

        for tier, config in subnet_configs.items():
            security_list: oci.core.SecurityList = getattr(self, f"{tier}_security_list")
            route_table: oci.core.RouteTable = getattr(self, f"{tier}_route_table")

            subnet_name: str = self.create_resource_name(f"sn-{tier}")
            setattr(
                self,
                f"{tier}_subnet",
                self._create_subnet(subnet_name, config, security_list, route_table, tier),
            )

    def _inject_baseline_rules(self) -> None:
        """Inject mandatory baseline rules into all four security lists.

        Called unconditionally at the start of `finalize_network` so these
        rules are always present regardless of which spells have contributed
        their own rules.

        **NAT Gateway egress — private tier:**

        - All protocols to `0.0.0.0/0`.  Required so that instances in the
          private subnet can reach the internet via the NAT Gateway.  OCI
          security lists are whitelist-only — without this rule, packets are
          dropped before they ever reach the gateway even though the route
          table is correctly wired.

        **Service Gateway egress — private / secure / management tiers:**

        - All protocols to the OCI service CIDR (`SERVICE_CIDR_BLOCK`).
          Required so that instances on all internal tiers can reach OCI
          services (Object Storage, Monitoring, Logging, Container Registry,
          etc.) through the Service Gateway without a public internet path.
          Without this rule, those packets are dropped despite the Service
          Gateway being present and the route rule pointing at it.

        """
        # NAT Gateway: allow all outbound from the private subnet.
        # Without this the security list drops packets before they reach the
        # gateway, even though the route table is correctly wired.
        nat_egress = oci.core.SecurityListEgressSecurityRuleArgs(
            protocol="all",
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            description="Egress to internet via NAT Gateway",
        )

        # Service Gateway: allow all outbound to the OCI service CIDR from
        # every internal tier.  Required so instances can reach OCI services
        # (Object Storage, Monitoring, Logging, etc.) without a public path.
        svc_egress = oci.core.SecurityListEgressSecurityRuleArgs(
            protocol="all",
            destination=self._svc_cidr_block,
            destination_type="SERVICE_CIDR_BLOCK",
            description="Egress to OCI services via Service Gateway",
        )

        self.add_security_list_rules(
            private_egress=[nat_egress, svc_egress],
            secure_egress=[svc_egress],
            management_egress=[svc_egress],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _add_unique_security_list_rules(
        self,
        fingerprint: str,
        public_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        public_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
        private_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        private_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
        secure_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        secure_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
        management_ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        management_egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
    ) -> None:
        """Add security list rules only if fingerprint has not been seen before.

        Prevents duplicate rules when multiple NSGs of the same role are created
        (e.g. five `APP_SERVER` NSGs should not write the services-egress rule
        five times to the private security list).  Each unique ambient rule is
        identified by a short string fingerprint chosen by the caller.

        This is an internal helper — callers are `Nsg`
        role and relationship methods.  External code should use
        `add_security_list_rules` directly.

        Args:
            fingerprint: Unique string identifying this rule (e.g.
                `"private-egress-all-services"`).  Subsequent calls with the
                same fingerprint are silently ignored.
            public_ingress: Ingress rules to add to the public security list.
            public_egress: Egress rules to add to the public security list.
            private_ingress: Ingress rules to add to the private security list.
            private_egress: Egress rules to add to the private security list.
            secure_ingress: Ingress rules to add to the secure security list.
            secure_egress: Egress rules to add to the secure security list.
            management_ingress: Ingress rules to add to the management list.
            management_egress: Egress rules to add to the management list.

        Raises:
            RuntimeError: If called after `finalize_network`.
        """
        if fingerprint in self._applied_ambient_rule_fingerprints:
            return
        self._applied_ambient_rule_fingerprints.add(fingerprint)
        self.add_security_list_rules(
            public_ingress=public_ingress,
            public_egress=public_egress,
            private_ingress=private_ingress,
            private_egress=private_egress,
            secure_ingress=secure_ingress,
            secure_egress=secure_egress,
            management_ingress=management_ingress,
            management_egress=management_egress,
        )

    def export(self) -> None:
        """Export the canonical VCN stack outputs for cross-stack consumption.

        Publishes the fourteen keys that `VcnRef.from_stack_reference`
        expects, so any stack using a standalone `Vcn` can be referenced by
        another stack without additional configuration.

        Calls `finalize_network` automatically if it has not been called
        yet, so no explicit call is needed before `export()`.

        Raises:
            RuntimeError: If any of the four subnets are `None` after
                `finalize_network` completes (indicates an internal
                inconsistency — should not occur in normal use).

        Example:
            ```python
            vcn = Vcn(name="lab", compartment_id=comp_id)
            vcn.export()  # finalize_network() is called automatically
            ```
        """
        self.finalize_network()
        if self.public_subnet is None:
            raise RuntimeError("finalize_network() must be called before export()")
        if self.private_subnet is None:
            raise RuntimeError("finalize_network() must be called before export()")
        if self.secure_subnet is None:
            raise RuntimeError("finalize_network() must be called before export()")
        if self.management_subnet is None:
            raise RuntimeError("finalize_network() must be called before export()")
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
        if self.drg is not None and self.drg_attachment is not None:
            pulumi.export("drg_id", self.drg.id)
            pulumi.export("drg_attachment_id", self.drg_attachment.id)
        if self.flow_logs is not None:
            pulumi.export("network_audit_log_group_id", self.flow_logs.log_group_id)

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

        Uses the builder pattern: rules contributed by different spells are
        collected here and applied together when `finalize_network` is
        called.  This ensures only a single security list per subnet is
        created, leaving the remaining OCI slots free for future services.

        This method **must** be called **before** `finalize_network`.

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
            RuntimeError: If called after `finalize_network` has already
                been called.

        Example:
            ```python
            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")

            vcn.add_security_list_rules(
                public_ingress=[...api_rules...],
                private_ingress=[...worker_rules...],
            )

            vcn.finalize_network()
            ```
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

    def add_security_rules(self, rules: SecurityRules) -> None:
        """Accumulate cloud-neutral security rules by translating them to OCI args.

        Converts each `IngressRule` / `EgressRule` into the corresponding
        `oci.core.SecurityList*Args` and delegates to
        `add_security_list_rules`.

        Symbolic source / destination values are resolved as follows:

        - `"internet"`       → `"0.0.0.0/0"` with type `CIDR_BLOCK`.
        - `"cloud-services"` → OCI Service Gateway CIDR block with type
          `SERVICE_CIDR_BLOCK`.

        Args:
            rules: Cloud-neutral rule descriptors to merge into this
                VCN's pending security list rule set.

        Raises:
            RuntimeError: If called after `finalize_network` has
                already been called.

        Example:
            ```python
            from cloudspells.core.abstractions.network import (
                SecurityRules, IngressRule, EgressRule,
            )

            rules = SecurityRules(
                public_ingress=[IngressRule(protocol="tcp", source="internet", port_min=443, port_max=443)],
                private_egress=[EgressRule(protocol="tcp", destination="cloud-services", port_min=443, port_max=443)],
            )
            vcn.add_security_rules(rules)
            vcn.finalize_network()
            ```
        """
        self.add_security_list_rules(
            public_ingress=[_translate_ingress_rule(r) for r in rules.public_ingress],
            public_egress=[_translate_egress_rule(r, self._svc_cidr_block) for r in rules.public_egress],
            private_ingress=[_translate_ingress_rule(r) for r in rules.private_ingress],
            private_egress=[_translate_egress_rule(r, self._svc_cidr_block) for r in rules.private_egress],
            secure_ingress=[_translate_ingress_rule(r) for r in rules.secure_ingress],
            secure_egress=[_translate_egress_rule(r, self._svc_cidr_block) for r in rules.secure_egress],
            management_ingress=[_translate_ingress_rule(r) for r in rules.management_ingress],
            management_egress=[_translate_egress_rule(r, self._svc_cidr_block) for r in rules.management_egress],
        )

    def get_public_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the public subnet CIDR.

        Available immediately after construction (before
        `finalize_network`), so other spells can use it when building
        their security rules.

        Returns:
            Public subnet CIDR (e.g. `"10.0.48.0/21"` for the default
            `10.0.0.0/18` VCN).
        """
        return self._subnet_cidrs.public

    def get_private_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the private subnet CIDR.

        Available immediately after construction (before
        `finalize_network`), so other spells can use it when building
        their security rules.

        Returns:
            Private subnet CIDR (e.g. `"10.0.0.0/19"` for the default
            `10.0.0.0/18` VCN).
        """
        return self._subnet_cidrs.private

    def get_secure_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the secure subnet CIDR.

        Available immediately after construction (before
        `finalize_network`), so other spells can use it when building
        their security rules.

        Returns:
            Secure subnet CIDR (e.g. `"10.0.32.0/20"` for the default
            `10.0.0.0/18` VCN).
        """
        return self._subnet_cidrs.secure

    def get_management_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the management subnet CIDR.

        Available immediately after construction (before
        `finalize_network`), so other spells can use it when building
        their security rules.

        Returns:
            Management subnet CIDR (e.g. `"10.0.56.0/21"` for the default
            `10.0.0.0/18` VCN).
        """
        return self._subnet_cidrs.management

    def finalize_network(self) -> None:
        """Create security lists and subnets with all accumulated rules.

        This method is **idempotent** — only the first call has any effect;
        subsequent calls return immediately.  It is invoked automatically by
        other CloudSpells spells (OKE, Compute, ScalableWorkload) at the end
        of their `__init__` methods.  Call it explicitly only when using
        `Vcn` in standalone mode (without other spells).

        After this method returns:

        - `self.public_security_list` is set.
        - `self.private_security_list` is set.
        - `self.secure_security_list` is set.
        - `self.management_security_list` is set.
        - `self.public_subnet` is set.
        - `self.private_subnet` is set.
        - `self.secure_subnet` is set.
        - `self.management_subnet` is set.
        - `self.flow_logs` is set when `flow_logs=True` was passed to
          `__init__`; it remains `None` otherwise.

        Raises:
            RuntimeError: If `compartment_id` is `None` when
                `flow_logs=True` (indicates construction was incomplete).

        Example:
            ```python
            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
            vcn.finalize_network()
            # vcn.public_subnet is now available
            ```
        """
        if self._security_lists_finalized:
            return

        self._inject_baseline_rules()
        self._create_security_lists()
        self._create_subnets(self._subnet_cidrs)

        self._security_lists_finalized = True

        if self._flow_logs_enabled:
            from .network_logging import VcnFlowLogs  # lazy import avoids circular dependency

            if self.compartment_id is None:
                raise RuntimeError("Vcn requires a compartment_id")
            self.flow_logs = VcnFlowLogs(
                name=self.name,
                compartment_id=self.compartment_id,
                vcn=self,
                retention_duration=self._flow_logs_retention,
                stack_name=self.stack_name,
            )

        self.register_outputs({
            "public_subnet_id": self.public_subnet.id if self.public_subnet is not None else None,
            "private_subnet_id": self.private_subnet.id if self.private_subnet is not None else None,
            "secure_subnet_id": self.secure_subnet.id if self.secure_subnet is not None else None,
            "management_subnet_id": self.management_subnet.id if self.management_subnet is not None else None,
            "cidr_block": self.cidr_block,
        })


class VcnRef(AbstractNetworkRef):
    """Read-only reference to a VCN managed by another Pulumi stack.

    Lets you deploy CloudSpells services (OKE, Compute, ScalableWorkload) into a
    VCN that was created by a separate Pulumi stack, without recreating or
    modifying any network resources.

    `add_security_list_rules` and `finalize_network` are **no-ops** for
    `VcnRef`.  Any security rules required by the services you deploy here
    must already exist in the source VCN stack.

    The source stack must export the following keys (all exported by the
    `examples/vcn` stack out of the box):

    - `vcn_id`
    - `cidr_block`
    - `public_subnet_id`
    - `private_subnet_id`
    - `secure_subnet_id`
    - `public_subnet_cidr`
    - `private_subnet_cidr`
    - `secure_subnet_cidr`
    - `public_security_list_id`
    - `private_security_list_id`
    - `secure_security_list_id`
    - `management_subnet_id`
    - `management_subnet_cidr`
    - `management_security_list_id`

    Attributes:
        id: `pulumi.Output[str]` OCID of the referenced VCN.
        cidr_block: `pulumi.Output[str]` CIDR of the referenced VCN.
        public_subnet: Stub whose `.id` is the public subnet OCID.
        private_subnet: Stub whose `.id` is the private subnet OCID.
        public_security_list: Stub whose `.id` is the public security list
            OCID, or `None` if not exported by the source stack.
        private_security_list: Stub whose `.id` is the private security list
            OCID, or `None` if not exported by the source stack.
        secure_subnet: Stub whose `.id` is the secure subnet OCID.
        secure_security_list: Stub whose `.id` is the secure security list
            OCID, or `None` if not exported by the source stack.
        management_subnet: Stub whose `.id` is the management subnet OCID,
            or `None` if not exported by the source stack.
        management_security_list: Stub whose `.id` is the management
            security list OCID, or `None` if not exported by the source stack.
        drg_id: `pulumi.Output[str]` OCID of the Dynamic Routing Gateway
            attached to the referenced VCN, or `None` if not exported.

    Example:
        ```python
        vcn = VcnRef.from_stack_reference("acme/networking/prod")
        cluster = OkeCluster(name="app", vcn=vcn, compartment_id=comp_id, ...)
        ```
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
    drg_id: pulumi.Output[str] | None

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
        drg_id: pulumi.Input[str] | None = None,
    ) -> None:
        """Wrap existing VCN resource IDs in a CloudSpells-compatible interface.

        Args:
            vcn_id: OCID of the existing VCN.
            public_subnet_id: OCID of the existing public subnet.
            private_subnet_id: OCID of the existing private subnet.
            public_subnet_cidr: IPv4 CIDR of the public subnet
                (e.g. `"10.0.48.0/21"` for a default `10.0.0.0/18` VCN).
                Used by spells when building security rules — must match
                the actual subnet CIDR.
            private_subnet_cidr: IPv4 CIDR of the private subnet
                (e.g. `"10.0.0.0/19"` for a default `10.0.0.0/18` VCN).
            cidr_block: IPv4 CIDR of the VCN itself (e.g. `"10.0.0.0/18"`).
                Exported as `cidr_block` by every CloudSpells VCN stack.
                Required — omitting it raises `ValueError`.
            public_security_list_id: OCID of the public security list.
                Required when using `OkeCluster.get_public_security_list_ids`.
            private_security_list_id: OCID of the private security list.
            secure_subnet_id: OCID of the existing secure subnet, if present.
            secure_subnet_cidr: IPv4 CIDR of the secure subnet
                (e.g. `"10.0.32.0/20"` for a default `10.0.0.0/18` VCN).
                Required when `secure_subnet_id` is provided.
            secure_security_list_id: OCID of the secure security list.
            management_subnet_id: OCID of the existing management subnet,
                if present.
            management_subnet_cidr: IPv4 CIDR of the management subnet
                (e.g. `"10.0.56.0/21"` for a default `10.0.0.0/18` VCN).
                Required when `management_subnet_id` is provided.
            management_security_list_id: OCID of the management security list.
            drg_id: OCID of the Dynamic Routing Gateway attached to the
                referenced VCN, if one exists.  Informational only — used
                by dependent stacks to attach VPN connections or FastConnect
                virtual circuits.

        Raises:
            ValueError: If `cidr_block` is `None`.  Every CloudSpells VCN
                stack exports `cidr_block`; pass that value here.
        """
        self.id = pulumi.Output.from_input(vcn_id)
        if cidr_block is None:
            raise ValueError(
                "cidr_block is required for VcnRef. "
                "Pass the VCN's IPv4 CIDR (e.g. '10.0.0.0/18'). "
                "It is exported as 'cidr_block' by every CloudSpells VCN stack."
            )
        self.cidr_block = pulumi.Output.from_input(cidr_block)
        self.public_subnet = _SubnetRef(public_subnet_id)
        self.private_subnet = _SubnetRef(private_subnet_id)
        self._public_subnet_cidr: pulumi.Input[str] = public_subnet_cidr
        self._private_subnet_cidr: pulumi.Input[str] = private_subnet_cidr
        self.public_security_list = _SecurityListRef(public_security_list_id) if public_security_list_id else None
        self.private_security_list = _SecurityListRef(private_security_list_id) if private_security_list_id else None
        self.secure_subnet = _SubnetRef(secure_subnet_id) if secure_subnet_id else None
        self._secure_subnet_cidr: pulumi.Input[str] = secure_subnet_cidr or ""
        self.secure_security_list = _SecurityListRef(secure_security_list_id) if secure_security_list_id else None
        self.management_subnet = _SubnetRef(management_subnet_id) if management_subnet_id else None
        self._management_subnet_cidr: pulumi.Input[str] = management_subnet_cidr or ""
        self.management_security_list = (
            _SecurityListRef(management_security_list_id) if management_security_list_id else None
        )
        self.drg_id = pulumi.Output.from_input(drg_id) if drg_id else None

    @classmethod
    def from_stack_reference(cls, stack_name: str) -> VcnRef:
        """Create a `VcnRef` from outputs published by another Pulumi stack.

        Args:
            stack_name: Pulumi stack reference string.

                - Pulumi Cloud: `"<organization>/<project>/<stack>"`
                - Local backend: `"<project>/<stack>"`

        Returns:
            A `VcnRef` populated from the referenced stack's outputs.

        Example:
            ```python
            vcn = VcnRef.from_stack_reference("acme/networking/prod")
            ```
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
            drg_id=ref.get_output("drg_id"),
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
        """Reject any non-empty rule list — security rules must live in the source stack.

        `VcnRef` is a read-only handle to a VCN managed by another CloudSpells
        stack.  Security lists in that stack are already finalised; this stack
        cannot modify them.  Any spell that calls this method (OKE, Compute,
        ScalableWorkload) requires those rules to exist **before** you deploy here.

        When all arguments are `None` or empty the call is silently accepted as a
        no-op (spells call this unconditionally; the no-op keeps spell code
        branch-free).

        **How to fix:** open the source CloudSpells stack, deploy the same spell
        there first so its rules are written to the VCN security lists, then
        re-run this stack.

        Args:
            public_ingress: Rules that cannot be applied (must be `None` or empty).
            public_egress: Rules that cannot be applied (must be `None` or empty).
            private_ingress: Rules that cannot be applied (must be `None` or empty).
            private_egress: Rules that cannot be applied (must be `None` or empty).
            secure_ingress: Rules that cannot be applied (must be `None` or empty).
            secure_egress: Rules that cannot be applied (must be `None` or empty).
            management_ingress: Rules that cannot be applied (must be `None` or empty).
            management_egress: Rules that cannot be applied (must be `None` or empty).

        Raises:
            RuntimeError: When any argument is a non-empty list.
        """
        requested = {
            "public_ingress": public_ingress,
            "public_egress": public_egress,
            "private_ingress": private_ingress,
            "private_egress": private_egress,
            "secure_ingress": secure_ingress,
            "secure_egress": secure_egress,
            "management_ingress": management_ingress,
            "management_egress": management_egress,
        }
        non_empty = [name for name, rules in requested.items() if rules]
        if non_empty:
            raise RuntimeError(
                f"VcnRef: the following security rule sets were requested but cannot be "
                f"applied to an imported CloudSpells VCN: {non_empty}. "
                f"Add these rules to the source CloudSpells stack first, then re-deploy here."
            )

    def get_public_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the public subnet CIDR.

        Returns:
            Public subnet CIDR as a `pulumi.Input[str]`.
        """
        return self._public_subnet_cidr

    def get_private_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the private subnet CIDR.

        Returns:
            Private subnet CIDR as a `pulumi.Input[str]`.
        """
        return self._private_subnet_cidr

    def get_secure_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the secure subnet CIDR.

        Returns:
            Secure subnet CIDR as a `pulumi.Input[str]`, or an empty string
            `""` when `secure_subnet_id` was not provided at construction.
            Check `self.secure_subnet is not None` before using the result
            in security rules.
        """
        return self._secure_subnet_cidr

    def get_management_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the management subnet CIDR.

        Returns:
            Management subnet CIDR as a `pulumi.Input[str]`, or an empty
            string `""` when `management_subnet_id` was not provided at
            construction.  Check `self.management_subnet is not None` before
            using the result in security rules.
        """
        return self._management_subnet_cidr

    def finalize_network(self) -> None:
        """No-op — the referenced VCN network is already finalized."""


__all__ = [
    "SUBNET_MANAGEMENT",
    "SUBNET_PRIVATE",
    "SUBNET_PUBLIC",
    "SUBNET_SECURE",
    "SubnetConfig",
    "SubnetTier",
    "Vcn",
    "VcnRef",
]
