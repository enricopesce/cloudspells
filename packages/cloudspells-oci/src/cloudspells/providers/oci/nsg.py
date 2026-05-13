"""Network Security Group (NSG) spell for CloudSpells.

Provides `Nsg`, a single named Network Security Group with opinionated
role-based rules.  NSGs are **role-based policies** — one NSG represents the
security policy and subnet tier for a class of resources (e.g. all web
servers, all databases, all load balancers).  The same NSG can be reused by
any number of VMs.

Typical usage:

```python
from cloudspells.providers.oci.nsg import Nsg, HTTP, HTTPS, SSH, POSTGRES
from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE

# One role-bearing NSG per service role
lb_nsg  = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS],
              vcn=vcn, compartment_id=compartment_id)
web_nsg = Nsg("web-backend",   role=APP_SERVER,
              vcn=vcn, compartment_id=compartment_id)
db_nsg  = Nsg("database",      role=DATABASE,
              vcn=vcn, compartment_id=compartment_id)

# Relationships add bilateral NSG rules and cross-subnet security-list rules.
lb_nsg.serves(web_nsg, port=8080)
web_nsg.serves(db_nsg, port=POSTGRES)

# ComputeInstance derives VCN and subnet placement from its NSG.
lb   = ComputeInstance("lb",    ..., nsg=lb_nsg)
web1 = ComputeInstance("web-1", ..., nsg=web_nsg)
web2 = ComputeInstance("web-2", ..., nsg=web_nsg)  # same NSG
db1  = ComputeInstance("db-1",  ..., nsg=db_nsg)
db2  = ComputeInstance("db-2",  ..., nsg=db_nsg)   # same NSG
```

Exports:

Protocol and CIDR constants:
    `TCP`, `UDP`, `ICMP`, `ALL`, `SVC_CIDR`, `INTERNET`

Well-known port integers (plain `int`, re-exported from `cloudspells.core.ports`):
    Web: `HTTP`, `HTTPS`, `HTTP_ALT`, `HTTPS_ALT`
    Access: `SSH`, `RDP`
    Databases: `MYSQL`, `POSTGRES`, `ORACLE_DB`, `MSSQL`, `CASSANDRA`, `MONGODB`
    Caching/messaging: `REDIS`, `MEMCACHED`, `RABBITMQ`, `KAFKA`
    File/directory: `NFS`, `SMB`, `LDAP`, `LDAPS`
    Search/observability: `ELASTICSEARCH`
    Mail: `SMTP`, `SMTPS`
    DNS: `DNS`

NSG class and role system:
    `Nsg`, `Role`
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.network import EgressRule, IngressRule, SecurityRules
from cloudspells.core.abstractions.tiers import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
)
from cloudspells.core.base import BaseResource
from cloudspells.core.ports import (
    CASSANDRA,
    DNS,
    ELASTICSEARCH,
    HTTP,
    HTTP_ALT,
    HTTPS,
    HTTPS_ALT,
    KAFKA,
    LDAP,
    LDAPS,
    MEMCACHED,
    MONGODB,
    MSSQL,
    MYSQL,
    NFS,
    ORACLE_DB,
    POSTGRES,
    RABBITMQ,
    RDP,
    REDIS,
    SMB,
    SMTP,
    SMTPS,
    SSH,
)

from ._oci_utils import get_svc_cidr as _get_svc_cidr
from .network import Vcn, VcnRef
from .roles import INTERNET_EDGE, Role

# ── Protocol constants ────────────────────────────────────────────────────────

TCP: str = "6"
"""OCI protocol number for TCP."""

UDP: str = "17"
"""OCI protocol number for UDP."""

ICMP: str = "1"
"""OCI protocol number for ICMP."""

ALL: str = "all"
"""OCI wildcard accepting all protocols."""

SVC_CIDR: str = "oci-services-cidr"
"""Sentinel string identifying the OCI All-Services CIDR target.

**This is NOT a valid CIDR string.** Do not pass it directly to OCI resource
arguments — it will produce an invalid rule that passes Pulumi planning but
fails at apply time.  Use `Nsg.allow_to_services()` instead, which resolves
the real `pulumi.Output[str]` CIDR at construction time via `_get_svc_cidr()`.

