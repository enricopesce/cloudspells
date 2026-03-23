"""Cloud-neutral network abstractions for CloudSpells multi-cloud support.

Defines the security-rule dataclasses, factory helpers, and network
interfaces that decouple spells (Compute, OKE, ScalableWorkload)
from any specific cloud provider.  Each provider translates these
descriptors into its own firewall model (OCI SecurityList, AWS Security
Group, GCP Firewall Rule).

Typical usage:

```python
from cloudspells.core.abstractions.network import (
    SecurityRules, INTERNET, CLOUD_SERVICES,
    tcp_ingress, all_egress,
)
from cloudspells.core.ports import HTTPS, HTTP, SSH, POSTGRES

vcn.add_security_rules(SecurityRules(
    public_ingress=[
        tcp_ingress(HTTPS, INTERNET),
        tcp_ingress(HTTP,  INTERNET),
        tcp_ingress(SSH,   INTERNET),
    ],
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
```

Symbols defined here:

- `INTERNET` — symbolic source/destination meaning `0.0.0.0/0`.
- `CLOUD_SERVICES` — symbolic destination meaning cloud-managed service endpoints.
- `IngressRule` — cloud-neutral inbound security rule descriptor.
- `EgressRule` — cloud-neutral outbound security rule descriptor.
- `SecurityRules` — accumulated rules for all four subnet tiers.
- `AbstractNetwork` — builder interface for cloud networks.
- `AbstractNetworkRef` — read-only reference to a network in another stack.
- `tcp_ingress` — build a TCP ingress rule from any source (CIDR, subnet ref, or `INTERNET`).
- `tcp_egress` — build a TCP egress rule to any destination.
- `all_egress` — build an all-protocol egress rule to any destination.
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
    construct.  The `source` field supports both literal CIDRs and the
    following symbolic names that each provider resolves internally:

    - `"internet"`       — `0.0.0.0/0` on all providers.
    - `"cloud-services"` — OCI Service Gateway CIDR, AWS managed-prefix
      list, or GCP Private Service Access range.

    Attributes:
        protocol: Transport protocol: `"tcp"`, `"udp"`, or `"all"`.
        source: Source CIDR block or symbolic name.
        port_min: First TCP/UDP port in the allowed range (inclusive).
            `None` means no port restriction.
        port_max: Last TCP/UDP port in the allowed range (inclusive).
            `None` means no port restriction.
        description: Human-readable description of the rule's purpose.

    Example:
        ```python
        # Allow SSH from the public subnet CIDR
        rule = IngressRule(
            protocol="tcp",
            source="10.0.0.0/19",
            port_min=22,
            port_max=22,
            description="SSH from bastion host",
        )
        ```
    """

    protocol: str
    source: pulumi.Input[str]
    port_min: int | None = None
    port_max: int | None = None
    description: str = ""


@dataclass
class EgressRule:
    """Cloud-neutral outbound security rule descriptor.

    Mirrors `IngressRule` for egress direction.  The `destination`
    field supports the same symbolic names as `IngressRule.source`.

    Attributes:
        protocol: Transport protocol: `"tcp"`, `"udp"`, or `"all"`.
        destination: Destination CIDR block or symbolic name.
        port_min: First TCP/UDP port in the allowed range (inclusive).
            `None` means no port restriction.
        port_max: Last TCP/UDP port in the allowed range (inclusive).
            `None` means no port restriction.
        description: Human-readable description of the rule's purpose.

    Example:
        ```python
        # Allow HTTPS egress to OCI-managed services
        rule = EgressRule(
            protocol="tcp",
            destination="cloud-services",
            port_min=443,
            port_max=443,
            description="HTTPS to OCI services",
        )
        ```
    """

    protocol: str
    destination: pulumi.Input[str]
    port_min: int | None = None
    port_max: int | None = None
    description: str = ""


@dataclass
class SecurityRules:
    """Accumulated cloud-neutral security rules for all four subnet tiers.

    Spells call `AbstractNetwork.add_security_rules` with a populated
    `SecurityRules` instance.  The network implementation translates each
    `IngressRule` / `EgressRule` into provider-specific constructs (OCI
    `SecurityListIngressSecurityRuleArgs`, AWS `SecurityGroupIngressArgs`,
    etc.) and accumulates them for batch materialisation when
    `AbstractNetwork.finalize_network` is called.

    Attributes:
        public_ingress: Ingress rules for the public (load-balancer) tier.
        public_egress: Egress rules for the public tier.
        private_ingress: Ingress rules for the private (app-server) tier.
        private_egress: Egress rules for the private tier.
        secure_ingress: Ingress rules for the secure (database) tier.
        secure_egress: Egress rules for the secure tier.
        management_ingress: Ingress rules for the management tier.
        management_egress: Egress rules for the management tier.

    Example:
        ```python
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
        ```
    """

    public_ingress: list[IngressRule] = field(default_factory=list)
    public_egress: list[EgressRule] = field(default_factory=list)
    private_ingress: list[IngressRule] = field(default_factory=list)
    private_egress: list[EgressRule] = field(default_factory=list)
    secure_ingress: list[IngressRule] = field(default_factory=list)
    secure_egress: list[EgressRule] = field(default_factory=list)
    management_ingress: list[IngressRule] = field(default_factory=list)
    management_egress: list[EgressRule] = field(default_factory=list)


