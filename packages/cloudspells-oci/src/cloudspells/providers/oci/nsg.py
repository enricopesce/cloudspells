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
from cloudspells.providers.oci.nsg import (
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
lb   = ComputeInstance("lb",    ..., nsg=lb_nsg)
web1 = ComputeInstance("web-1", ..., nsg=web_nsg)
web2 = ComputeInstance("web-2", ..., nsg=web_nsg)  # same NSG
db1  = ComputeInstance("db-1",  ..., nsg=db_nsg)
db2  = ComputeInstance("db-2",  ..., nsg=db_nsg)   # same NSG
```

Exports:

Protocol and CIDR constants:
    `TCP`, `UDP`, `ICMP`, `ALL`, `SVC_CIDR`, `INTERNET`

Rule-option builders:
    `tcp_port`, `tcp_port_range`, `udp_port`, `udp_port_range`, `icmp_opts`

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
from cloudspells.core.abstractions.tiers import SUBNET_PUBLIC
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

from ._naming import ordinal_suffix
from ._oci_utils import get_all_services
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
the real `pulumi.Output[str]` CIDR at construction time via the regional All Services lookup.

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


def udp_port(port: int) -> oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs:
    """Return UDP options restricting traffic to a single destination port.

    Args:
        port: Destination UDP port number (1–65535).

    Returns:
        `NetworkSecurityGroupSecurityRuleUdpOptionsArgs` with a single-port
        destination range.

    Example:
        ```python
        # DNS over UDP
        nsg.add_rule("dns-out", direction="EGRESS", protocol=UDP,
                     destination=resolver_cidr, destination_type="CIDR_BLOCK",
                     udp_options=udp_port(DNS))
        ```
    """
    return oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsDestinationPortRangeArgs(
            min=port,
            max=port,
        )
    )


def udp_port_range(min_port: int, max_port: int) -> oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs:
    """Return UDP options restricting traffic to a destination port range.

    Args:
        min_port: Lowest destination port (inclusive).
        max_port: Highest destination port (inclusive).

    Returns:
        `NetworkSecurityGroupSecurityRuleUdpOptionsArgs` with the specified
        destination port range.

    Example:
        ```python
        nsg.add_rule("rtp-out", ..., udp_options=udp_port_range(16384, 32767))
        ```
    """
    return oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsDestinationPortRangeArgs(
            min=min_port,
            max=max_port,
        )
    )


def icmp_opts(
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
        `Nsg.add_rule` or `Nsg.allow_icmp_from_cidr`.

    Example:
        ```python
        nsg.add_rule("icmp-unreachable", direction="INGRESS", protocol=ICMP,
                     source="0.0.0.0/0", source_type="CIDR_BLOCK",
                     icmp_options=icmp_opts(3, 4))
        ```
    """
    return oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs(
        type=icmp_type,
        code=code,
    )


# ── Security-list rule builders (private helpers used by role/serves) ─────────
# These translate the role and relationship declarations into OCI SecurityList
# args so that nsg.py does not need to import from network.py's translation
# layer.  They mirror the private _translate_* functions inside Vcn.add_security_rules
# but live here to keep the NSG module self-contained.


# ── Nsg ───────────────────────────────────────────────────────────────────────


class Nsg(BaseResource):
    """A single named Network Security Group with caller-defined rules.

    Represents the security policy for one **service role** (e.g. all web
    servers, all databases, all load balancers).  Multiple VMs of the same
    role share the same `Nsg`; a VM with multiple roles receives multiple
    `Nsg` IDs via `nsg_ids`.

    OCI allows traffic if a rule in an applicable NSG or subnet security
    list permits it. An empty NSG grants no additional permission.

    Attributes:
        nsg: The underlying `oci.core.NetworkSecurityGroup` resource.
        id: `pulumi.Output[str]` OCID of this NSG.  Pass this to
            `ComputeInstance` via `nsg_ids` or reference it in another
            NSG's rule as `source` / `destination`.
        role: The `Role` that governs this NSG's ambient rules and subnet
            tier placement, or `None` when the NSG was created without a
            role and all rules are managed manually.  Read by `serves` to
            determine whether to add the SSH management channel.

    Example:
        ```python
        from cloudspells.providers.oci.nsg import Nsg, TCP, ALL, SVC_CIDR, tcp_port

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
        lb   = ComputeInstance("lb",    ..., nsg=lb_nsg)
        web1 = ComputeInstance("web-1", ..., nsg=web_nsg)
        web2 = ComputeInstance("web-2", ..., nsg=web_nsg)
        db1  = ComputeInstance("db-1",  ..., nsg=db_nsg)
        db2  = ComputeInstance("db-2",  ..., nsg=db_nsg)
        ```
    """

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

        When `role` is supplied, its default rules apply to this group's
        members.

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
                NSG. Its default rules are generated automatically.
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

        self.role = role
        self._rule_labels: set[str] = set()
        self._served_ports: dict[Nsg, set[int]] = {}
        self._next_rule_index = 0

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

    # ------------------------------------------------------------------
    # Role and relationship methods
    # ------------------------------------------------------------------

    def _apply_role_ambient_rules(self, role: Role, ports: list[int]) -> None:
        """Create the default NSG rules for `role`.

        Called once from `__init__` when `role=` is supplied.  The caller
        must not invoke this method directly.

        NSG rules created per role:

        - **INTERNET_EDGE** (`subnet_tier == SUBNET_PUBLIC`): TCP ingress from
          `0.0.0.0/0` on each declared port.
        - **APP_SERVER / CACHE** (`egress_internet=True`): all-protocol egress
          to `0.0.0.0/0` and to Oracle Services.
        - **DATABASE / MANAGEMENT** (`egress_services=True` only): all-protocol
          egress to Oracle Services only (no internet).

        Args:
            role: The `Role` to apply.
            ports: TCP ports for `INTERNET_EDGE` internet ingress.
        """
        tier = role.subnet_tier
        is_internet_edge = tier == SUBNET_PUBLIC

        if is_internet_edge:
            for port in dict.fromkeys(ports):
                self.allow_from_cidr(f"internet-in-{port}", port, INTERNET)

        if role.egress_services:
            self.allow_to_services("svc-out")
        if role.egress_internet:
            self.allow_to_cidr("inet-out", INTERNET)

    def serves(
        self,
        target: Nsg,
        port: int,
        *,
        with_ssh: bool = True,
    ) -> None:
        """Declare a directed traffic relationship from this NSG to `target`.

        A single call generates the full set of bilateral rules needed for the
        relationship. Repeated calls reuse the ports already configured for
        the target:

        - Egress from this NSG to `target` on `port`.
        - Ingress on `target` from this NSG on `port`.
        - (When `with_ssh=True` and `target` has `role.accept_management_ssh`)
          Egress from this NSG to `target` on port 22.
        - (Same condition) Ingress on `target` from this NSG on port 22.

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

        served_ports = self._served_ports.setdefault(target, set())
        if port not in served_ports:
            self.allow_to_nsg(f"out-{tgt}-{port}", target, port)
            target.allow_from_nsg(f"in-{src}-{port}", self, port)
            served_ports.add(port)

        needs_ssh = with_ssh and (target.role is None or target.role.accept_management_ssh)
        if needs_ssh and SSH not in served_ports:
            self.allow_to_nsg(f"out-{tgt}-ssh", target, SSH)
            target.allow_from_nsg(f"in-{src}-ssh", self, SSH)
            served_ports.add(SSH)

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
        udp_options: oci.core.NetworkSecurityGroupSecurityRuleUdpOptionsArgs | None = None,
        icmp_options: oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs | None = None,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add a single stateful security rule to this NSG.

        The Pulumi resource name uses an internal ordinal suffix such as
        `{stack}-{nsg-name}-nsg-rule-1`. `label` remains the human-readable
        unique key for this rule within the NSG.

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
            udp_options: UDP port restriction — build with `udp_port`
                or `udp_port_range`.
            icmp_options: ICMP type/code restriction — build with `icmp_opts`.
            description: Human-readable description shown in the OCI Console.

        Returns:
            The `oci.core.NetworkSecurityGroupSecurityRule` resource.

        Raises:
            ValueError: If `label` duplicates an existing rule label on this
                NSG.

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

            # DNS over UDP (requires udp_options — previously impossible)
            dns_nsg.add_rule(
                "dns-out",
                direction="EGRESS", protocol=UDP,
                destination=resolver_ip, destination_type="CIDR_BLOCK",
                udp_options=udp_port(DNS),
            )
            ```
        """
        if label in self._rule_labels:
            raise ValueError(f"Nsg rule label must be unique within this NSG; duplicate label: {label!r}")
        self._rule_labels.add(label)
        rule_index = self._next_rule_index
        self._next_rule_index += 1

        legacy_rule_name = f"{self.stack_name}-{self.name}-nsg-rule-{label}"
        resource_name = self.create_resource_name(ordinal_suffix("nsg-rule", rule_index))
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
            description=description or label,
            opts=pulumi.ResourceOptions(
                parent=self,
                aliases=[pulumi.Alias(name=legacy_rule_name)],
            ),
        )

    # ------------------------------------------------------------------
    # Convenience helpers — encode idiomatic OCI patterns
    # ------------------------------------------------------------------

    def allow_from_cidr(
        self,
        label: str,
        port: int,
        cidr: pulumi.Input[str],
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
        source_label = cidr if isinstance(cidr, str) else "CIDR"
        return self.add_rule(
            label,
            direction="INGRESS",
            protocol=TCP,
            source=cidr,
            source_type="CIDR_BLOCK",
            tcp_options=tcp_port(port),
            description=description or f"TCP {port} from {source_label}",
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
            destination=get_all_services(self).cidr_block,
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
        return self.add_rule(
            label,
            direction="INGRESS",
            protocol=ICMP,
            source=cidr,
            source_type="CIDR_BLOCK",
            icmp_options=icmp_opts(icmp_type, code),
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
    "tcp_port",
    "tcp_port_range",
    "udp_port",
    "udp_port_range",
    "icmp_opts",
    # Role system (re-exported for convenience — canonical source is providers.oci.roles)
    "Role",
]
