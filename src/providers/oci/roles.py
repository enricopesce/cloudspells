"""Role-based security posture descriptors for OCIBlocks NSGs.

A `Role` captures the security posture of a class of resources — which subnet
tier it belongs to, what ambient network access it needs, and whether it
accepts SSH management connections from upstream resources.

Predefined roles cover the most common OCI reference architectures.  They are
designed to be passed to `Nsg` via the `role=` parameter, which
auto-generates the correct ambient NSG rules and the corresponding subnet
security list rules so callers never have to write boilerplate firewall
configuration by hand.

Predefined roles:

- `INTERNET_EDGE` — public-facing load balancers or bastion hosts.
  Accepts inbound TCP on explicitly declared ports from `0.0.0.0/0`.
- `APP_SERVER` — private-tier application servers.
  Egresses to Oracle Services and the internet (via NAT Gateway).
- `DATABASE` — secure-tier databases.
  Egresses to Oracle Services only; no internet path.
- `CACHE` — private-tier caches and message brokers.
  Same posture as `APP_SERVER`.
- `MANAGEMENT` — management-tier monitoring agents and tooling.
  Egresses to Oracle Services only; same isolation as `DATABASE`.

Custom roles can be composed by instantiating `Role` directly with any
combination of attributes.

Exports:
    Role: Security posture dataclass.
    INTERNET_EDGE: Predefined role for internet-facing resources.
    APP_SERVER: Predefined role for private-tier application servers.
    DATABASE: Predefined role for secure-tier databases.
    CACHE: Predefined role for private-tier caches and message brokers.
    MANAGEMENT: Predefined role for management-tier tooling.
"""

from __future__ import annotations

from dataclasses import dataclass

from providers.oci.network import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
)


@dataclass
class Role:
    """Security posture descriptor for a class of networked resources.

    A `Role` encodes the ambient network behaviour of an NSG — the rules that
    every resource of this type needs regardless of which peers it communicates
    with.  Directional traffic relationships are declared separately via
    `Nsg.serves`.

    Attributes:
        subnet_tier: Which VCN tier resources carrying this role belong to.
            Used by `ComputeInstance` to infer the `subnet` placement when
            `nsg=` is supplied instead of `subnet=` and `nsg_ids=`.
        egress_internet: `True` adds an all-protocol egress rule to
            `0.0.0.0/0` (outbound via NAT Gateway) to both the NSG and the
            tier's security list.  Suitable for private-tier app servers that
            need to call external APIs.  Not set for `DATABASE`, `MANAGEMENT`,
            or `INTERNET_EDGE`.
        egress_services: `True` adds an all-protocol egress rule to the OCI
            Service Gateway CIDR to both the NSG and the tier's security list.
            Required for any instance that calls Oracle-managed endpoints
            (Object Storage, container registry, etc.).
        accept_management_ssh: `True` causes `Nsg.serves` to automatically
            include an SSH (port 22) management channel from the upstream NSG
            in addition to the application port, and to add the corresponding
            security list cross-subnet SSH rules.  Set `False` for roles where
            SSH access arrives through a separate channel (e.g. an OCI Bastion
            session).

    Example:
        ```python
        from providers.oci.roles import Role
        from providers.oci.network import SUBNET_PRIVATE

        # Custom role: private tier, internet + service egress, no SSH from upstream.
        proxy = Role(
            subnet_tier=SUBNET_PRIVATE,
            egress_internet=True,
            egress_services=True,
            accept_management_ssh=False,
        )
        proxy_nsg = Nsg("proxy", role=proxy, vcn=vcn, compartment_id=compartment_id)
        ```
    """

    subnet_tier: SubnetTier
    egress_internet: bool = False
    egress_services: bool = False
    accept_management_ssh: bool = True


# ── Predefined roles ───────────────────────────────────────────────────────────