# ── Source / destination constants ────────────────────────────────────────────

INTERNET: str = "0.0.0.0/0"
"""CIDR representing the public internet.  Works as source or destination
in `tcp_ingress`, `all_egress`, and `tcp_egress`."""

CLOUD_SERVICES: str = "cloud-services"
"""Symbolic destination resolving to cloud-managed service endpoints.

Resolves to the OCI Service Gateway CIDR (`SERVICE_CIDR_BLOCK`) on OCI,
or the equivalent managed-prefix on other clouds.
"""

# ── Security-rule factory helpers ─────────────────────────────────────────────


def tcp_ingress(
    port: int,
    source: pulumi.Input[str],
    description: str = "",
) -> IngressRule:
    """Build a TCP ingress rule from any source.

    source can be a literal CIDR string, a `pulumi.Input[str]` subnet
    reference (e.g. `vcn.get_public_subnet_cidr()`), the `INTERNET`
    constant (`"0.0.0.0/0"`), or the `CLOUD_SERVICES` constant for
    cloud-managed service endpoints.

    Args:
        port: Destination TCP port number.
        source: Source CIDR, subnet reference, `INTERNET`, or
            `CLOUD_SERVICES`.
        description: Human-readable description.  Defaults to
            `"TCP {port} ingress"`.

    Returns:
        `IngressRule` configured for TCP on port from source.

    Example:
        ```python
        tcp_ingress(HTTPS, INTERNET)
        tcp_ingress(app_port, vcn.get_public_subnet_cidr())
        tcp_ingress(POSTGRES, "10.0.8.0/21")
        ```
    """
    return IngressRule(
        protocol="tcp",
        source=source,
        port_min=port,
        port_max=port,
        description=description or f"TCP {port} ingress",
    )


def tcp_egress(
    port: int,
    destination: pulumi.Input[str],
    description: str = "",
) -> EgressRule:
    """Build a TCP egress rule to a CIDR block or subnet reference.

    Args:
        port: Destination TCP port number.
        destination: Destination CIDR or `pulumi.Input[str]` subnet
            reference.
        description: Human-readable description.  Defaults to
            `"TCP {port} egress"`.

    Returns:
        `EgressRule` configured for TCP on port to destination.

    Example:
        ```python
        tcp_egress(db_port, vcn.get_secure_subnet_cidr())
        tcp_egress(SSH,     "10.0.0.0/16")
        ```
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

    Pass `INTERNET` for unrestricted outbound via NAT Gateway, or
    `CLOUD_SERVICES` for Oracle-managed service endpoints via Service
    Gateway (no internet path).

    Args:
        destination: Destination CIDR, subnet reference, `INTERNET`,
            or `CLOUD_SERVICES`.
        description: Human-readable description.  Defaults to
            `"All traffic egress"`.

    Returns:
        `EgressRule` configured for all protocols to destination.

    Example:
        ```python
        all_egress(INTERNET)        # outbound via NAT gateway
        all_egress(CLOUD_SERVICES)  # cloud-managed services (no internet path)
        ```
    """
    return EgressRule(
        protocol="all",
        destination=destination,
        description=description or "All traffic egress",
    )


