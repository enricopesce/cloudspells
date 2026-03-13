"""Cloud-neutral network abstractions for OCIBlocks multi-cloud support.

Defines the security-rule dataclasses, factory helpers, and network
interfaces that decouple service blocks (Compute, OKE, ScalableWorkload)
from any specific cloud provider.  Each provider translates these
descriptors into its own firewall model (OCI SecurityList, AWS Security
Group, GCP Firewall Rule).

Typical usage
-------------

.. code-block:: python

    from core.abstractions.network import (
        SecurityRules, INTERNET, CLOUD_SERVICES,
        tcp_ingress, icmp_path_mtu_ingress,
        all_egress, icmp_path_mtu_egress,
    )
    from providers.oci.nsg import HTTPS, HTTP, SSH, POSTGRES

    vcn.add_security_rules(SecurityRules(
        public_ingress=[
            tcp_ingress(HTTPS, INTERNET),
            tcp_ingress(HTTP,  INTERNET),
            tcp_ingress(SSH,   INTERNET),
            icmp_path_mtu_ingress(),
        ],
        public_egress=[icmp_path_mtu_egress()],
        private_ingress=[
            tcp_ingress(app_port, vcn.get_public_subnet_cidr()),
            tcp_ingress(SSH,      vcn.get_public_subnet_cidr()),
        ],
        private_egress=[
            all_egress(CLOUD_SERVICES),
            all_egress(INTERNET),
        ],
        secure_ingress=[
            tcp_ingress(POSTGRES, vcn.get_private_subnet_cidr()),
            tcp_ingress(SSH,      vcn.get_private_subnet_cidr()),
        ],
        secure_egress=[all_egress(CLOUD_SERVICES)],
    ))

Exports:
    INTERNET: Symbolic source/destination meaning ``0.0.0.0/0``.
    CLOUD_SERVICES: Symbolic destination meaning cloud-managed service endpoints.
    IngressRule: Cloud-neutral inbound security rule descriptor.
    EgressRule: Cloud-neutral outbound security rule descriptor.
    SecurityRules: Accumulated rules for all four subnet tiers.
    AbstractNetwork: Builder interface for cloud networks.
    AbstractNetworkRef: Read-only reference to a network in another stack.
    tcp_ingress: Build a TCP ingress rule from any source (CIDR, subnet ref, or INTERNET).
    icmp_path_mtu_ingress: Build an ICMP Path-MTU ingress rule.
    tcp_egress: Build a TCP egress rule to any destination.
    all_egress: Build an all-protocol egress rule to any destination.
    icmp_path_mtu_egress: Build an ICMP Path-MTU egress rule.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pulumi


@dataclass
class IngressRule:
    """Cloud-neutral inbound security rule descriptor.

    Provider implementations translate this into their native firewall
    construct.  The ``source`` field supports both literal CIDRs and the
    following symbolic names that each provider resolves internally:

    * ``"internet"``       – ``0.0.0.0/0`` on all providers.
    * ``"cloud-services"`` – OCI Service Gateway CIDR, AWS managed-prefix
      list, or GCP Private Service Access range.

    Attributes:
        protocol: Transport protocol: ``"tcp"``, ``"udp"``, ``"icmp"``,
            or ``"all"``.
        source: Source CIDR block or symbolic name.
        port_min: First TCP/UDP port in the allowed range (inclusive).
            ``None`` means no port restriction.
        port_max: Last TCP/UDP port in the allowed range (inclusive).
            ``None`` means no port restriction.
        description: Human-readable description of the rule's purpose.
        icmp_type: ICMP type code.  Only relevant when
            ``protocol="icmp"``.
        icmp_code: ICMP code.  Only relevant when ``protocol="icmp"``.

    Example::

        # Allow SSH from the public subnet CIDR
        rule = IngressRule(
            protocol="tcp",
            source="10.0.0.0/19",
            port_min=22,
            port_max=22,
            description="SSH from bastion host",
        )

        # Allow ICMP path-MTU discovery from anywhere
        mtu_rule = IngressRule(
            protocol="icmp",
            source="0.0.0.0/0",
            description="ICMP path-MTU discovery",
            icmp_type=3,
            icmp_code=4,
        )
    """

    protocol: str
    source: pulumi.Input[str]
    port_min: int | None = None
    port_max: int | None = None
    description: str = ""
    icmp_type: int | None = None
    icmp_code: int | None = None


@dataclass
class EgressRule:
    """Cloud-neutral outbound security rule descriptor.

    Mirrors :class:`IngressRule` for egress direction.  The ``destination``
    field supports the same symbolic names as :attr:`IngressRule.source`.

    Attributes:
        protocol: Transport protocol: ``"tcp"``, ``"udp"``, ``"icmp"``,
            or ``"all"``.
        destination: Destination CIDR block or symbolic name.
        port_min: First TCP/UDP port in the allowed range (inclusive).
            ``None`` means no port restriction.
        port_max: Last TCP/UDP port in the allowed range (inclusive).
            ``None`` means no port restriction.
        description: Human-readable description of the rule's purpose.
        icmp_type: ICMP type code.  Only relevant when
            ``protocol="icmp"``.
        icmp_code: ICMP code.  Only relevant when ``protocol="icmp"``.

    Example::

        # Allow HTTPS egress to OCI-managed services
        rule = EgressRule(
            protocol="tcp",
            destination="cloud-services",
            port_min=443,
            port_max=443,
            description="HTTPS to OCI services",
        )
    """

    protocol: str
    destination: pulumi.Input[str]
    port_min: int | None = None
    port_max: int | None = None
    description: str = ""
    icmp_type: int | None = None
    icmp_code: int | None = None


@dataclass
class SecurityRules:
    """Accumulated cloud-neutral security rules for all four subnet tiers.

    Service blocks call :meth:`AbstractNetwork.add_security_rules` with a
    populated ``SecurityRules`` instance.  The network implementation
    translates each :class:`IngressRule` / :class:`EgressRule` into
    provider-specific constructs (OCI ``SecurityListIngressSecurityRuleArgs``,
    AWS ``SecurityGroupIngressArgs``, etc.) and accumulates them for batch
    materialisation when :meth:`AbstractNetwork.finalize_network` is called.

    Attributes:
        public_ingress: Ingress rules for the public (load-balancer) tier.
        public_egress: Egress rules for the public tier.
        private_ingress: Ingress rules for the private (app-server) tier.
        private_egress: Egress rules for the private tier.
        secure_ingress: Ingress rules for the secure (database) tier.
        secure_egress: Egress rules for the secure tier.
        management_ingress: Ingress rules for the management tier.
        management_egress: Egress rules for the management tier.

    Example::

        rules = SecurityRules(
            private_ingress=[
                IngressRule(
                    protocol="tcp",
                    source="10.0.0.0/19",
                    port_min=22,
                    port_max=22,
                    description="SSH from public subnet",
                )
            ],
        )
        vcn.add_security_rules(rules)
    """

    public_ingress:     list[IngressRule] = field(default_factory=list)
    public_egress:      list[EgressRule]  = field(default_factory=list)
    private_ingress:    list[IngressRule] = field(default_factory=list)
    private_egress:     list[EgressRule]  = field(default_factory=list)
    secure_ingress:     list[IngressRule] = field(default_factory=list)
    secure_egress:      list[EgressRule]  = field(default_factory=list)
    management_ingress: list[IngressRule] = field(default_factory=list)
    management_egress:  list[EgressRule]  = field(default_factory=list)


# ── Source / destination constants ────────────────────────────────────────────

INTERNET: str = "0.0.0.0/0"
"""CIDR representing the public internet.  Works as source or destination
in :func:`tcp_ingress`, :func:`all_egress`, and :func:`tcp_egress`."""

CLOUD_SERVICES: str = "cloud-services"
"""Symbolic destination resolving to cloud-managed service endpoints.