INTERNET_EDGE: Role = Role(
    subnet_tier=SUBNET_PUBLIC,
    egress_internet=False,
    egress_services=False,
    accept_management_ssh=False,
)
"""Role for internet-facing load balancers and bastion hosts.

Resources carrying this role are placed in the public subnet (Internet
Gateway route).  Inbound ports are declared via the `ports=` parameter on
`Nsg`.  ICMP path-MTU rules are added automatically to both the NSG and the
public security list.

`accept_management_ssh=False` because this role is the management entry point
— it acts as the SSH source toward private-tier resources, not as an SSH
target from another resource.

Example:
    ```python
    from providers.oci.nsg import Nsg, HTTP, HTTPS, SSH
    from providers.oci.roles import INTERNET_EDGE

    lb_nsg = Nsg(
        "load-balancer",
        role=INTERNET_EDGE,
        ports=[HTTP, HTTPS, SSH],
        vcn=vcn,
        compartment_id=compartment_id,
    )
    ```
"""

APP_SERVER: Role = Role(
    subnet_tier=SUBNET_PRIVATE,
    egress_internet=True,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for private-tier application servers.

Resources carrying this role are placed in the private subnet (NAT Gateway +
Service Gateway routes).  Ambient rules include:

- All-protocol egress to `0.0.0.0/0` via NAT Gateway (package updates,
  external API calls) — added to both NSG and private security list.
- All-protocol egress to Oracle Services via Service Gateway — added to
  both NSG and private security list.
- ICMP path-MTU ingress from `0.0.0.0/0` on the NSG.

When an upstream resource calls `Nsg.serves` toward this role, an SSH
management channel (port 22) is automatically included.

Example:
    ```python
    from providers.oci.nsg import Nsg
    from providers.oci.roles import APP_SERVER

    web_nsg = Nsg("web-backend", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)
    ```
"""

DATABASE: Role = Role(
    subnet_tier=SUBNET_SECURE,
    egress_internet=False,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for secure-tier databases.

Resources carrying this role are placed in the secure subnet (Service Gateway
only — no NAT, no internet path).  Ambient rules include:

- All-protocol egress to Oracle Services via Service Gateway — added to both
  NSG and secure security list.

An SSH management channel is included automatically in incoming `Nsg.serves`
relationships.

Example:
    ```python
    from providers.oci.nsg import Nsg
    from providers.oci.roles import DATABASE

    db_nsg = Nsg("database", role=DATABASE, vcn=vcn, compartment_id=compartment_id)
    ```
"""

CACHE: Role = Role(
    subnet_tier=SUBNET_PRIVATE,
    egress_internet=True,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for private-tier caches and message brokers (Redis, Memcached, Kafka).

Identical security posture to `APP_SERVER` — private subnet, NAT egress,
Service Gateway egress.  Provided as a semantic alias so that the intent of
each resource is clear from its role name.

Example:
    ```python
    from providers.oci.nsg import Nsg
    from providers.oci.roles import CACHE

    cache_nsg = Nsg("redis", role=CACHE, vcn=vcn, compartment_id=compartment_id)
    ```
"""

MANAGEMENT: Role = Role(
    subnet_tier=SUBNET_MANAGEMENT,
    egress_internet=False,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for management-tier monitoring agents, bastion service, and tooling.

Resources carrying this role are placed in the management subnet (Service
Gateway only — same isolation as the secure tier, but logically separated for
operational tooling).  Ambient rules include:

- All-protocol egress to Oracle Services via Service Gateway.

Example:
    ```python
    from providers.oci.nsg import Nsg
    from providers.oci.roles import MANAGEMENT

    mgmt_nsg = Nsg("monitoring", role=MANAGEMENT, vcn=vcn, compartment_id=compartment_id)
    ```
"""

__all__ = [
    "APP_SERVER",
    "CACHE",
    "DATABASE",
    "INTERNET_EDGE",
    "MANAGEMENT",
    "Role",
]
