"""Cloud-neutral role-based security posture descriptors.

A `Role` captures the ambient network behaviour of a class of resources —
which subnet tier it belongs to, what outbound access it needs, and whether
it accepts SSH management connections from upstream resources.  It is the
cloud-neutral counterpart of per-provider NSG/security-group rule sets.

The four-tier topology (public / private / secure / management) is universal
across cloud providers; the predefined roles below encode the most common
reference-architecture assignments.

Predefined roles:

- `INTERNET_EDGE` — public-facing load balancers or bastion hosts.
- `APP_SERVER` — private-tier application servers; NAT + service egress.
- `DATABASE` — secure-tier databases; service egress only.
- `CACHE` — private-tier caches and message brokers; same posture as `APP_SERVER`.
- `MANAGEMENT` — management-tier monitoring agents and tooling; service egress only.

The `Role` dataclass is the base type; the five constants above are the
complete predefined set.  Callers can also construct custom `Role` instances
for non-standard postures.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tiers import SUBNET_MANAGEMENT, SUBNET_PRIVATE, SUBNET_PUBLIC, SUBNET_SECURE, SubnetTier


@dataclass(frozen=True)
class Role:
    """Security posture descriptor for a class of networked resources.

    A `Role` encodes the ambient network behaviour of a security group — the
    rules that every resource of this type needs regardless of which peers it
    communicates with.  Directional traffic relationships are declared
    separately by the provider's NSG/security-group implementation.

    Attributes:
        name: Human-readable identifier for this role (e.g. `"APP_SERVER"`).
            Used as a stable identity field so that two `Role` instances with
            identical network flags but different names compare as unequal.
        subnet_tier: Which network tier resources carrying this role belong to.
            Used by compute spells to infer subnet placement when a role is
            supplied instead of an explicit subnet.
        egress_internet: `True` adds an all-protocol egress rule to
            `0.0.0.0/0` (outbound via NAT Gateway or equivalent).  Suitable
            for private-tier app servers that call external APIs.  Not set for
            `DATABASE`, `MANAGEMENT`, or `INTERNET_EDGE`.
        egress_services: `True` adds an all-protocol egress rule to the cloud
            provider's managed-services endpoint (OCI Service Gateway, AWS
            VPC Gateway, GCP Private Google Access).  Required for any
            instance that calls provider-managed endpoints (object storage,
            container registry, etc.).
        accept_management_ssh: `True` causes the provider NSG implementation
            to automatically include an SSH (port 22) management channel from
            the upstream NSG in addition to the application port.  Set `False`
            for roles where SSH access arrives through a separate channel (e.g.
            a bastion service session).

    Example:
        ```python
        from cloudspells.core.abstractions import Role
        from cloudspells.core.abstractions import SUBNET_PRIVATE

        # Custom role: private tier, internet + service egress, no SSH from upstream.
        proxy = Role(
            name="PROXY",
            subnet_tier=SUBNET_PRIVATE,
            egress_internet=True,
            egress_services=True,
            accept_management_ssh=False,
        )
        ```
    """

    name: str
    subnet_tier: SubnetTier
    egress_internet: bool = False
    egress_services: bool = False
    accept_management_ssh: bool = True


# ── Predefined roles ────────────────────────────────────────────────────────

INTERNET_EDGE: Role = Role(
    name="INTERNET_EDGE",
    subnet_tier=SUBNET_PUBLIC,
    egress_internet=False,
    egress_services=False,
    accept_management_ssh=False,
)
"""Role for internet-facing load balancers and bastion hosts.

Resources carrying this role are placed in the public subnet (internet
gateway route).  Inbound ports are declared via the provider NSG `ports=`
parameter.

`egress_internet=False` and `egress_services=False` because public-tier
resources do not initiate outbound connections — they receive inbound
traffic and forward it to the private tier.  Adding general egress here
would violate the CloudSpells network isolation model.

`accept_management_ssh=False` because this role is the management entry
point — it acts as the SSH source toward private-tier resources, not as an
SSH target from another resource.

Example:
    ```python
    from cloudspells.core.abstractions import INTERNET_EDGE
    from cloudspells.providers.oci import Nsg

    lb_nsg = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS], vcn=vcn,
                 compartment_id=compartment_id)
    ```
"""

APP_SERVER: Role = Role(
    name="APP_SERVER",
    subnet_tier=SUBNET_PRIVATE,
    egress_internet=True,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for private-tier application servers.

Resources carrying this role are placed in the private subnet (NAT gateway +
service gateway routes).  Ambient rules include outbound access to the
internet and to provider-managed services.

Example:
    ```python
    from cloudspells.core.abstractions import APP_SERVER
    from cloudspells.providers.oci import Nsg

    web_nsg = Nsg("web-backend", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)
    ```
"""

DATABASE: Role = Role(
    name="DATABASE",
    subnet_tier=SUBNET_SECURE,
    egress_internet=False,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for secure-tier databases.

Resources carrying this role are placed in the secure subnet (service gateway
only — no NAT, no internet path).

Example:
    ```python
    from cloudspells.core.abstractions import DATABASE
    from cloudspells.providers.oci import Nsg

    db_nsg = Nsg("database", role=DATABASE, vcn=vcn, compartment_id=compartment_id)
    ```
"""

CACHE: Role = Role(
    name="CACHE",
    subnet_tier=SUBNET_PRIVATE,
    egress_internet=True,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for private-tier caches and message brokers (Redis, Memcached, Kafka).

Identical network posture to `APP_SERVER` — private subnet, internet egress
via NAT, and service-endpoint egress.  Provided as a distinct constant so
that the purpose of each NSG is immediately clear from its role name:
use `APP_SERVER` for stateless compute and `CACHE` for stateful
caching/messaging resources.  The `name="CACHE"` field ensures that
`CACHE != APP_SERVER` under equality even though their other flags are
identical, preventing accidental role confusion in NSG and security-list
logic.

Example:
    ```python
    from cloudspells.core.abstractions import CACHE
    from cloudspells.providers.oci import Nsg

    cache_nsg = Nsg("redis", role=CACHE, vcn=vcn, compartment_id=compartment_id)
    ```
"""

MANAGEMENT: Role = Role(
    name="MANAGEMENT",
    subnet_tier=SUBNET_MANAGEMENT,
    egress_internet=False,
    egress_services=True,
    accept_management_ssh=True,
)
"""Role for management-tier monitoring agents, bastion service, and tooling.

Resources carrying this role are placed in the management subnet (service
gateway only — same isolation as the secure tier, but logically separated for
operational tooling).

Example:
    ```python
    from cloudspells.core.abstractions import MANAGEMENT
    from cloudspells.providers.oci import Nsg

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
