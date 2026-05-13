"""CloudSpells OCI VCN schema and network profile helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import pulumi
from cloudspells.core.abstractions.network import (
    CLOUD_SERVICES,
    INTERNET,
    EgressRule,
    IngressRule,
    SecurityRules,
)

CLOUDSPELLS_OCI_VCN_SCHEMA = "cloudspells.oci.vcn/v1"
"""Schema marker exported by CloudSpells-managed OCI VCN stacks."""

NETWORK_PROFILE_BASELINE = "cloudspells.oci.vcn.profile/base/v1"
"""Baseline profile present on every CloudSpells-managed OCI VCN."""


def normalize_cidrs(cidrs: Sequence[str] | None) -> tuple[str, ...]:
    """Return a stable, duplicate-free CIDR tuple.

    Args:
        cidrs: CIDR list supplied by the caller, or `None`.

    Returns:
        Sorted tuple with duplicate CIDRs removed.
    """
    return tuple(sorted(dict.fromkeys(cidrs or [])))


def oke_profile_id(kubectl_allowed_cidrs: Sequence[str] | None) -> str:
    """Return the deterministic CloudSpells OKE network profile ID.

    Args:
        kubectl_allowed_cidrs: CIDRs allowed to reach the Kubernetes API on
            TCP 6443. `None` and `[]` are equivalent.

    Returns:
        Stable profile ID suitable for stack export and cross-stack checks.
    """
    cidrs = normalize_cidrs(kubectl_allowed_cidrs)
    if not cidrs:
        return "cloudspells.oci.vcn.profile/oke/v1/kubectl:none"
    digest = hashlib.sha256("\n".join(cidrs).encode("utf-8")).hexdigest()[:16]
    return f"cloudspells.oci.vcn.profile/oke/v1/kubectl:{digest}"


def require_cloudspells_schema(schema: Any) -> str:
    """Validate a CloudSpells OCI VCN schema marker.

    Args:
        schema: Value exported by the source stack.

    Returns:
        The supported schema string.

    Raises:
        RuntimeError: If the source stack did not export the schema marker.
        ValueError: If the schema marker is present but unsupported.
    """
    if schema is None:
        raise RuntimeError(
            "VcnRef requires a CloudSpells OCI VCN schema export. "
            "Deploy the source VCN with Vcn.export() before referencing it."
        )
    if schema != CLOUDSPELLS_OCI_VCN_SCHEMA:
        raise ValueError(
            f"Unsupported CloudSpells OCI VCN schema: {schema!r}. Expected {CLOUDSPELLS_OCI_VCN_SCHEMA!r}."
        )
    return CLOUDSPELLS_OCI_VCN_SCHEMA


def require_profile_id(profile_id: str, profiles: Any) -> str:
    """Validate that a source stack exported `profile_id`.

    Args:
        profile_id: Required profile ID.
        profiles: Exported profile list from the source CloudSpells VCN stack.

    Returns:
        The required profile ID when present.

    Raises:
        RuntimeError: If the profile list is missing or does not contain the
            required profile.
    """
    if profiles is None:
        raise RuntimeError(
            "VcnRef source CloudSpells VCN stack does not export required network profile "
            f"{profile_id!r}. Deploy the source VCN with Vcn.export() before referencing it."
        )
    profile_set = {str(profile) for profile in profiles}
    if profile_id not in profile_set:
        raise RuntimeError(
            "VcnRef source CloudSpells VCN stack does not export required network profile "
            f"{profile_id!r}. Enable the profile in the source VCN stack, run pulumi up "
            "there, then redeploy this stack."
        )
    return profile_id


def oke_security_rules(
    public_subnet_cidr: pulumi.Input[str],
    private_subnet_cidr: pulumi.Input[str],
    kubectl_allowed_cidrs: Sequence[str] | None,
) -> SecurityRules:
    """Build subnet-level security rules required by OKE.

    Args:
        public_subnet_cidr: CIDR of the public subnet tier.
        private_subnet_cidr: CIDR of the private subnet tier.
        kubectl_allowed_cidrs: CIDRs allowed to reach the Kubernetes API on
            TCP 6443. `None` and `[]` mean no external kubectl security-list
            ingress is installed.

    Returns:
        Cloud-neutral security rules for the OKE network profile.
    """

    def tcp_ingress(source: pulumi.Input[str], port_min: int, port_max: int, description: str) -> IngressRule:
        return IngressRule(
            protocol="tcp",
            source=source,
            port_min=port_min,
            port_max=port_max,
            description=description,
        )

    def all_ingress(source: pulumi.Input[str], description: str) -> IngressRule:
        return IngressRule(protocol="all", source=source, description=description)

    def tcp_egress(
        destination: pulumi.Input[str],
        port_min: int | None,
        port_max: int | None,
        description: str,
    ) -> EgressRule:
        return EgressRule(
            protocol="tcp",
            destination=destination,
            port_min=port_min,
            port_max=port_max,
            description=description,
        )

    def all_egress(destination: pulumi.Input[str], description: str) -> EgressRule:
        return EgressRule(protocol="all", destination=destination, description=description)

    public_ingress = [
        tcp_ingress(
            private_subnet_cidr,
            6443,
            6443,
            "Workers and pods communicate with Kubernetes API server for cluster operations and service discovery",
        ),
        tcp_ingress(
            private_subnet_cidr,
            12250,
            12250,
            "Workers and pods communicate with Kubernetes control plane for internal cluster operations",
        ),
        tcp_ingress(
            INTERNET,
            443,
            443,
            "Load Balancer receives HTTPS traffic from internet for public web applications and APIs",
        ),
        tcp_ingress(
            INTERNET,
            80,
            80,
            "Load Balancer receives HTTP traffic from internet for public applications",
        ),
    ]
    for cidr in normalize_cidrs(kubectl_allowed_cidrs):
        public_ingress.append(
            tcp_ingress(
                cidr,
                6443,
                6443,
                f"Allow kubectl access to Kubernetes API from {cidr}",
            )
        )

    return SecurityRules(
        public_ingress=public_ingress,
        public_egress=[
            tcp_egress(
                CLOUD_SERVICES,
                None,
                None,
                "Control plane communicates with OCI services for cluster management and telemetry",
            ),
            tcp_egress(
                private_subnet_cidr,
                10250,
                10250,
                "Control plane manages worker nodes via kubelet for pod operations and health monitoring",
            ),
            tcp_egress(
                private_subnet_cidr,
                30000,
                32767,
                "Load Balancer forwards traffic to worker nodes via NodePort for Kubernetes service routing",
            ),
            tcp_egress(
                private_subnet_cidr,
                10256,
                10256,
                "Load Balancer checks worker node health via kube-proxy",
            ),
            all_egress(
                private_subnet_cidr,
                "Control plane reaches pods on arbitrary ports for webhooks, admission controllers, and metrics",
            ),
        ],
        private_ingress=[
            tcp_ingress(
                public_subnet_cidr,
                10250,
                10250,
                "Control plane manages pods on worker nodes via kubelet for commands, logs, and health monitoring",
            ),
            tcp_ingress(
                public_subnet_cidr,
                30000,
                32767,
                "Load Balancer forwards traffic to worker nodes via NodePort to reach Kubernetes services",
            ),
            tcp_ingress(
                public_subnet_cidr,
                10256,
                10256,
                "Load Balancer verifies worker node health via kube-proxy endpoint before routing traffic",
            ),
            all_ingress(
                public_subnet_cidr,
                "Control plane reaches pods on arbitrary ports for webhooks and admission controllers",
            ),
        ],
        private_egress=[
            tcp_egress(
                CLOUD_SERVICES,
                None,
                None,
                "Workers and pods communicate with OCI services for container images, logging, and monitoring",
            ),
            tcp_egress(
                public_subnet_cidr,
                6443,
                6443,
                "Workers and pods communicate with Kubernetes API to register, report status, and access resources",
            ),
            tcp_egress(
                public_subnet_cidr,
                12250,
                12250,
                "Workers and pods communicate with control plane for internal cluster operations",
            ),
            tcp_egress(
                INTERNET,
                443,
                443,
                "Workers pull container images and pods call external APIs via HTTPS",
            ),
            tcp_egress(
                INTERNET,
                80,
                80,
                "Workers pull container images from HTTP registries and access OCI pre-authenticated URLs",
            ),
        ],
    )
