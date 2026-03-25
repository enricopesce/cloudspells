"""Subnet tier constants shared across all CloudSpells abstractions.

Defines the four canonical network placement tiers and the `SubnetTier`
type alias.  These constants are used by `roles.py`, `compute.py`, and any
future abstraction that needs to express subnet placement.

Keeping tier constants in their own module avoids a coupling where
`roles.py` must import from `compute.py` for a concept more primitive than
either.

Exports:
    SubnetTier: `Literal` type alias for the four valid tier strings.
    SUBNET_PUBLIC: Public tier — internet gateway route.
    SUBNET_PRIVATE: Private tier — NAT + service gateway route.
    SUBNET_SECURE: Secure tier — service gateway only.
    SUBNET_MANAGEMENT: Management tier — service gateway only.
"""

from __future__ import annotations

from typing import Literal

SubnetTier = Literal["public", "private", "secure", "management"]

#: Public tier — load balancers and bastion hosts.  Route: internet gateway.
SUBNET_PUBLIC: SubnetTier = "public"

#: Private tier — app servers, Kubernetes nodes.  Route: NAT + service gateway.
SUBNET_PRIVATE: SubnetTier = "private"

#: Secure tier — databases, secrets.  Route: service gateway only.
SUBNET_SECURE: SubnetTier = "secure"

#: Management tier — monitoring, VPN endpoints.  Route: service gateway only.
SUBNET_MANAGEMENT: SubnetTier = "management"

__all__ = [
    "SUBNET_MANAGEMENT",
    "SUBNET_PRIVATE",
    "SUBNET_PUBLIC",
    "SUBNET_SECURE",
    "SubnetTier",
]