This constant is retained in `__all__` only for import-compatibility
with existing code that references it in docstrings or type guards.
"""


INTERNET: str = "0.0.0.0/0"
"""CIDR representing the public internet.  Use with `Nsg.allow_from_cidr`
and `Nsg.allow_to_cidr` for edge-facing rules."""

# ── Well-known port constants (re-exported from cloudspells.core.ports) ───────────────────
# These are plain integers with no OCI dependency.  The canonical source is
# `core.ports`; they are re-exported here so that existing imports from
# `providers.oci.nsg` continue to work unchanged.

# ── Rule-options helpers ──────────────────────────────────────────────────────


def _tcp_port(port: int) -> oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs:
    """Return TCP options restricting traffic to a single destination port.

    Args:
        port: Destination TCP port number (1–65535).

    Returns:
        `NetworkSecurityGroupSecurityRuleTcpOptionsArgs` with a single-port
        destination range.

    This helper is provider-internal plumbing for the opinionated NSG
    rule helpers.
    """
    return oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsDestinationPortRangeArgs(
            min=port,
            max=port,
        )
    )


def _udp_port(port: int) -> oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs:
    """Return UDP options restricting traffic to a single destination port.

    Args:
        port: Destination UDP port number (1–65535).

    Returns:
        `NetworkSecurityGroupSecurityRuleUdpOptionsArgs` with a single-port
        destination range.

    This helper is provider-internal plumbing for the opinionated NSG
    rule helpers.
    """
    return oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsDestinationPortRangeArgs(
            min=port,
            max=port,
        )
    )


def _icmp_opts(
    icmp_type: int,
    code: int = -1,
) -> oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs:
    """Return ICMP options for a specific type and optional code.

    Args:
        icmp_type: ICMP type number (e.g. `3` for Destination Unreachable).
        code: ICMP code number.  Use `-1` (default) to match all codes for
            the given type.

    Returns:
        `NetworkSecurityGroupSecurityRuleIcmpOptionsArgs` ready for use in
        `Nsg.allow_icmp_from_cidr`.
    """
    return oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs(
        type=icmp_type,
        code=code,
    )


# ── Nsg ───────────────────────────────────────────────────────────────────────


class Nsg(BaseResource):
    """A single named Network Security Group with caller-defined rules.

    Represents the security policy and subnet tier for one **service role**
    (e.g. all web servers, all databases, all load balancers).  Multiple VMs
    of the same role share the same `Nsg`; `ComputeInstance` requires one
    role-bearing `Nsg` via `nsg=`.

    OCI enforces implicit deny-all for NSGs with no rules — every allowed
    traffic flow must be stated explicitly with the opinionated rule helpers.

    Attributes:
        nsg: The underlying `oci.core.NetworkSecurityGroup` resource.
        id: `pulumi.Output[str]` OCID of this NSG.  `ComputeInstance` reads
            this from the required `nsg=` object, and other NSG rules can
            reference it as `source` / `destination`.
        role: The `Role` that governs this NSG's ambient rules and subnet
            tier placement, or `None` when the NSG was created without a
            role and all rules are managed manually.  Read by `serves` to
            determine the SSH management channel and cross-subnet security
            list rules.

    Example:
        ```python
        from cloudspells.providers.oci.nsg import Nsg, HTTP, HTTPS, POSTGRES
        from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE

        lb_nsg  = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS],
                      vcn=vcn, compartment_id=compartment_id)
        web_nsg = Nsg("web-backend",   role=APP_SERVER,
                      vcn=vcn, compartment_id=compartment_id)
        db_nsg  = Nsg("database",      role=DATABASE,
                      vcn=vcn, compartment_id=compartment_id)

        lb_nsg.serves(web_nsg, port=8080)
        web_nsg.serves(db_nsg, port=POSTGRES)

        # Attach — ComputeInstance derives VCN and subnet from the role-bearing NSG
        lb   = ComputeInstance("lb",    ..., nsg=lb_nsg)
        web1 = ComputeInstance("web-1", ..., nsg=web_nsg)
        web2 = ComputeInstance("web-2", ..., nsg=web_nsg)
        db1  = ComputeInstance("db-1",  ..., nsg=db_nsg)
        db2  = ComputeInstance("db-2",  ..., nsg=db_nsg)
        ```
    """

    _vcn: Vcn | VcnRef
    id: pulumi.Output[str]
    nsg: oci.core.NetworkSecurityGroup
    role: Role | None

    def __init__(
        self,
        name: str,
        vcn: Vcn | VcnRef,
        compartment_id: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
        role: Role | None = None,
        ports: list[int] | None = None,
    ) -> None:
        """Create a single NSG for a service role.

        When `role` is supplied the NSG self-configures: ambient rules are
        added automatically based on the posture declared in the role, and the
        corresponding VCN security list rules are registered so that
        `Vcn.finalize_network` can materialise them without any manual
        `Vcn.add_security_rules` call.

        When `role` is `None` the NSG is created empty and all rules must be
        added explicitly via the convenience helpers.

        Args:
            name: Role name for this NSG (e.g. `"load-balancer"`,
                `"web-backend"`, `"database"`).  Used to derive the
                Pulumi resource name and OCI display name.
            vcn: The `Vcn` (or `VcnRef`) that hosts this NSG.
            compartment_id: OCID of the OCI compartment to deploy into.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            opts: Pulumi resource options forwarded to the component.
            role: Optional `Role` that encodes the security posture of this
                NSG.  When set, ambient rules are generated automatically and
                subnet security list rules are registered with the VCN.
            ports: TCP port numbers that `INTERNET_EDGE` resources accept from
                the internet (e.g. `[HTTP, HTTPS, SSH]`).  Required when
                `role=INTERNET_EDGE`; ignored for other roles.

        Raises:
            ValueError: If `role` is `INTERNET_EDGE` and `ports` is `None` or
                empty.  An internet-facing NSG with no declared ports would
                silently accept no inbound traffic.

        Example:
            ```python
            from cloudspells.providers.oci import INTERNET_EDGE, APP_SERVER, DATABASE
            from cloudspells.providers.oci.nsg import Nsg, HTTP, HTTPS, SSH

            lb_nsg  = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS, SSH],
                          vcn=vcn, compartment_id=compartment_id)
            web_nsg = Nsg("web-backend",   role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)
            db_nsg  = Nsg("database",      role=DATABASE,   vcn=vcn, compartment_id=compartment_id)

            lb_nsg.serves(web_nsg, port=8080)
            web_nsg.serves(db_nsg, port=5432)
            ```
        """
        super().__init__(
            "custom:network:Nsg",
            name,
            compartment_id,
            stack_name,
            opts,
        )

        self._vcn = vcn
        self.role = role

        if role is INTERNET_EDGE and not ports:
            raise ValueError(
                f"Nsg '{name}': role=INTERNET_EDGE requires at least one port in `ports=` "
                "(e.g. ports=[HTTP, HTTPS]).  An empty or missing ports list would create "
                "an internet-facing NSG that accepts no inbound traffic."
            )

        resource_name = self.create_resource_name("nsg")
        self.nsg = oci.core.NetworkSecurityGroup(
            resource_name,
            compartment_id=self.compartment_id,
            vcn_id=vcn.id,
            display_name=resource_name,
            freeform_tags=self.create_freeform_tags(resource_name, "nsg"),
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.id = self.nsg.id

        if role is not None:
            self._apply_role_ambient_rules(role, ports or [])

        self.register_outputs({"id": self.id})

    @property
    def vcn(self) -> Vcn | VcnRef:
        """Return the VCN that hosts this NSG.

        Returns:
            The live `Vcn` or imported `VcnRef` supplied when the NSG was
            constructed.
        """
        return self._vcn

    # ------------------------------------------------------------------
    # Role and relationship methods
    # ------------------------------------------------------------------

    def _sl_for_tier(
        self,
        fingerprint: str,
        tier: str,
        ingress: list[IngressRule] | None = None,
        egress: list[EgressRule] | None = None,
    ) -> None:
        """Dispatch a uniquely-fingerprinted security list rule to the correct tier.

        Wraps `Vcn.add_unique_security_rules` with an explicit
        `if`/`elif` tier dispatch so Pyright can verify that ingress args go
        to ingress parameters and egress args to egress parameters (dynamic
        `**kwargs` unpacking defeats the type checker).

        This is an internal helper; external callers should use `serves` or
        `_apply_role_ambient_rules`.

        Args:
            fingerprint: Unique key; subsequent calls with the same fingerprint
                are silently ignored by the VCN accumulator.
            tier: Subnet tier constant (`"public"`, `"private"`, `"secure"`,
                or `"management"`).
            ingress: Optional ingress rule list for the tier's security list.
            egress: Optional egress rule list for the tier's security list.
        """
        if not isinstance(self._vcn, Vcn):
            return
        vcn = self._vcn
        if tier == SUBNET_PUBLIC:
            vcn.add_unique_security_rules(
                fingerprint,
                SecurityRules(public_ingress=ingress or [], public_egress=egress or []),
            )
        elif tier == SUBNET_PRIVATE:
            vcn.add_unique_security_rules(
                fingerprint,
                SecurityRules(private_ingress=ingress or [], private_egress=egress or []),
            )
        elif tier == SUBNET_SECURE:
            vcn.add_unique_security_rules(
                fingerprint,
                SecurityRules(secure_ingress=ingress or [], secure_egress=egress or []),
            )
        elif tier == SUBNET_MANAGEMENT:
            vcn.add_unique_security_rules(
                fingerprint,
                SecurityRules(management_ingress=ingress or [], management_egress=egress or []),
            )

    def _cidr_for_tier(self, tier: str) -> pulumi.Input[str]:
        """Return the subnet CIDR for `tier` from the backing VCN.

        Args:
            tier: Subnet tier constant (`"public"`, `"private"`, `"secure"`,
                or `"management"`).

        Returns:
            `pulumi.Input[str]` CIDR for the requested tier.

        Raises:
            ValueError: If `tier` is not one of the four known constants.
        """
        if tier == SUBNET_PUBLIC:
            return self._vcn.get_public_subnet_cidr()
        elif tier == SUBNET_PRIVATE:
            return self._vcn.get_private_subnet_cidr()
        elif tier == SUBNET_SECURE:
            return self._vcn.get_secure_subnet_cidr()
        elif tier == SUBNET_MANAGEMENT:
            return self._vcn.get_management_subnet_cidr()
        else:
            raise ValueError(f"Unknown subnet tier: {tier!r}")

    def _apply_role_ambient_rules(self, role: Role, ports: list[int]) -> None:
        """Create ambient NSG rules and register security list rules for `role`.

        Called once from `__init__` when `role=` is supplied.  The caller
        must not invoke this method directly.

        NSG rules created per role:

        - **INTERNET_EDGE** (`subnet_tier == SUBNET_PUBLIC`): TCP ingress from
          `0.0.0.0/0` on each declared port.
        - **APP_SERVER / CACHE** (`egress_internet=True`): all-protocol egress
          to `0.0.0.0/0` and to Oracle Services.
        - **DATABASE / MANAGEMENT** (`egress_services=True` only): all-protocol
          egress to Oracle Services only (no internet).

        When the backing network is a live `Vcn` (not a `VcnRef`), the
        equivalent subnet security list rules are also registered via
        `Vcn.add_unique_security_rules` so that `Vcn.finalize_network`
        can emit them without any manual `Vcn.add_security_rules` call by the
        user.

        Args:
            role: The `Role` to apply.
            ports: TCP ports for `INTERNET_EDGE` internet ingress.
        """
        tier = role.subnet_tier
        is_internet_edge = tier == SUBNET_PUBLIC

        # -- NSG rules --------------------------------------------------------
        if is_internet_edge:
            for port in ports:
                self.allow_from_cidr(f"internet-in-{port}", port, INTERNET)

        if role.egress_services:
            self.allow_to_services("svc-out")
        if role.egress_internet:
            self.allow_to_cidr("inet-out", INTERNET)

        # -- Security list rules (only for live Vcn, not VcnRef) --------------
        if not isinstance(self._vcn, Vcn):
            return

        if is_internet_edge:
            for port in ports:
                self._vcn.add_unique_security_rules(
                    f"public-ingress-tcp-{port}",
                    SecurityRules(
                        public_ingress=[
                            IngressRule(
                                protocol="tcp",
                                source=INTERNET,
                                port_min=port,
                                port_max=port,
                                description=f"TCP {port} from internet",
                            )
                        ],
                    ),
                )

        if role.egress_services:
            self._sl_for_tier(
                f"{tier}-egress-all-services",
                tier,
                egress=[
                    EgressRule(
                        protocol="all",
                        destination="cloud-services",
                        description="All traffic to Oracle Services",
                    )
                ],
            )
        if role.egress_internet:
            self._sl_for_tier(
                f"{tier}-egress-all-internet",
                tier,
                egress=[
                    EgressRule(
                        protocol="all",
                        destination=INTERNET,
                        description="All outbound traffic via NAT Gateway",
                    )
                ],
            )

    def serves(
        self,
        target: Nsg,
        port: int,
        *,
        with_ssh: bool = True,
    ) -> None:
        """Declare a directed traffic relationship from this NSG to `target`.

        A single call generates the full set of bilateral rules needed for the
        relationship:

        - Egress from this NSG to `target` on `port`.
        - Ingress on `target` from this NSG on `port`.
        - (When `with_ssh=True` and `target` has `role.accept_management_ssh`)
          Egress from this NSG to `target` on port 22.
        - (Same condition) Ingress on `target` from this NSG on port 22.

        When both NSGs carry `Role` instances and the backing network is a
        live `Vcn`, the corresponding subnet security list cross-subnet rules
        are also registered automatically.  Cross-subnet rules are only emitted
        when the two roles occupy different tiers (same-tier rules are handled
        entirely by the NSGs themselves).

        Args:
            target: The downstream `Nsg` that receives the traffic.
            port: TCP port number for the application-level connection.
            with_ssh: When `True` (default) an SSH (port 22) management
                channel is added alongside the application port — egress from
                this NSG to `target`, ingress on `target` from this NSG.  Set
                `False` to suppress the SSH channel (e.g. for read-only data
                paths or when SSH access is provided by a separate Bastion
                service).

        Raises:
            ValueError: If either NSG's role contains an unrecognised subnet
                tier string (should never occur with the predefined role
                constants).

        Example:
            ```python
            lb_nsg.serves(web_nsg, port=8080)          # app + SSH management
            web_nsg.serves(db_nsg, port=5432)          # app + SSH management
            lb_nsg.serves(web_nsg, port=443, with_ssh=False)  # HTTPS only
            ```
        """
        src = self.name
        tgt = target.name

        # Application port — both directions
        self.allow_to_nsg(f"out-{tgt}-{port}", target, port)
        target.allow_from_nsg(f"in-{src}-{port}", self, port)

        # SSH management channel
        needs_ssh = with_ssh and (target.role is None or target.role.accept_management_ssh)
        if needs_ssh:
            self.allow_to_nsg(f"out-{tgt}-ssh", target, SSH)
            target.allow_from_nsg(f"in-{src}-ssh", self, SSH)

        # Security list cross-subnet rules (only when both roles are known
        # and the network is a live Vcn — VcnRef manages its own rules)
        if self.role is None or target.role is None:
            return
        if not isinstance(self._vcn, Vcn):
            return
        src_tier = self.role.subnet_tier
        tgt_tier = target.role.subnet_tier
        if src_tier == tgt_tier:
            return  # same subnet — NSG rules are sufficient

        src_cidr = self._cidr_for_tier(src_tier)
        tgt_cidr = self._cidr_for_tier(tgt_tier)

        self._sl_for_tier(
            f"{src_tier}-egress-tcp-{port}-to-{tgt_tier}",
            src_tier,
            egress=[
                EgressRule(
                    protocol="tcp",
                    destination=tgt_cidr,
                    port_min=port,
                    port_max=port,
                    description=f"TCP {port} to {tgt_tier} tier",
                )
            ],
        )
        self._sl_for_tier(
            f"{tgt_tier}-ingress-tcp-{port}-from-{src_tier}",
            tgt_tier,
            ingress=[
                IngressRule(
                    protocol="tcp",
                    source=src_cidr,
                    port_min=port,
                    port_max=port,
                    description=f"TCP {port} from {src_tier} tier",
                )
            ],
        )

        if needs_ssh:
            self._sl_for_tier(
                f"{src_tier}-egress-tcp-22-to-{tgt_tier}",
                src_tier,
                egress=[
                    EgressRule(
                        protocol="tcp",
                        destination=tgt_cidr,
                        port_min=SSH,
                        port_max=SSH,
                        description=f"SSH to {tgt_tier} tier",
                    )
                ],
            )
            self._sl_for_tier(
                f"{tgt_tier}-ingress-tcp-22-from-{src_tier}",
                tgt_tier,
                ingress=[
                    IngressRule(
                        protocol="tcp",
                        source=src_cidr,
                        port_min=SSH,
                        port_max=SSH,
                        description=f"SSH from {src_tier} tier",
                    )
                ],
            )

    def _add_rule(
        self,
        label: str,
        *,
        direction: str,
        protocol: str,
        source: pulumi.Input[str] | None = None,
        source_type: str | None = None,
        destination: pulumi.Input[str] | None = None,
        destination_type: str | None = None,
        tcp_options: oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs | None = None,
        udp_options: oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs | None = None,
        icmp_options: oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs | None = None,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Create a single stateful security rule for this NSG.

        The Pulumi resource name is `{stack}-{nsg-name}-nsg-rule-{label}`.
        `label` must be unique within this NSG.

        Args:
            label: Short unique label for this rule within the NSG
                (e.g. `"https-in"`, `"db-out"`).
            direction: `"INGRESS"` or `"EGRESS"`.
            protocol: OCI protocol string — use module constants `TCP`,
                `UDP`, `ICMP`, or `ALL`.
            source: Source CIDR string or NSG OCID.  Required for ingress.
            source_type: `"CIDR_BLOCK"`, `"NETWORK_SECURITY_GROUP"`,
                or `"SERVICE_CIDR_BLOCK"`.
            destination: Destination CIDR or NSG OCID.  Required for egress.
            destination_type: `"CIDR_BLOCK"`, `"NETWORK_SECURITY_GROUP"`,
                or `"SERVICE_CIDR_BLOCK"`.
            tcp_options: TCP port restriction built internally.
            udp_options: UDP port restriction built internally.
            icmp_options: ICMP type/code restriction built internally.
            description: Human-readable description shown in the OCI Console.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        This is provider-internal plumbing. Public callers should use
        `allow_from_cidr`, `allow_from_nsg`, `allow_to_nsg`,
        `allow_to_services`, `allow_to_cidr`, or `allow_icmp_from_cidr`.
        """
        resource_name = self.create_resource_name(f"nsg-rule-{label}")
        return oci.core.NetworkSecurityGroupSecurityRule(
            resource_name,
            network_security_group_id=self.nsg.id,
            direction=direction,
            protocol=protocol,
            source=source,
            source_type=source_type,
            destination=destination,
            destination_type=destination_type,
            tcp_options=tcp_options,
            udp_options=udp_options,
            icmp_options=icmp_options,
            stateless=False,
            description=description or resource_name,
            opts=pulumi.ResourceOptions(parent=self),
        )

    # ------------------------------------------------------------------
    # Convenience helpers — encode idiomatic OCI patterns
    # ------------------------------------------------------------------

    def allow_from_cidr(
        self,
        label: str,
        port: int,
        cidr: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an INGRESS TCP rule allowing traffic from a CIDR block.

        Use `INTERNET` (`"0.0.0.0/0"`) for unrestricted internet access, or
        pass a specific CIDR for restricted sources such as an office IP, VPN
        range, or peered VCN CIDR.

        Args:
            label: Unique label for this rule within the NSG.
            port: Destination TCP port.
            cidr: Source CIDR block.  Use `INTERNET` for `"0.0.0.0/0"`.
            description: Optional human-readable description.  Defaults to
                `"TCP {port} from {cidr}"`.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            lb_nsg.allow_from_cidr("https-in",   HTTPS,    INTERNET)
            lb_nsg.allow_from_cidr("ssh-office",  SSH,      "203.0.113.42/32")
            db_nsg.allow_from_cidr("db-peered",   POSTGRES, "172.16.0.0/12")
            ```
        """
        return self._add_rule(
            label,
            direction="INGRESS",
            protocol=TCP,
            source=cidr,
            source_type="CIDR_BLOCK",
            tcp_options=_tcp_port(port),
            description=description or f"TCP {port} from {cidr}",
        )

    def allow_udp_from_cidr(
        self,
        label: str,
        port: int,
        cidr: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an INGRESS UDP rule allowing traffic from a CIDR block.

        Args:
            label: Unique label for this rule within the NSG.
            port: Destination UDP port.
            cidr: Source CIDR block. Use `INTERNET` for `"0.0.0.0/0"`.
            description: Optional human-readable description. Defaults to
                `"UDP {port} from {cidr}"`.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            resolver_nsg.allow_udp_from_cidr("dns-in", DNS, "10.0.0.0/16")
            ```
        """
        return self._add_rule(
            label,
            direction="INGRESS",
            protocol=UDP,
            source=cidr,
            source_type="CIDR_BLOCK",
            udp_options=_udp_port(port),
            description=description or f"UDP {port} from {cidr}",
        )

    def allow_from_nsg(
        self,
        label: str,
        source: Nsg,
        port: int,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an INGRESS TCP rule allowing traffic from another NSG.

        Uses `source_type="NETWORK_SECURITY_GROUP"` so only VMs carrying
        `source` can send traffic — no CIDRs required.

        Args:
            label: Unique label for this rule within the NSG.
            source: The peer `Nsg` whose members are the traffic source.
            port: Destination TCP port.
            description: Optional human-readable description.  Defaults to
                `"TCP {port} from NSG"`.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            web_nsg.allow_from_nsg("app-in", lb_nsg,  app_port)
            web_nsg.allow_from_nsg("ssh-in", lb_nsg,  SSH)
            db_nsg.allow_from_nsg("db-in",  web_nsg, POSTGRES)
            ```
        """
        return self._add_rule(
            label,
            direction="INGRESS",
            protocol=TCP,
            source=source.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=_tcp_port(port),
            description=description or f"TCP {port} from NSG",
        )

    def allow_to_nsg(
        self,
        label: str,
        destination: Nsg,
        port: int,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an EGRESS TCP rule allowing traffic to another NSG.

        Uses `destination_type="NETWORK_SECURITY_GROUP"` so only VMs
        carrying `destination` can receive the traffic.

        Args:
            label: Unique label for this rule within the NSG.
            destination: The peer `Nsg` whose members are the target.
            port: Destination TCP port.
            description: Optional human-readable description.  Defaults to
                `"TCP {port} to NSG"`.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            lb_nsg.allow_to_nsg("app-out",     web_nsg, app_port)
            web_nsg.allow_to_nsg("db-out",     db_nsg,  POSTGRES)
            web_nsg.allow_to_nsg("ssh-db-out", db_nsg,  SSH)
            ```
        """
        return self._add_rule(
            label,
            direction="EGRESS",
            protocol=TCP,
            destination=destination.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=_tcp_port(port),
            description=description or f"TCP {port} to NSG",
        )

    def allow_to_services(
        self,
        label: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an EGRESS rule allowing all traffic to Oracle Services (Service GW).

        Uses `destination_type="SERVICE_CIDR_BLOCK"` and `protocol=ALL`.
        Required for any instance that must reach OCI Object Storage, the
        container registry, or other Oracle-managed services.

        Args:
            label: Unique label for this rule within the NSG.
            description: Optional human-readable description.  Defaults to
                `"All traffic to Oracle Services"`.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            web_nsg.allow_to_services("svc-out")
            db_nsg.allow_to_services("svc-out")
            ```
        """
        return self._add_rule(
            label,
            direction="EGRESS",
            protocol=ALL,
            destination=_get_svc_cidr(),
            destination_type="SERVICE_CIDR_BLOCK",
            description=description or "All traffic to Oracle Services",
        )

    def allow_to_cidr(
        self,
        label: str,
        cidr: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an EGRESS all-protocol rule allowing traffic to a CIDR block.

        Use `INTERNET` (`"0.0.0.0/0"`) for unrestricted outbound via the NAT
        Gateway, or pass a specific CIDR for targeted egress.

        Args:
            label: Unique label for this rule within the NSG.
            cidr: Destination CIDR block.  Use `INTERNET` for `"0.0.0.0/0"`.
            description: Optional human-readable description.  Defaults to
                `"All traffic to {cidr}"`.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            web_nsg.allow_to_cidr("inet-out",    INTERNET)
            web_nsg.allow_to_cidr("peered-out",  "10.1.0.0/16")
            ```
        """
        return self._add_rule(
            label,
            direction="EGRESS",
            protocol=ALL,
            destination=cidr,
            destination_type="CIDR_BLOCK",
            description=description or f"All traffic to {cidr}",
        )

    def allow_udp_to_cidr(
        self,
        label: str,
        port: int,
        cidr: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an EGRESS UDP rule allowing traffic to a CIDR block.

        Args:
            label: Unique label for this rule within the NSG.
            port: Destination UDP port.
            cidr: Destination CIDR block. Use `INTERNET` for `"0.0.0.0/0"`.
            description: Optional human-readable description. Defaults to
                `"UDP {port} to {cidr}"`.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            app_nsg.allow_udp_to_cidr("dns-out", DNS, "10.0.0.2/32")
            ```
        """
        return self._add_rule(
            label,
            direction="EGRESS",
            protocol=UDP,
            destination=cidr,
            destination_type="CIDR_BLOCK",
            udp_options=_udp_port(port),
            description=description or f"UDP {port} to {cidr}",
        )

    def allow_icmp_from_cidr(
        self,
        label: str,
        cidr: str,
        icmp_type: int,
        code: int = -1,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an INGRESS ICMP rule allowing a specific type (and optional code) from a CIDR.

        Args:
            label: Unique label for this rule within the NSG.
            cidr: Source CIDR block.  Use `INTERNET` for `"0.0.0.0/0"`.
            icmp_type: ICMP type number (e.g. `3` for Destination Unreachable).
            code: ICMP code number.  Use `-1` (default) to match all codes.
            description: Optional human-readable description.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            nsg.allow_icmp_from_cidr("icmp-unreachable", INTERNET, icmp_type=3, code=4)
            ```
        """
        return self._add_rule(
            label,
            direction="INGRESS",
            protocol=ICMP,
            source=cidr,
            source_type="CIDR_BLOCK",
            icmp_options=_icmp_opts(icmp_type, code),
            description=description or f"ICMP type {icmp_type} code {code} from {cidr}",
        )


__all__ = [
    "Nsg",
    "TCP",
    "UDP",
    "ICMP",
    "ALL",
    "SVC_CIDR",
    "INTERNET",
    # Web / access
    "HTTP",
    "HTTPS",
    "HTTP_ALT",
    "HTTPS_ALT",
    "SSH",
    "RDP",
    # Databases
    "MYSQL",
    "POSTGRES",
    "ORACLE_DB",
    "MSSQL",
    "CASSANDRA",
    "MONGODB",
    # Caching / messaging
    "REDIS",
    "MEMCACHED",
    "RABBITMQ",
    "KAFKA",
    # File / directory
    "NFS",
    "SMB",
    "LDAP",
    "LDAPS",
    # Search / observability
    "ELASTICSEARCH",
    # Mail
    "SMTP",
    "SMTPS",
    # DNS
    "DNS",
    # Role system (re-exported for convenience — canonical source is providers.oci.roles)
    "Role",
]