class AbstractNetwork(ABC):
    """Builder interface for a cloud network with four subnet tiers.

    All provider network implementations (OCI `Vcn`,
    AWS `AwsVpc`, GCP `GcpVpc`) inherit from this class.

    The four tiers follow the CloudSpells reference architecture:

    - **Public** — load balancers, bastion hosts; route to internet gateway.
    - **Private** — app servers, Kubernetes nodes; route via NAT + service
      gateway (internet-capable outbound).
    - **Secure** — databases, secrets; route via service gateway only
      (no internet path).
    - **Management** — monitoring agents, VPN endpoints; same isolation as
      secure.

    Typical usage by a spell:

    ```python
    rules = SecurityRules(
        private_ingress=[IngressRule(protocol="tcp", source="...", ...)],
    )
    network.add_security_rules(rules)
    network.finalize_network()  # idempotent
    ```

    Attributes:
        id: Provider resource ID of the network (VCN OCID, VPC ID, etc.).
        public_subnet: Provider subnet object for the public tier, or
            `None` before `finalize_network` is called.
        private_subnet: Provider subnet object for the private tier, or
            `None` before `finalize_network` is called.
        secure_subnet: Provider subnet object for the secure tier, or
            `None` before `finalize_network` is called.
        management_subnet: Provider subnet object for the management tier, or
            `None` before `finalize_network` is called.
    """

    id: pulumi.Output[str]
    public_subnet: Any | None
    private_subnet: Any | None
    secure_subnet: Any | None
    management_subnet: Any | None

    @abstractmethod
    def add_security_rules(self, rules: SecurityRules) -> None:
        """Accumulate cloud-neutral security rules for later materialisation.

        Translates each `IngressRule` / `EgressRule` into
        provider-specific firewall constructs and merges them into the
        pending rule set.  Does not create any cloud resources; call
        `finalize_network` to materialise.

        Args:
            rules: Cloud-neutral rule descriptors to merge into this
                network's pending rule set.
        """

    @abstractmethod
    def finalize_network(self) -> None:
        """Create subnets and firewall resources from accumulated rules.

        Idempotent — only the first call has effect.  Called automatically
        by every spell (Compute, OKE, ScalableWorkload) after it has
        appended its security rules.
        """

    @abstractmethod
    def get_public_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the public subnet tier.

        Returns:
            `pulumi.Input[str]` resolving to the public subnet CIDR.
        """

    @abstractmethod
    def get_private_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the private subnet tier.

        Returns:
            `pulumi.Input[str]` resolving to the private subnet CIDR.
        """

    @abstractmethod
    def get_secure_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the secure subnet tier.

        Returns:
            `pulumi.Input[str]` resolving to the secure subnet CIDR.
        """

    @abstractmethod
    def get_management_subnet_cidr(self) -> pulumi.Input[str]:
        """Return the CIDR of the management subnet tier.

        Returns:
            `pulumi.Input[str]` resolving to the management subnet CIDR.
        """

    @abstractmethod
    def export(self) -> None:
        """Publish standard network stack outputs.

        Implementations must export at minimum:

        - `vcn_id` — provider resource ID of the network.
        - `public_subnet_cidr` — CIDR of the public tier.
        - `private_subnet_cidr` — CIDR of the private tier.
        - `secure_subnet_cidr` — CIDR of the secure tier.
        - `management_subnet_cidr` — CIDR of the management tier.

        Additional provider-specific outputs (gateway IDs, DNS labels, etc.)
        may be added by the implementation.
        """


class AbstractNetworkRef(ABC):
    """Read-only reference to a network deployed in another Pulumi stack.

    `add_security_rules` and `finalize_network` are deliberate
    no-ops — the owning stack manages all firewall rules.  Spells accept
    either `AbstractNetwork` or `AbstractNetworkRef` and call both methods
    unconditionally; the no-ops make `VcnRef`-style usage safe without
    extra branching in spell code.

    Example:
        ```python
        from cloudspells.providers.oci import VcnRef, OkeCluster

        vcn_ref = VcnRef.from_stack_reference("org/platform/prod")
        cluster = OkeCluster(name="app", vcn=vcn_ref, ...)
        ```
    """

    def add_security_rules(self, rules: SecurityRules) -> None:  # noqa: B027
        """No-op — cross-stack refs do not mutate the source network.

        Args:
            rules: Ignored.
        """

    def finalize_network(self) -> None:  # noqa: B027
        """No-op — cross-stack refs do not mutate the source network."""

    @classmethod
    @abstractmethod
    def from_stack_reference(cls, stack_name: str) -> AbstractNetworkRef:
        """Construct a read-only network reference from a stack name.

        Args:
            stack_name: Fully qualified Pulumi stack name in
                `"org/project/stack"` format (e.g. `"acme/platform/prod"`).

        Returns:
            A populated read-only network reference whose CIDR accessors
            resolve via Pulumi stack outputs from the referenced stack.

        Raises:
            pulumi.RunError: If the referenced stack has never been deployed
                or does not export the expected network output keys.
        """


__all__ = [
    "CLOUD_SERVICES",
    "INTERNET",
    "AbstractNetwork",
    "AbstractNetworkRef",
    "EgressRule",
    "IngressRule",
    "SecurityRules",
    "all_egress",
    "tcp_egress",
    "tcp_ingress",
]
