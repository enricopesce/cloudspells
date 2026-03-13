"""Network Security Group (NSG) building block for OCIBlocks.

Provides :class:`Nsg`, a single named Network Security Group with
caller-defined rules.  NSGs are **role-based policies** — one NSG represents
the security policy for a class of resources (e.g. all web servers, all
databases, all load balancers).  The same NSG can be attached to any number
of VMs, and a single VM can hold multiple NSGs.

This is intentionally **not** tied to subnet topology.  Place the
``ComputeInstance`` in whatever subnet tier makes sense; attach the NSG that
matches its *role*.

Typical usage
-------------

.. code-block:: python

    from providers.oci.nsg import (
        Nsg, TCP, ALL, SVC_CIDR,
        HTTP, HTTPS, SSH, POSTGRES,
        tcp_port, icmp_opts,
    )

    # One NSG per service role
    lb_nsg  = Nsg("load-balancer", vcn=vcn, compartment_id=compartment_id)
    web_nsg = Nsg("web-backend",   vcn=vcn, compartment_id=compartment_id)
    db_nsg  = Nsg("database",      vcn=vcn, compartment_id=compartment_id)

    # Internet edge — use convenience helpers
    lb_nsg.allow_from_internet("https-in", HTTPS)
    lb_nsg.allow_from_internet("http-in",  HTTP)
    lb_nsg.allow_icmp_path_mtu_in("icmp-in")
    lb_nsg.allow_to_nsg("app-out", web_nsg, 8080)
    lb_nsg.allow_icmp_path_mtu_out("icmp-out")

    web_nsg.allow_from_nsg("app-in", lb_nsg, 8080)
    web_nsg.allow_from_nsg("ssh-in", lb_nsg, SSH)
    web_nsg.allow_to_nsg("db-out",   db_nsg, POSTGRES)
    web_nsg.allow_to_services("svc-out")
    web_nsg.allow_to_internet("inet-out")

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

Exports
-------
:class:`Nsg`
``TCP``, ``UDP``, ``ICMP``, ``ALL``, ``SVC_CIDR``
``HTTP``, ``HTTPS``, ``SSH``, ``MYSQL``, ``POSTGRES``, ``ORACLE_DB``, ``REDIS``
:func:`tcp_port`, :func:`tcp_port_range`, :func:`icmp_opts`
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from providers.oci.network import Vcn

# ── Protocol constants ────────────────────────────────────────────────────────

TCP: str = "6"
"""OCI protocol number for TCP."""

UDP: str = "17"
"""OCI protocol number for UDP."""

ICMP: str = "1"
"""OCI protocol number for ICMP."""

ALL: str = "all"
"""OCI wildcard accepting all protocols."""

SVC_CIDR: str = oci.core.get_services().services[0].cidr_block
"""OCI All-Services CIDR block used for Service Gateway egress rules."""

# ── Well-known port constants ─────────────────────────────────────────────────
# Web / access

HTTP: int = 80
"""Standard HTTP port."""

HTTPS: int = 443
"""Standard HTTPS port."""

HTTP_ALT: int = 8080
"""Alternate HTTP port commonly used by application servers."""

HTTPS_ALT: int = 8443
"""Alternate HTTPS port commonly used by application servers."""

SSH: int = 22
"""Standard SSH port."""

RDP: int = 3389
"""Remote Desktop Protocol port."""

# Databases

MYSQL: int = 3306
"""Default MySQL / Aurora port."""

POSTGRES: int = 5432
"""Default PostgreSQL port."""

ORACLE_DB: int = 1521
"""Default Oracle Database listener port."""

MSSQL: int = 1433
"""Default Microsoft SQL Server port."""

CASSANDRA: int = 9042
"""Default Apache Cassandra CQL native transport port."""

MONGODB: int = 27017
"""Default MongoDB port."""

# Caching / messaging

REDIS: int = 6379
"""Default Redis port."""

MEMCACHED: int = 11211
"""Default Memcached port."""

RABBITMQ: int = 5672
"""Default RabbitMQ AMQP port."""

KAFKA: int = 9092
"""Default Apache Kafka broker port."""

# File / directory services

NFS: int = 2049
"""Network File System (NFSv3/v4) port."""

SMB: int = 445
"""SMB / CIFS (Windows file sharing) port."""

LDAP: int = 389
"""Lightweight Directory Access Protocol port."""

LDAPS: int = 636
"""LDAP over TLS port."""

# Search / observability

ELASTICSEARCH: int = 9200
"""Elasticsearch HTTP REST API port."""

# Mail

SMTP: int = 25
"""SMTP relay port."""

SMTPS: int = 587
"""SMTP submission (STARTTLS) port."""

# DNS

DNS: int = 53
"""DNS query port (TCP for zone transfers; UDP for queries)."""

# ── Rule-options helpers ──────────────────────────────────────────────────────

def tcp_port(port: int) -> oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs:
    """Return TCP options restricting traffic to a single destination port.

    Args:
        port: Destination TCP port number (1–65535).

    Returns:
        ``NetworkSecurityGroupSecurityRuleTcpOptionsArgs`` with a
        single-port destination range.

    Example::

        nsg.add_rule("https-in", ..., tcp_options=tcp_port(443))
    """
    return oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsDestinationPortRangeArgs(
            min=port,
            max=port,
        )
    )


def tcp_port_range(
    min_port: int, max_port: int
) -> oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs:
    """Return TCP options restricting traffic to a destination port range.

    Args:
        min_port: Lowest destination port (inclusive).
        max_port: Highest destination port (inclusive).

    Returns:
        ``NetworkSecurityGroupSecurityRuleTcpOptionsArgs`` with the
        specified destination port range.

    Example::

        nsg.add_rule("ephemeral-out", ..., tcp_options=tcp_port_range(1024, 65535))
    """
    return oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsDestinationPortRangeArgs(
            min=min_port,
            max=max_port,
        )
    )


def icmp_opts(
    icmp_type: int, icmp_code: int
) -> oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs:
    """Return ICMP options for a specific type/code pair.

    Args:
        icmp_type: ICMP type number (e.g. ``3`` for Destination Unreachable).
        icmp_code: ICMP code number (e.g. ``4`` for Fragmentation Needed).

    Returns:
        ``NetworkSecurityGroupSecurityRuleIcmpOptionsArgs``.

    Example::

        nsg.add_rule("icmp-mtu", ..., protocol=ICMP, icmp_options=icmp_opts(3, 4))
    """
    return oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs(
        type=icmp_type,
        code=icmp_code,
    )


# ── Nsg ───────────────────────────────────────────────────────────────────────

class Nsg(BaseResource):
    """A single named Network Security Group with caller-defined rules.

    Represents the security policy for one **service role** (e.g. all web
    servers, all databases, all load balancers).  Multiple VMs of the same
    role share the same ``Nsg``; a VM with multiple roles receives multiple
    ``Nsg`` IDs via ``nsg_ids``.

    OCI enforces implicit deny-all for NSGs with no rules — every allowed
    traffic flow must be stated explicitly with :meth:`add_rule`.

    Attributes:
        nsg: The underlying ``oci.core.NetworkSecurityGroup`` resource.
        id: ``pulumi.Output[str]`` OCID of this NSG.  Pass this to
            :class:`~providers.oci.compute.ComputeInstance` via ``nsg_ids``
            or reference it in another NSG's rule as
            ``source`` / ``destination``.

    Example::

        from providers.oci.nsg import Nsg, TCP, ALL, SVC_CIDR, tcp_port

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
    """

    nsg: oci.core.NetworkSecurityGroup
    id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        vcn: Vcn,
        compartment_id: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a single empty NSG for a service role.

        Args:
            name: Role name for this NSG (e.g. ``"load-balancer"``,
                ``"web-backend"``, ``"database"``).  Used to derive the
                Pulumi resource name and OCI display name.
            vcn: The :class:`~providers.oci.network.Vcn` that hosts this NSG.
            compartment_id: OCID of the OCI compartment to deploy into.
            stack_name: Pulumi stack name.  Defaults to
                ``pulumi.get_stack()`` when ``None``.
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__(
            "custom:network:Nsg",
            name,
            compartment_id,
            stack_name,
            opts,
        )

        resource_name = self.create_resource_name("nsg")
        self.nsg = oci.core.NetworkSecurityGroup(
            resource_name,
            compartment_id=self.compartment_id,
            vcn_id=vcn.vcn.id,
            display_name=resource_name,
            freeform_tags=self.create_freeform_tags(resource_name, "nsg"),
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.id = self.nsg.id

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

        The Pulumi resource name is ``{stack}-{nsg-name}-nsg-rule-{label}``.
        *label* must be unique within this NSG.

        Args:
            label: Short unique label for this rule within the NSG
                (e.g. ``"https-in"``, ``"db-out"``).
            direction: ``"INGRESS"`` or ``"EGRESS"``.
            protocol: OCI protocol string — use module constants :data:`TCP`,
                :data:`UDP`, :data:`ICMP`, or :data:`ALL`.
            source: Source CIDR string or NSG OCID.  Required for ingress.
            source_type: ``"CIDR_BLOCK"``, ``"NETWORK_SECURITY_GROUP"``,
                or ``"SERVICE_CIDR_BLOCK"``.
            destination: Destination CIDR or NSG OCID.  Required for egress.
            destination_type: ``"CIDR_BLOCK"``, ``"NETWORK_SECURITY_GROUP"``,
                or ``"SERVICE_CIDR_BLOCK"``.
            tcp_options: TCP port restriction — build with :func:`tcp_port`
                or :func:`tcp_port_range`.
            icmp_options: ICMP type/code restriction — build with
                :func:`icmp_opts`.
            description: Human-readable description shown in the OCI Console.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            web_nsg.add_rule(
                "app-in",
                direction="INGRESS", protocol=TCP,
                source=lb_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=tcp_port(8080),
                description="HTTP traffic from load-balancer NSG",
            )
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

    def allow_from_internet(
        self,
        label: str,
        port: int,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an INGRESS TCP rule allowing traffic from the public internet.

        Shorthand for an INGRESS rule with ``source="0.0.0.0/0"`` and
        ``source_type="CIDR_BLOCK"``.  Use this for edge-facing ports on
        load balancers or public-subnet hosts.

        Args:
            label: Unique label for this rule within the NSG.
            port: Destination TCP port (e.g. ``HTTPS``, ``HTTP``, ``SSH``).
            description: Optional human-readable description.  Defaults to
                ``"TCP {port} from internet"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            lb_nsg.allow_from_internet("https-in", HTTPS)
            lb_nsg.allow_from_internet("http-in",  HTTP)
            lb_nsg.allow_from_internet("ssh-in",   SSH)
        """
        return self.add_rule(
            label,
            direction="INGRESS",
            protocol=TCP,
            source="0.0.0.0/0",
            source_type="CIDR_BLOCK",
            tcp_options=tcp_port(port),
            description=description or f"TCP {port} from internet",
        )

    def allow_from_cidr(
        self,
        label: str,
        port: int,
        cidr: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an INGRESS TCP rule allowing traffic from a specific CIDR.

        Use this for restricted sources such as an office IP, VPN range, or
        peered VCN CIDR.  For unrestricted internet access use
        :meth:`allow_from_internet` instead.

        Args:
            label: Unique label for this rule within the NSG.
            port: Destination TCP port.
            cidr: Source CIDR block (e.g. ``"203.0.113.0/24"`` or
                ``"10.1.0.0/16"``).
            description: Optional human-readable description.  Defaults to
                ``"TCP {port} from {cidr}"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            lb_nsg.allow_from_cidr("ssh-office", SSH,     "203.0.113.42/32")
            lb_nsg.allow_from_cidr("ssh-vpn",    SSH,     "10.8.0.0/16")
            db_nsg.allow_from_cidr("db-peered",  POSTGRES, "172.16.0.0/12")
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

        Uses ``source_type="NETWORK_SECURITY_GROUP"`` so only VMs carrying
        *source* can send traffic — no CIDRs required.

        Args:
            label: Unique label for this rule within the NSG.
            source: The peer :class:`Nsg` whose members are the traffic source.
            port: Destination TCP port.
            description: Optional human-readable description.  Defaults to
                ``"TCP {port} from NSG"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            web_nsg.allow_from_nsg("app-in", lb_nsg,  app_port)
            web_nsg.allow_from_nsg("ssh-in", lb_nsg,  SSH)
            db_nsg.allow_from_nsg("db-in",  web_nsg, POSTGRES)
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

        Uses ``destination_type="NETWORK_SECURITY_GROUP"`` so only VMs
        carrying *destination* can receive the traffic.

        Args:
            label: Unique label for this rule within the NSG.
            destination: The peer :class:`Nsg` whose members are the target.
            port: Destination TCP port.
            description: Optional human-readable description.  Defaults to
                ``"TCP {port} to NSG"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            lb_nsg.allow_to_nsg("app-out",     web_nsg, app_port)
            web_nsg.allow_to_nsg("db-out",     db_nsg,  POSTGRES)
            web_nsg.allow_to_nsg("ssh-db-out", db_nsg,  SSH)
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

        Uses ``destination_type="SERVICE_CIDR_BLOCK"`` and ``protocol=ALL``.
        Required for any instance that must reach OCI Object Storage, the
        container registry, or other Oracle-managed services.

        Args:
            label: Unique label for this rule within the NSG.
            description: Optional human-readable description.  Defaults to
                ``"All traffic to Oracle Services"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            web_nsg.allow_to_services("svc-out")
            db_nsg.allow_to_services("svc-out")
        """
        return self.add_rule(
            label,
            direction="EGRESS",
            protocol=ALL,
            destination=SVC_CIDR,
            destination_type="SERVICE_CIDR_BLOCK",
            description=description or "All traffic to Oracle Services",
        )

    def allow_to_internet(
        self,
        label: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an EGRESS rule allowing all traffic to the public internet.

        Routes via the VCN's NAT Gateway for private-subnet instances.  Only
        applicable to instances in subnets with a NAT Gateway route.

        Args:
            label: Unique label for this rule within the NSG.
            description: Optional human-readable description.  Defaults to
                ``"All traffic to internet"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            web_nsg.allow_to_internet("inet-out")
        """
        return self.add_rule(
            label,
            direction="EGRESS",
            protocol=ALL,
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            description=description or "All traffic to internet",
        )

    def allow_icmp_path_mtu_in(
        self,
        label: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an INGRESS ICMP type 3 code 4 (Path MTU Discovery) rule.

        OCI recommends this rule on every NSG to allow proper MTU negotiation
        for TCP connections.

        Args:
            label: Unique label for this rule within the NSG.
            description: Optional human-readable description.  Defaults to
                ``"ICMP Path-MTU inbound"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            lb_nsg.allow_icmp_path_mtu_in("icmp-in")
        """
        return self.add_rule(
            label,
            direction="INGRESS",
            protocol=ICMP,
            source="0.0.0.0/0",
            source_type="CIDR_BLOCK",
            icmp_options=icmp_opts(3, 4),
            description=description or "ICMP Path-MTU inbound",
        )

    def allow_icmp_path_mtu_out(
        self,
        label: str,
        description: str = "",
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Add an EGRESS ICMP type 3 code 4 (Path MTU Discovery) rule.

        OCI recommends this rule on every NSG to allow proper MTU negotiation
        for TCP connections.

        Args:
            label: Unique label for this rule within the NSG.
            description: Optional human-readable description.  Defaults to
                ``"ICMP Path-MTU outbound"``.

        Returns:
            The ``oci.core.NetworkSecurityGroupSecurityRule`` resource.

        Example::

            lb_nsg.allow_icmp_path_mtu_out("icmp-out")
        """
        return self.add_rule(
            label,
            direction="EGRESS",
            protocol=ICMP,
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            icmp_options=icmp_opts(3, 4),
            description=description or "ICMP Path-MTU outbound",
        )


__all__ = [
    "Nsg",
    "TCP", "UDP", "ICMP", "ALL", "SVC_CIDR",
    # Web / access
    "HTTP", "HTTPS", "HTTP_ALT", "HTTPS_ALT", "SSH", "RDP",
    # Databases
    "MYSQL", "POSTGRES", "ORACLE_DB", "MSSQL", "CASSANDRA", "MONGODB",
    # Caching / messaging
    "REDIS", "MEMCACHED", "RABBITMQ", "KAFKA",
    # File / directory
    "NFS", "SMB", "LDAP", "LDAPS",
    # Search / observability
    "ELASTICSEARCH",
    # Mail
    "SMTP", "SMTPS",
    # DNS
    "DNS",
    "tcp_port", "tcp_port_range", "icmp_opts",
]
