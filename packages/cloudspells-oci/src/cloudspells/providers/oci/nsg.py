"""Network Security Group (NSG) spell for CloudSpells.

Provides `Nsg`, a single named Network Security Group with
caller-defined rules.  NSGs are **role-based policies** — one NSG represents
the security policy for a class of resources (e.g. all web servers, all
databases, all load balancers).  The same NSG can be attached to any number
of VMs, and a single VM can hold multiple NSGs.

This is intentionally **not** tied to subnet topology.  Place the
`ComputeInstance` in whatever subnet tier makes sense; attach the NSG that
matches its role.

Typical usage:

```python
from .nsg import (
    Nsg, TCP, ALL, SVC_CIDR, INTERNET,
    HTTP, HTTPS, SSH, POSTGRES,
    tcp_port,
)

# One NSG per service role
lb_nsg  = Nsg("load-balancer", vcn=vcn, compartment_id=compartment_id)
web_nsg = Nsg("web-backend",   vcn=vcn, compartment_id=compartment_id)
db_nsg  = Nsg("database",      vcn=vcn, compartment_id=compartment_id)

# Internet edge — INTERNET constant replaces hard-coded "0.0.0.0/0"
lb_nsg.allow_from_cidr("https-in", HTTPS, INTERNET)
lb_nsg.allow_from_cidr("http-in",  HTTP,  INTERNET)
lb_nsg.allow_to_nsg("app-out", web_nsg, 8080)

web_nsg.allow_from_nsg("app-in", lb_nsg, 8080)
web_nsg.allow_from_nsg("ssh-in", lb_nsg, SSH)
web_nsg.allow_to_nsg("db-out",   db_nsg, POSTGRES)
web_nsg.allow_to_services("svc-out")
web_nsg.allow_to_cidr("inet-out", INTERNET)

db_nsg.allow_from_nsg("db-in",  web_nsg, POSTGRES)
db_nsg.allow_from_nsg("ssh-in", web_nsg, SSH)
db_nsg.allow_to_services("svc-out")

# Attach the right NSG to each VM — same NSG shared across identical roles
lb   = ComputeInstance("lb",    ..., nsg_ids=[lb_nsg.id])
web1 = ComputeInstance("web-1", ..., nsg_ids=[web_nsg.id])
web2 = ComputeInstance("web-2", ..., nsg_ids=[web_nsg.id])  # same NSG
db1  = ComputeInstance("db-1",  ..., nsg_ids=[db_nsg.id])
db2  = ComputeInstance("db-2",  ..., nsg_ids=[db_nsg.id])   # same NSG

# A VM with two roles gets two NSGs
combo = ComputeInstance("app", ..., nsg_ids=[web_nsg.id, db_nsg.id])
```

Exports:
    `Nsg`, `TCP`, `UDP`, `ALL`, `SVC_CIDR`,
    `HTTP`, `HTTPS`, `SSH`, `MYSQL`, `POSTGRES`, `ORACLE_DB`, `REDIS`,
    `tcp_port`, `tcp_port_range`
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
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

from .network import SUBNET_MANAGEMENT, SUBNET_PRIVATE, SUBNET_PUBLIC, SUBNET_SECURE, Vcn, VcnRef
from .roles import Role

# ── Protocol constants ────────────────────────────────────────────────────────

TCP: str = "6"
"""OCI protocol number for TCP."""

UDP: str = "17"
"""OCI protocol number for UDP."""

ALL: str = "all"
"""OCI wildcard accepting all protocols."""

SVC_CIDR: pulumi.Output[str] = oci.core.get_services_output().services.apply(
    lambda svcs: next(s.cidr_block for s in svcs if s.cidr_block.startswith("all-"))
)
"""OCI All-Services CIDR block used for Service Gateway egress rules.

