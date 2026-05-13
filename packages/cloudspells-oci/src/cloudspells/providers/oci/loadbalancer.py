"""OCI Load Balancer spells for CloudSpells.

Provides two purpose-built OCI Load Balancer spells for the most common
internet-facing and internal service routing architectures:

- `LoadBalancer`: Internet-facing HTTPS load balancer placed in the VCN
  public subnet.  TLS is terminated at the load balancer using a
  pre-uploaded certificate; HTTP traffic on port 80 is automatically
  redirected to HTTPS with a 301 response.
- `InternalLoadBalancer`: Private load balancer placed in the VCN private
  subnet for internal service-to-service routing.  No public IP is assigned;
  the load balancer is reachable only from within the VCN.

Both spells use a flexible-shape OCI Load Balancer (10–100 Mbps) with a
ROUND_ROBIN backend set and HTTP health checks on `backend_port`.  Subnet
placement, shape, bandwidth bounds, and backend policy are fixed by the
spell — not configurable by the caller.

Exports:
    LoadBalancer: Internet-facing HTTPS load balancer (public subnet).
    InternalLoadBalancer: Private HTTP load balancer (private subnet).
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.network import EgressRule, IngressRule, SecurityRules
from cloudspells.core.base import BaseResource

from .network import Vcn, VcnRef

# ── Private mixin ─────────────────────────────────────────────────────────────


class _LbMixin:
    """Shared accessors for all CloudSpells load balancer spells.

    Plain base class providing `get_lb_id()`, `get_lb_ip()`, and `export()`
    so the identical implementation is not repeated across every load balancer
    spell class.  Used via multiple inheritance alongside `BaseResource`.
    Not part of the public API.

    Attributes:
        name: Logical resource name; provided by `BaseResource`.
        load_balancer: The underlying `oci.loadbalancer.LoadBalancer`; set by
            each spell's `__init__`.
    """

    name: str
    load_balancer: oci.loadbalancer.LoadBalancer

    def get_lb_id(self) -> pulumi.Output[str]:
        """Return the OCID of the load balancer.

        Returns:
            `pulumi.Output[str]` resolving to the load balancer OCID.
        """
        return self.load_balancer.id

    def get_lb_ip(self) -> pulumi.Output[str]:
        """Return the first IP address assigned to the load balancer.

        Resolves the first entry in the load balancer's `ip_address_details`
        list.  For a public load balancer this is the public VIP; for a
        private load balancer it is the private VIP within the subnet.

        Returns:
            `pulumi.Output[str]` resolving to the IP address string, or an
            empty string if no IP details are available yet.
        """
        return self.load_balancer.ip_address_details.apply(
            lambda details: (details[0].ip_address or "") if details else ""
        )

    def export(self) -> None:
        """Export the load balancer OCID and IP as Pulumi stack outputs.

        Publishes `"{name}_lb_id"` and `"{name}_lb_ip"` where `name` is the
        spell's logical name with hyphens replaced by underscores.

        Example:
            ```python
            lb = LoadBalancer(name="web-frontend", ...)
            lb.export()
            # Exports: web_frontend_lb_id, web_frontend_lb_ip
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_lb_id", self.get_lb_id())
        pulumi.export(f"{prefix}_lb_ip", self.get_lb_ip())


# ── Spell classes ─────────────────────────────────────────────────────────────


class LoadBalancer(BaseResource, _LbMixin):
    """Internet-facing HTTPS load balancer in the VCN public subnet.

    Creates a flexible-shape OCI Load Balancer with TLS termination.
    HTTP traffic on port 80 is redirected to HTTPS (301) via a built-in
    rule set; HTTPS traffic on port 443 is terminated at the load balancer
    using the supplied pre-uploaded certificate and forwarded to backends
    on `backend_port`.

    Resources created:

    - One `oci.loadbalancer.LoadBalancer` (flexible shape, public subnet).
    - One `oci.loadbalancer.BackendSet` (ROUND_ROBIN, HTTP health check).
    - One `oci.loadbalancer.RuleSet` (HTTP→HTTPS 301 redirect rule).
    - One `oci.loadbalancer.Listener` on HTTPS:443 with SSL termination.
    - One `oci.loadbalancer.Listener` on HTTP:80 with the redirect rule set.

    Security rules added to the VCN (only when the network is not yet
    finalised and the VCN is a `Vcn` rather than a `VcnRef`):

    - Public subnet ingress: TCP 80 from `0.0.0.0/0`.
    - Public subnet ingress: TCP 443 from `0.0.0.0/0`.
    - Public subnet egress: TCP `backend_port` to private subnet CIDR.
    - Private subnet ingress: TCP `backend_port` from public subnet CIDR.

    Attributes:
        vcn: The `Vcn` or `VcnRef` this load balancer is deployed into.
        load_balancer: The underlying `oci.loadbalancer.LoadBalancer`.
        backend_set: The `oci.loadbalancer.BackendSet`.
        redirect_rule_set: The `oci.loadbalancer.RuleSet` for HTTP→HTTPS.
        listeners: List of `oci.loadbalancer.Listener` resources
            (`[https_listener, http_listener]`).
        lb_id: `pulumi.Output[str]` resolving to the load balancer OCID.
        lb_ip: `pulumi.Output[str]` resolving to the public VIP address.

    Example:
        ```python
        vcn = Vcn(name="prod", compartment_id=comp_id)

        lb = LoadBalancer(
            name="web-frontend",
            compartment_id=comp_id,
            vcn=vcn,
            certificate_name="my-tls-cert",
            backend_port=8080,
        )
        lb.export()
        ```
    """

    vcn: Vcn | VcnRef
    load_balancer: oci.loadbalancer.LoadBalancer
    backend_set: oci.loadbalancer.BackendSet
    redirect_rule_set: oci.loadbalancer.RuleSet
    listeners: list[oci.loadbalancer.Listener]
    lb_id: pulumi.Output[str]
    lb_ip: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        certificate_name: pulumi.Input[str],
        backend_port: int = 80,
        health_check_path: str = "/health",
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create an internet-facing HTTPS load balancer.

        Args:
            name: Logical name (e.g. `"web-frontend"`). Combined with the
                stack name to form `"{stack}-{name}-lb"`.
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` providing the subnets and security lists.
                The load balancer is placed in the public subnet.
            certificate_name: Name of a TLS certificate already uploaded to
                the OCI Load Balancer service in this compartment.  Used for
                HTTPS termination on port 443.  Obtain the name from the OCI
                Console under **Load Balancers → Certificates**, or via the
                OCI CLI before deploying this spell.
            backend_port: Port on which backend instances accept forwarded
                traffic and health-check probes.  Defaults to `80`.
            health_check_path: HTTP path used for backend health checks.
                Defaults to `"/health"`.  Must be a valid absolute URL path
                (e.g. `"/healthz"`, `"/status"`).
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `backend_port` is not in the range 1-65535.
            RuntimeError: If the VCN public or private subnet is absent after
                `finalize_network()` completes.
        """
        if not (1 <= backend_port <= 65535):
            raise ValueError(f"backend_port ({backend_port}) must be in the range 1-65535")

        super().__init__("custom:loadbalancer:LoadBalancer", name, compartment_id, stack_name, opts)

        self.vcn = vcn
        self.listeners = []

        # 1. Register security rules before finalising the network.
        if isinstance(self.vcn, Vcn):
            self._add_security_rules(backend_port)
        # finalize_network() is idempotent for Vcn and a no-op for VcnRef.
        self.vcn.finalize_network()

        # 2. Load balancer — flexible shape, public subnet, public IP.
        lb_name = self.create_resource_name("lb")
        self.load_balancer = oci.loadbalancer.LoadBalancer(
            lb_name,
            compartment_id=self.compartment_id,
            display_name=lb_name,
            shape="flexible",
            shape_details=oci.loadbalancer.LoadBalancerShapeDetailsArgs(
                minimum_bandwidth_in_mbps=10,
                maximum_bandwidth_in_mbps=100,
            ),
            subnet_ids=[self.vcn.get_public_subnet_id()],
            is_private=False,
            freeform_tags=self.create_freeform_tags(lb_name, "load-balancer"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # 3. Backend set — round-robin, HTTP health check on backend_port.
        bs_name = self.create_resource_name("bs")
        self.backend_set = oci.loadbalancer.BackendSet(
            bs_name,
            load_balancer_id=self.load_balancer.id,
            name=bs_name,
            policy="ROUND_ROBIN",
            health_checker=oci.loadbalancer.BackendSetHealthCheckerArgs(
                protocol="HTTP",
                port=backend_port,
                url_path=health_check_path,
                interval_ms=10000,
                timeout_in_millis=3000,
                retries=3,
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # 4. Rule set — HTTP→HTTPS 301 redirect.
        rs_name = self.create_resource_name("rs-redirect")
        self.redirect_rule_set = oci.loadbalancer.RuleSet(
            rs_name,
            load_balancer_id=self.load_balancer.id,
            name=rs_name,
            items=[
                oci.loadbalancer.RuleSetItemArgs(
                    action="REDIRECT",
                    response_code=301,
                    redirect_uri=oci.loadbalancer.RuleSetItemRedirectUriArgs(
                        protocol="HTTPS",
                        port=443,
                    ),
                ),
            ],
            opts=pulumi.ResourceOptions(parent=self),
        )

        # 5. HTTPS listener on port 443 — TLS termination.
        https_name = self.create_resource_name("listener-https")
        https_listener = oci.loadbalancer.Listener(
            https_name,
            load_balancer_id=self.load_balancer.id,
            name=https_name,
            default_backend_set_name=self.backend_set.name,
            port=443,
            protocol="HTTPS",
            ssl_configuration=oci.loadbalancer.ListenerSslConfigurationArgs(
                certificate_name=certificate_name,
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.listeners.append(https_listener)

        # 6. HTTP listener on port 80 — redirect to HTTPS via rule set.
        http_name = self.create_resource_name("listener-http")
        http_listener = oci.loadbalancer.Listener(
            http_name,
            load_balancer_id=self.load_balancer.id,
            name=http_name,
            default_backend_set_name=self.backend_set.name,
            port=80,
            protocol="HTTP",
            rule_set_names=[self.redirect_rule_set.name],
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.listeners.append(http_listener)

        # 7. Expose outputs.
        self.lb_id = self.load_balancer.id
        self.lb_ip = self.get_lb_ip()
        self.register_outputs({
            "lb_id": self.load_balancer.id,
            "lb_ip": self.lb_ip,
        })

    def _add_security_rules(self, backend_port: int) -> None:
        """Register load balancer security rules on the VCN public and private subnets.

        Adds the following rules:

        - Public subnet ingress TCP 80 from `0.0.0.0/0` (fingerprinted as
          `"lb-public-ingress-tcp-80"` — deduplicated if another spell such
          as `ScalableWorkload` registers the same rule on this VCN).
        - Public subnet ingress TCP 443 from `0.0.0.0/0` (fingerprinted as
          `"lb-public-ingress-tcp-443"`).
        - Public subnet egress TCP `backend_port` to private subnet CIDR
          (workload-specific, not fingerprinted).
        - Private subnet ingress TCP `backend_port` from public subnet CIDR
          (health checks and forwarded traffic from the LB).

        Must be called before `Vcn.finalize_network`.

        Args:
            backend_port: Port on which backend instances accept forwarded
                traffic and health-check probes.

        Raises:
            TypeError: If `self.vcn` is not a `Vcn` instance.
        """
        if not isinstance(self.vcn, Vcn):
            raise TypeError(f"_add_security_rules requires a Vcn instance, got {type(self.vcn)!r}")

        public_subnet_cidr: pulumi.Input[str] = self.vcn.get_public_subnet_cidr()
        private_subnet_cidr: pulumi.Input[str] = self.vcn.get_private_subnet_cidr()

        self.vcn.add_unique_security_rules(
            "lb-public-ingress-tcp-80",
            SecurityRules(
                public_ingress=[
                    IngressRule(
                        protocol="tcp",
                        source="0.0.0.0/0",
                        port_min=80,
                        port_max=80,
                        description="HTTP traffic from internet to load balancer",
                    ),
                ],
            ),
        )
        self.vcn.add_unique_security_rules(
            "lb-public-ingress-tcp-443",
            SecurityRules(
                public_ingress=[
                    IngressRule(
                        protocol="tcp",
                        source="0.0.0.0/0",
                        port_min=443,
                        port_max=443,
                        description="HTTPS traffic from internet to load balancer",
                    ),
                ],
            ),
        )
        self.vcn.add_security_rules(
            SecurityRules(
                public_egress=[
                    EgressRule(
                        protocol="tcp",
                        destination=private_subnet_cidr,
                        port_min=backend_port,
                        port_max=backend_port,
                        description=f"Load balancer forwards traffic to backend instances on port {backend_port}",
                    ),
                ],
                private_ingress=[
                    IngressRule(
                        protocol="tcp",
                        source=public_subnet_cidr,
                        port_min=backend_port,
                        port_max=backend_port,
                        description=f"Traffic from load balancer to backend instances on port {backend_port}",
                    ),
                ],
            )
        )


class InternalLoadBalancer(BaseResource, _LbMixin):
    """Private HTTP load balancer in the VCN private subnet.

    Creates a flexible-shape OCI Load Balancer with `is_private=True` placed
    in the VCN private subnet.  No public IP is assigned; the load balancer is
    reachable only from within the VCN.  A single HTTP listener on port 80
    accepts connections and forwards traffic to backends on `backend_port`.

    Resources created:

    - One `oci.loadbalancer.LoadBalancer` (flexible shape, private subnet,
      no public IP).
    - One `oci.loadbalancer.BackendSet` (ROUND_ROBIN, HTTP health check).
    - One `oci.loadbalancer.Listener` on HTTP:80.

    Security rules added to the VCN (only when the network is not yet
    finalised and the VCN is a `Vcn` rather than a `VcnRef`):

    - Private subnet ingress: TCP 80 from VCN CIDR (restricts to
      VCN-internal and on-premises traffic only).
    - Private subnet egress: TCP `backend_port` to private subnet CIDR.

    Attributes:
        vcn: The `Vcn` or `VcnRef` this load balancer is deployed into.
        load_balancer: The underlying `oci.loadbalancer.LoadBalancer`.
        backend_set: The `oci.loadbalancer.BackendSet`.
        listener: The `oci.loadbalancer.Listener` on HTTP:80.
        lb_id: `pulumi.Output[str]` resolving to the load balancer OCID.
        lb_ip: `pulumi.Output[str]` resolving to the private VIP address.

    Example:
        ```python
        vcn = Vcn(name="prod", compartment_id=comp_id)

        ilb = InternalLoadBalancer(
            name="api-gateway",
            compartment_id=comp_id,
            vcn=vcn,
            backend_port=8080,
        )
        ilb.export()
        ```
    """

    vcn: Vcn | VcnRef
    load_balancer: oci.loadbalancer.LoadBalancer
    backend_set: oci.loadbalancer.BackendSet
    listener: oci.loadbalancer.Listener
    lb_id: pulumi.Output[str]
    lb_ip: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        backend_port: int = 80,
        health_check_path: str = "/health",
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a private internal HTTP load balancer.

        Args:
            name: Logical name (e.g. `"api-gateway"`). Combined with the
                stack name to form `"{stack}-{name}-lb"`.
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` providing the subnets and security lists.
                The load balancer is placed in the private subnet.
            backend_port: Port on which backend instances accept forwarded
                traffic and health-check probes.  Defaults to `80`.
            health_check_path: HTTP path used for backend health checks.
                Defaults to `"/health"`.  Must be a valid absolute URL path
                (e.g. `"/healthz"`, `"/status"`).
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `backend_port` is not in the range 1-65535.
            RuntimeError: If the VCN private subnet is absent after
                `finalize_network()` completes.
        """
        if not (1 <= backend_port <= 65535):
            raise ValueError(f"backend_port ({backend_port}) must be in the range 1-65535")

        super().__init__("custom:loadbalancer:InternalLoadBalancer", name, compartment_id, stack_name, opts)

        self.vcn = vcn

        # 1. Register security rules before finalising the network.
        if isinstance(self.vcn, Vcn):
            self._add_security_rules(backend_port)
        # finalize_network() is idempotent for Vcn and a no-op for VcnRef.
        self.vcn.finalize_network()

        # 2. Load balancer — flexible shape, private subnet, no public IP.
        lb_name = self.create_resource_name("lb")
        self.load_balancer = oci.loadbalancer.LoadBalancer(
            lb_name,
            compartment_id=self.compartment_id,
            display_name=lb_name,
            shape="flexible",
            shape_details=oci.loadbalancer.LoadBalancerShapeDetailsArgs(
                minimum_bandwidth_in_mbps=10,
                maximum_bandwidth_in_mbps=100,
            ),
            subnet_ids=[self.vcn.get_private_subnet_id()],
            is_private=True,
            freeform_tags=self.create_freeform_tags(lb_name, "load-balancer"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # 3. Backend set — round-robin, HTTP health check on backend_port.
        bs_name = self.create_resource_name("bs")
        self.backend_set = oci.loadbalancer.BackendSet(
            bs_name,
            load_balancer_id=self.load_balancer.id,
            name=bs_name,
            policy="ROUND_ROBIN",
            health_checker=oci.loadbalancer.BackendSetHealthCheckerArgs(
                protocol="HTTP",
                port=backend_port,
                url_path=health_check_path,
                interval_ms=10000,
                timeout_in_millis=3000,
                retries=3,
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # 4. HTTP listener on port 80.
        listener_name = self.create_resource_name("listener-http")
        self.listener = oci.loadbalancer.Listener(
            listener_name,
            load_balancer_id=self.load_balancer.id,
            name=listener_name,
            default_backend_set_name=self.backend_set.name,
            port=80,
            protocol="HTTP",
            opts=pulumi.ResourceOptions(parent=self),
        )

        # 5. Expose outputs.
        self.lb_id = self.load_balancer.id
        self.lb_ip = self.get_lb_ip()
        self.register_outputs({
            "lb_id": self.load_balancer.id,
            "lb_ip": self.lb_ip,
        })

    def _add_security_rules(self, backend_port: int) -> None:
        """Register internal load balancer security rules on the VCN private subnet.

        Adds the following rules:

        - Private subnet ingress TCP 80 from `vcn.cidr_block` (fingerprinted as
          `"lb-private-ingress-tcp-80"` — restricts ingress to VCN-internal and
          on-premises traffic only).
        - Private subnet egress TCP `backend_port` to private subnet CIDR
          (forwarded traffic from the load balancer to backend instances).

        Must be called before `Vcn.finalize_network`.

        Args:
            backend_port: Port on which backend instances accept forwarded
                traffic and health-check probes.

        Raises:
            TypeError: If `self.vcn` is not a `Vcn` instance.
        """
        if not isinstance(self.vcn, Vcn):
            raise TypeError(f"_add_security_rules requires a Vcn instance, got {type(self.vcn)!r}")

        private_subnet_cidr: pulumi.Input[str] = self.vcn.get_private_subnet_cidr()

        self.vcn.add_unique_security_rules(
            "lb-private-ingress-tcp-80",
            SecurityRules(
                private_ingress=[
                    IngressRule(
                        protocol="tcp",
                        source=self.vcn.cidr_block,
                        port_min=80,
                        port_max=80,
                        description="HTTP traffic to internal load balancer from VCN-internal sources only",
                    ),
                ],
            ),
        )
        self.vcn.add_security_rules(
            SecurityRules(
                private_egress=[
                    EgressRule(
                        protocol="tcp",
                        destination=private_subnet_cidr,
                        port_min=backend_port,
                        port_max=backend_port,
                        description=(
                            f"Internal load balancer forwards traffic to backend instances on port {backend_port}"
                        ),
                    ),
                ],
            )
        )


__all__ = [
    "InternalLoadBalancer",
    "LoadBalancer",
]