Resolves to the OCI Service Gateway CIDR (``SERVICE_CIDR_BLOCK``) on OCI,
or the equivalent managed-prefix on other clouds.
"""

# ── Security-rule factory helpers ─────────────────────────────────────────────

def tcp_ingress(
    port: int,
    source: pulumi.Input[str],
    description: str = "",
) -> IngressRule:
    """Build a TCP ingress rule from any source.

    *source* can be a literal CIDR string, a ``pulumi.Input[str]`` subnet
    reference (e.g. ``vcn.get_public_subnet_cidr()``), or the
    :data:`INTERNET` constant for unrestricted internet access.

    Args:
        port: Destination TCP port number.
        source: Source CIDR, subnet reference, or :data:`INTERNET`.
        description: Human-readable description.  Defaults to
            ``"TCP {port} ingress"``.

    Returns:
        :class:`IngressRule` configured for TCP on *port* from *source*.

    Example::

        tcp_ingress(HTTPS, INTERNET)
        tcp_ingress(app_port, vcn.get_public_subnet_cidr())
        tcp_ingress(POSTGRES, "10.0.8.0/21")
    """
    return IngressRule(
        protocol="tcp",
        source=source,
        port_min=port,
        port_max=port,
        description=description or f"TCP {port} ingress",
    )


def icmp_path_mtu_ingress(description: str = "") -> IngressRule:
    """Build an ICMP type 3 code 4 (Path MTU Discovery) ingress rule.

    OCI recommends this on every security list to allow proper MTU
    negotiation for TCP connections.

    Args:
        description: Human-readable description.  Defaults to
            ``"ICMP Path-MTU inbound"``.

    Returns:
        :class:`IngressRule` configured for ICMP 3/4 from the internet.

    Example::

        icmp_path_mtu_ingress()
    """
    return IngressRule(
        protocol="icmp",
        source="internet",
        icmp_type=3,
        icmp_code=4,
        description=description or "ICMP Path-MTU inbound",
    )


def tcp_egress(
    port: int,
    destination: pulumi.Input[str],
    description: str = "",
) -> EgressRule:
    """Build a TCP egress rule to a CIDR block or subnet reference.

    Args:
        port: Destination TCP port number.
        destination: Destination CIDR or ``pulumi.Input[str]`` subnet
            reference.
        description: Human-readable description.  Defaults to
            ``"TCP {port} egress"``.

    Returns:
        :class:`EgressRule` configured for TCP on *port* to *destination*.

    Example::

        tcp_egress(db_port, vcn.get_secure_subnet_cidr())
        tcp_egress(SSH,     "10.0.0.0/16")
    """
    return EgressRule(
        protocol="tcp",
        destination=destination,
        port_min=port,
        port_max=port,
        description=description or f"TCP {port} egress",
    )


def all_egress(
    destination: pulumi.Input[str],
    description: str = "",
) -> EgressRule:
    """Build an all-protocol egress rule to any destination.

    Pass :data:`INTERNET` for unrestricted outbound via NAT Gateway, or
    :data:`CLOUD_SERVICES` for Oracle-managed service endpoints via Service
    Gateway (no internet path).

    Args:
        destination: Destination CIDR, subnet reference, :data:`INTERNET`,
            or :data:`CLOUD_SERVICES`.
        description: Human-readable description.  Defaults to
            ``"All traffic egress"``.

    Returns:
        :class:`EgressRule` configured for all protocols to *destination*.

    Example::

        all_egress(INTERNET)        # outbound via NAT GW
        all_egress(CLOUD_SERVICES)  # Oracle Services via Service GW
    """
    return EgressRule(
        protocol="all",
        destination=destination,
        description=description or "All traffic egress",
    )


def icmp_path_mtu_egress(description: str = "") -> EgressRule:
    """Build an ICMP type 3 code 4 (Path MTU Discovery) egress rule.

    OCI recommends this on every security list to allow proper MTU
    negotiation for TCP connections.

    Args:
        description: Human-readable description.  Defaults to
            ``"ICMP Path-MTU outbound"``.

    Returns:
        :class:`EgressRule` configured for ICMP 3/4 to the internet.

    Example::

        icmp_path_mtu_egress()
    """
    return EgressRule(
        protocol="icmp",
        destination="internet",
        icmp_type=3,
        icmp_code=4,
        description=description or "ICMP Path-MTU outbound",
    )


class AbstractNetwork(ABC):
    """Builder interface for a cloud network with four subnet tiers.

    All provider network implementations (OCI :class:`~providers.oci.network.Vcn`,
    AWS ``AwsVpc``, GCP ``GcpVpc``) inherit from this class.

    The four tiers follow the OCIBlocks reference architecture:

    * **Public** – load balancers, bastion hosts; route to internet gateway.
    * **Private** – app servers, Kubernetes nodes; route via NAT + service
      gateway (internet-capable outbound).
    * **Secure** – databases, secrets; route via service gateway only
      (no internet path).
    * **Management** – monitoring agents, VPN endpoints; same isolation as
      secure.

    Typical usage by a service block::

        rules = SecurityRules(
            private_ingress=[IngressRule(protocol="tcp", source="...", ...)],
        )
        network.add_security_rules(rules)
        network.finalize_network()  # idempotent

    Attributes:
        id: Provider resource ID of the network (VCN OCID, VPC ID, etc.).
        public_subnet: Provider subnet object for the public tier, or
            ``None`` before :meth:`finalize_network` is called.
        private_subnet: Provider subnet object for the private tier.
        secure_subnet: Provider subnet object for the secure tier.
        management_subnet: Provider subnet object for the management tier.
    """

    id: pulumi.Output[str]
    public_subnet: Any | None
    private_subnet: Any | None
    secure_subnet: Any | None
    management_subnet: Any | None

    @abstractmethod
    def add_security_rules(self, rules: SecurityRules) -> None:
        """Accumulate cloud-neutral security rules for later materialisation.

        Translates each :class:`IngressRule` / :class:`EgressRule` into
        provider-specific firewall constructs and merges them into the
        pending rule set.  Does not create any cloud resources; call
        :meth:`finalize_network` to materialise.

        Args:
            rules: Cloud-neutral rule descriptors to merge into this
                network's pending rule set.
        """

    @abstractmethod
    def finalize_network(self) -> None:
        """Create subnets and firewall resources from accumulated rules.

        Idempotent — only the first call has effect.  Called automatically
        by every service block (Compute, OKE, ScalableWorkload) after it
        has appended its security rules.
        """

    @abstractmethod
    def get_public_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the public subnet tier.

        Returns:
            ``pulumi.Input[str]`` resolving to the public subnet CIDR.
        """

    @abstractmethod
    def get_private_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the private subnet tier.

        Returns:
            ``pulumi.Input[str]`` resolving to the private subnet CIDR.
        """

    @abstractmethod
    def get_secure_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the secure subnet tier.

        Returns:
            ``pulumi.Input[str]`` resolving to the secure subnet CIDR.
        """

    @abstractmethod
    def get_management_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the management subnet tier.

        Returns:
            ``pulumi.Input[str]`` resolving to the management subnet CIDR.
        """

    @abstractmethod
    def export(self) -> None:
        """Publish standard network stack outputs."""


class AbstractNetworkRef(ABC):
    """Read-only reference to a network deployed in another Pulumi stack.

    :meth:`add_security_rules` and :meth:`finalize_network` are deliberate
    no-ops — the owning stack manages all firewall rules.  Service blocks
    accept either :class:`AbstractNetwork` or ``AbstractNetworkRef`` and
    call both methods unconditionally; the no-ops make ``VcnRef``-style
    usage safe without extra branching in service code.

    Example::

        vcn_ref = OciVcnRef.from_stack_reference("org/platform/prod")
        cluster = OkeCluster(name="app", vcn=vcn_ref, ...)
    """

    def add_security_rules(self, rules: SecurityRules) -> None:  # noqa: ARG002
        """No-op — cross-stack refs do not mutate the source network.

        Args:
            rules: Ignored.
        """

    def finalize_network(self) -> None:
        """No-op — cross-stack refs do not mutate the source network."""

    @classmethod
    @abstractmethod
    def from_stack_reference(cls, stack_name: str) -> "AbstractNetworkRef":
        """Construct a read-only network reference from a stack name.

        Args:
            stack_name: Fully qualified Pulumi stack name
                (e.g. ``"org/project/stack"``).

        Returns:
            A populated read-only network reference.
        """


__all__ = [
    "INTERNET",
    "CLOUD_SERVICES",
    "IngressRule",
    "EgressRule",
    "SecurityRules",
    "AbstractNetwork",
    "AbstractNetworkRef",
    "tcp_ingress",
    "icmp_path_mtu_ingress",
    "tcp_egress",
    "all_egress",
    "icmp_path_mtu_egress",
]