Resolved lazily at plan time via `oci.core.get_services_output()`.
Type is `pulumi.Output[str]`; passes directly to any `pulumi.Input[str]` field.
"""

INTERNET: str = "0.0.0.0/0"
"""CIDR representing the public internet.  Use with `Nsg.allow_from_cidr`
and `Nsg.allow_to_cidr` for edge-facing rules."""

# ── Well-known port constants (re-exported from cloudspells.core.ports) ───────────────────
# These are plain integers with no OCI dependency.  The canonical source is
# `core.ports`; they are re-exported here so that existing imports from
# `providers.oci.nsg` continue to work unchanged.

__all_ports__ = [
    "HTTP",
    "HTTPS",
    "HTTP_ALT",
    "HTTPS_ALT",
    "SSH",
    "RDP",
    "MYSQL",
    "POSTGRES",
    "ORACLE_DB",
    "MSSQL",
    "CASSANDRA",
    "MONGODB",
    "REDIS",
    "MEMCACHED",
    "RABBITMQ",
    "KAFKA",
    "NFS",
    "SMB",
    "LDAP",
    "LDAPS",
    "ELASTICSEARCH",
    "SMTP",
    "SMTPS",
    "DNS",
]

# ── Rule-options helpers ──────────────────────────────────────────────────────


def tcp_port(port: int) -> oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs:
    """Return TCP options restricting traffic to a single destination port.

    Args:
        port: Destination TCP port number (1–65535).

    Returns:
        `NetworkSecurityGroupSecurityRuleTcpOptionsArgs` with a single-port
        destination range.

    Example:
        ```python
        nsg.add_rule("https-in", ..., tcp_options=tcp_port(443))
        ```
    """
    return oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsDestinationPortRangeArgs(
            min=port,
            max=port,
        )
    )


def tcp_port_range(min_port: int, max_port: int) -> oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs:
    """Return TCP options restricting traffic to a destination port range.

    Args:
        min_port: Lowest destination port (inclusive).
        max_port: Highest destination port (inclusive).

    Returns:
        `NetworkSecurityGroupSecurityRuleTcpOptionsArgs` with the specified
        destination port range.

    Example:
        ```python
        nsg.add_rule("ephemeral-out", ..., tcp_options=tcp_port_range(1024, 65535))
        ```
    """
    return oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsDestinationPortRangeArgs(
            min=min_port,
            max=max_port,
        )
    )


# ── Security-list rule builders (private helpers used by role/serves) ─────────
# These translate the role and relationship declarations into OCI SecurityList
# args so that nsg.py does not need to import from network.py's translation
# layer.  They mirror the private _translate_* functions inside Vcn.add_security_rules
# but live here to keep the NSG module self-contained.


def _sl_ingress_tcp(
    port: int,
    source: pulumi.Input[str],
    description: str = "",
) -> oci.core.SecurityListIngressSecurityRuleArgs:
    """Build a TCP ingress `SecurityListIngressSecurityRuleArgs` for `port` from `source`."""
    return oci.core.SecurityListIngressSecurityRuleArgs(
        protocol="6",
        source=source,
        source_type="CIDR_BLOCK",
        tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(min=port, max=port),
        description=description or f"TCP {port} ingress",
    )


def _sl_egress_tcp(
    port: int,
    destination: pulumi.Input[str],
    description: str = "",
) -> oci.core.SecurityListEgressSecurityRuleArgs:
    """Build a TCP egress `SecurityListEgressSecurityRuleArgs` for `port` to `destination`."""
    return oci.core.SecurityListEgressSecurityRuleArgs(
        protocol="6",
        destination=destination,
        destination_type="CIDR_BLOCK",
        tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(min=port, max=port),
        description=description or f"TCP {port} egress",
    )


def _sl_egress_all_services() -> oci.core.SecurityListEgressSecurityRuleArgs:
    """Build an all-protocol egress rule to the OCI Service Gateway CIDR."""
    return oci.core.SecurityListEgressSecurityRuleArgs(
        protocol="all",
        destination=SVC_CIDR,
        destination_type="SERVICE_CIDR_BLOCK",
        description="All traffic to Oracle Services",
    )


def _sl_egress_all_internet() -> oci.core.SecurityListEgressSecurityRuleArgs:
    """Build an all-protocol egress rule to the internet (0.0.0.0/0)."""
    return oci.core.SecurityListEgressSecurityRuleArgs(
        protocol="all",
        destination="0.0.0.0/0",
        destination_type="CIDR_BLOCK",
        description="All outbound traffic via NAT Gateway",
    )


# ── Nsg ───────────────────────────────────────────────────────────────────────


class Nsg(BaseResource):
    """A single named Network Security Group with caller-defined rules.

    Represents the security policy for one **service role** (e.g. all web
    servers, all databases, all load balancers).  Multiple VMs of the same
    role share the same `Nsg`; a VM with multiple roles receives multiple
    `Nsg` IDs via `nsg_ids`.

    OCI enforces implicit deny-all for NSGs with no rules — every allowed
    traffic flow must be stated explicitly with `add_rule`.

    Attributes:
        nsg: The underlying `oci.core.NetworkSecurityGroup` resource.
        id: `pulumi.Output[str]` OCID of this NSG.  Pass this to
            `ComputeInstance` via `nsg_ids` or reference it in another
            NSG's rule as `source` / `destination`.

    Example:
        ```python
        from .nsg import Nsg, TCP, ALL, SVC_CIDR, tcp_port

        lb_nsg  = Nsg("load-balancer", vcn=vcn, compartment_id=compartment_id)
        web_nsg = Nsg("web-backend",   vcn=vcn, compartment_id=compartment_id)
        db_nsg  = Nsg("database",      vcn=vcn, compartment_id=compartment_id)

        # internet → load balancer
        lb_nsg.add_rule("https-in",
                        direction="INGRESS", protocol=TCP,
                        source="0.0.0.0/0", source_type="CIDR_BLOCK",
                        tcp_options=tcp_port(443))

        # load balancer → web backends  (NSG-to-NSG, no CIDRs)
        lb_nsg.add_rule("app-out",
                        direction="EGRESS", protocol=TCP,
                        destination=web_nsg.id,
                        destination_type="NETWORK_SECURITY_GROUP",
                        tcp_options=tcp_port(8080))
        web_nsg.add_rule("app-in",
                         direction="INGRESS", protocol=TCP,
                         source=lb_nsg.id,
                         source_type="NETWORK_SECURITY_GROUP",
                         tcp_options=tcp_port(8080))

        # web backends → databases  (NSG-to-NSG, no CIDRs)
        web_nsg.add_rule("db-out",
                         direction="EGRESS", protocol=TCP,
                         destination=db_nsg.id,
                         destination_type="NETWORK_SECURITY_GROUP",
                         tcp_options=tcp_port(5432))
        db_nsg.add_rule("db-in",
                        direction="INGRESS", protocol=TCP,
                        source=web_nsg.id,
                        source_type="NETWORK_SECURITY_GROUP",
                        tcp_options=tcp_port(5432))

        # Attach — same NSG shared by all VMs of the same role
        lb   = ComputeInstance("lb",    ..., nsg_ids=[lb_nsg.id])
        web1 = ComputeInstance("web-1", ..., nsg_ids=[web_nsg.id])
        web2 = ComputeInstance("web-2", ..., nsg_ids=[web_nsg.id])
        db1  = ComputeInstance("db-1",  ..., nsg_ids=[db_nsg.id])
        db2  = ComputeInstance("db-2",  ..., nsg_ids=[db_nsg.id])
        ```
    """

    nsg: oci.core.NetworkSecurityGroup
    id: pulumi.Output[str]

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
        added explicitly via `add_rule` and the convenience helpers.

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

        Example:
            ```python
            from .roles import INTERNET_EDGE, APP_SERVER, DATABASE
            from .nsg import Nsg, HTTP, HTTPS, SSH

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

    # ------------------------------------------------------------------
    # Role and relationship methods
    # ------------------------------------------------------------------

    def _sl_for_tier(
        self,
        fingerprint: str,
        tier: str,
        ingress: list[oci.core.SecurityListIngressSecurityRuleArgs] | None = None,
        egress: list[oci.core.SecurityListEgressSecurityRuleArgs] | None = None,
    ) -> None:
        """Dispatch a uniquely-fingerprinted security list rule to the correct tier.

        Wraps `Vcn._add_unique_security_list_rules` with an explicit
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
            vcn._add_unique_security_list_rules(fingerprint, public_ingress=ingress, public_egress=egress)
        elif tier == SUBNET_PRIVATE:
            vcn._add_unique_security_list_rules(fingerprint, private_ingress=ingress, private_egress=egress)
        elif tier == SUBNET_SECURE:
            vcn._add_unique_security_list_rules(fingerprint, secure_ingress=ingress, secure_egress=egress)
        elif tier == SUBNET_MANAGEMENT:
            vcn._add_unique_security_list_rules(fingerprint, management_ingress=ingress, management_egress=egress)

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
        `Vcn._add_unique_security_list_rules` so that `Vcn.finalize_network`
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
                self._vcn._add_unique_security_list_rules(
                    f"public-ingress-tcp-{port}",
                    public_ingress=[_sl_ingress_tcp(port, "0.0.0.0/0", f"TCP {port} from internet")],
                )

        if role.egress_services:
            self._sl_for_tier(f"{tier}-egress-all-services", tier, egress=[_sl_egress_all_services()])
        if role.egress_internet:
            self._sl_for_tier(f"{tier}-egress-all-internet", tier, egress=[_sl_egress_all_internet()])

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

        src_cidr = getattr(self._vcn, f"get_{src_tier}_subnet_cidr")()
        tgt_cidr = getattr(self._vcn, f"get_{tgt_tier}_subnet_cidr")()

        self._sl_for_tier(
            f"{src_tier}-egress-tcp-{port}-to-{tgt_tier}",
            src_tier,
            egress=[_sl_egress_tcp(port, tgt_cidr, f"TCP {port} to {tgt_tier} tier")],
        )
        self._sl_for_tier(
            f"{tgt_tier}-ingress-tcp-{port}-from-{src_tier}",
            tgt_tier,
            ingress=[_sl_ingress_tcp(port, src_cidr, f"TCP {port} from {src_tier} tier")],
        )

        if needs_ssh:
            self._sl_for_tier(
                f"{src_tier}-egress-tcp-22-to-{tgt_tier}",
                src_tier,
                egress=[_sl_egress_tcp(SSH, tgt_cidr, f"SSH to {tgt_tier} tier")],
            )
            self._sl_for_tier(
                f"{tgt_tier}-ingress-tcp-22-from-{src_tier}",
                tgt_tier,
                ingress=[_sl_ingress_tcp(SSH, src_cidr, f"SSH from {src_tier} tier")],
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_rule(
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
        icmp_options: oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs | None = None,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add a single stateful security rule to this NSG.

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
            tcp_options: TCP port restriction — build with `tcp_port`
                or `tcp_port_range`.
            icmp_options: ICMP type/code restriction — build with `icmp_opts`.
            description: Human-readable description shown in the OCI Console.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Example:
            ```python
            web_nsg.add_rule(
                "app-in",
                direction="INGRESS", protocol=TCP,
                source=lb_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=tcp_port(8080),
                description="HTTP traffic from load-balancer NSG",
            )
            ```
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
        return self.add_rule(
            label,
            direction="INGRESS",
            protocol=TCP,
            source=cidr,
            source_type="CIDR_BLOCK",
            tcp_options=tcp_port(port),
            description=description or f"TCP {port} from {cidr}",
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
        return self.add_rule(
            label,
            direction="INGRESS",
            protocol=TCP,
            source=source.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(port),
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
        return self.add_rule(
            label,
            direction="EGRESS",
            protocol=TCP,
            destination=destination.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(port),
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
        return self.add_rule(
            label,
            direction="EGRESS",
            protocol=ALL,
            destination=SVC_CIDR,
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
        return self.add_rule(
            label,
            direction="EGRESS",
            protocol=ALL,
            destination=cidr,
            destination_type="CIDR_BLOCK",
            description=description or f"All traffic to {cidr}",
        )


__all__ = [
    "Nsg",
    "TCP",
    "UDP",
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
    "tcp_port",
    "tcp_port_range",
    # Role system (re-exported for convenience — canonical source is providers.oci.roles)
    "Role",
]
