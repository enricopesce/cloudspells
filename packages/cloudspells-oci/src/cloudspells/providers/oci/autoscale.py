"""Scalable Workload spell for CloudSpells.

Provides `ScalableWorkload`, which creates a complete horizontally-scalable
OCI compute tier with load balancing and autoscaling:

- **OCI Load Balancer** (flexible shape) — public-facing in the VCN's public
  subnet by default, or internal in the private subnet when
  `OciLoadBalancerConfig.is_public=False`.  HTTP and optional HTTPS listeners.
- **Instance Configuration** as a launch template for pool instances.
- **Instance Pool** in the VCN's private subnet, spread across all
  availability domains.
- **Autoscaling Configuration** — metric-based (CPU/memory) or schedule-based
  (cron expressions).

Supporting configuration dataclasses:

- `OciLoadBalancerConfig`: Customise LB port, health check path, bandwidth, and SSL.
- `MetricScalingPolicy`: Scale in/out based on CPU or memory utilisation thresholds.
- `ScheduleScalingPolicy`: Scale in/out on a Quartz cron schedule (e.g. business hours).
- `ScheduleEntry`: A single cron-schedule scaling action.
- `ScalingMetric`: Enum of available metric types.
- `ScalingAction`: Enum of available scaling action types.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import cast

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.autoscale import (
    AbstractScalableWorkload,
    MetricScalingPolicy,
    ScalingAction,
    ScalingMetric,
    ScheduleEntry,
    ScheduleScalingPolicy,
)
from cloudspells.core.abstractions.autoscale import (
    LoadBalancerConfig as _BaseLoadBalancerConfig,
)
from cloudspells.core.abstractions.network import EgressRule, IngressRule, SecurityRules
from cloudspells.core.base import BaseResource

from .network import Vcn, VcnRef


class _UnsetType:
    """Sentinel type distinguishing `scaling_policy` not provided from `None`."""


_UNSET = _UnsetType()


@dataclass
class OciLoadBalancerConfig(_BaseLoadBalancerConfig):
    """OCI-specific load balancer configuration extending the cloud-neutral base.

    Adds OCI flexible-shape bandwidth parameters to the base `_BaseLoadBalancerConfig`.
    Use this class when deploying `ScalableWorkload` on OCI.

    Attributes:
        backend_port: Port on backend instances to receive forwarded traffic
            and health-check probes.  Default: `80`.
        health_check_path: HTTP path used for backend health checks.
            Default: `"/health"`.
        is_public: Whether the load balancer is assigned a public IP.
            This also drives subnet placement and ingress-rule topology:
            when `True` (default), the LB is placed in the VCN public
            subnet and HTTP/HTTPS ingress is allowed from `0.0.0.0/0`;
            when `False`, the LB is placed in the VCN private subnet and
            HTTP/HTTPS ingress is only allowed from within the VCN CIDR —
            no internet exposure.
            Default: `True`.
        min_bandwidth_mbps: Minimum bandwidth allocated to the OCI flexible
            load-balancer shape in Mbps.  OCI will not reduce below this value even
            when traffic is idle.  Default: `10`.
        max_bandwidth_mbps: Maximum bandwidth the OCI flexible load-balancer
            shape may burst to in Mbps.  Default: `100`.
        ssl_certificate_name: Name of a certificate object already uploaded to
            the load balancer.  When set, an HTTPS listener on port 443 is created
            alongside the HTTP listener on port 80.  Default: `None` (HTTP only).

    Example:
        ```python
        from cloudspells.providers.oci import OciLoadBalancerConfig

        lb_cfg = OciLoadBalancerConfig(
            backend_port=8080,
            health_check_path="/api/health",
            min_bandwidth_mbps=100,
            max_bandwidth_mbps=500,
        )
        ```
    """

    min_bandwidth_mbps: int = 10
    max_bandwidth_mbps: int = 100


class ScalableWorkload(BaseResource, AbstractScalableWorkload):
    """OCI Scalable Workload with load balancer, instance pool, and autoscaling.

    Creates a complete horizontally-scalable compute tier following OCI best
    practices:

    - OCI Load Balancer (flexible shape) — public-facing in the VCN public
      subnet by default, or internal in the private subnet when
      `OciLoadBalancerConfig.is_public=False`.  HTTP and optional HTTPS
      listeners.
    - Instance Configuration as the launch template for pool VMs.
    - Instance Pool in the VCN private subnet, spread across all
      availability domains.
    - Autoscaling Configuration — metric-based (CPU/memory thresholds) or
      schedule-based (Quartz cron).  Pass `None` to disable autoscaling.

    Security rules are added automatically to the VCN via
    `Vcn.add_security_rules` before `Vcn.finalize_network` is called.

    Attributes:
        vcn: The `Vcn` or `VcnRef` this workload is deployed into.
        shape: Compute shape for instance pool VMs
            (e.g. `"VM.Standard.E4.Flex"`).
        ocpus: Number of OCPUs per instance.
        memory_in_gbs: RAM in GiB per instance.
        ssh_public_key: OpenSSH public key installed on instances.
        ssh_private_key: Corresponding private key, or `None` when the caller
            supplied their own public key.
        image_id: OCID of the boot image resolved for the pool instances.
        cloud_init_script: Base64-encoded cloud-init script stored internally,
            or `None`.  Pass a plain `str` or `bytes` to `__init__`; encoding
            is performed automatically.
        min_instances: Minimum (floor) number of instances for autoscaling.
        max_instances: Maximum (ceiling) number of instances for autoscaling.
        initial_instances: Instance count when the pool is first created.
        load_balancer_config: `OciLoadBalancerConfig` in use.
        scaling_policy: `MetricScalingPolicy`, `ScheduleScalingPolicy`, or `None`.
        boot_volume_size_in_gbs: Boot volume size in GiB for pool instances.
        auto_generated_keys: `True` when SSH keys were auto-generated.
        load_balancer: The `oci.loadbalancer.LoadBalancer` resource.
        backend_set: The `oci.loadbalancer.BackendSet` resource.
        listeners: List of `oci.loadbalancer.Listener` resources (HTTP,
            and optionally HTTPS).
        instance_configuration: The `oci.core.InstanceConfiguration`
            resource used as the pool launch template.
        instance_pool: The `oci.core.InstancePool` resource.
        autoscaling_configuration: The
            `oci.autoscaling.AutoScalingConfiguration` resource, or `None`
            when autoscaling is disabled.
        id: `pulumi.Output[str]` of the instance pool OCID.

    Example:
        ```python
        vcn = Vcn(name="app", compartment_id=comp_id, cidr_block="10.0.0.0/16")

        pool = ScalableWorkload(
            name="web",
            compartment_id=comp_id,
            vcn=vcn,
            min_instances=2,
            max_instances=10,
            load_balancer_config=OciLoadBalancerConfig(backend_port=8080),
            scaling_policy=MetricScalingPolicy(scale_out_threshold=70),
        )

        pulumi.export("lb_ip", pool.get_load_balancer_ip())
        ```
    """

    vcn: Vcn | VcnRef
    shape: pulumi.Input[str]
    ocpus: pulumi.Input[float]
    memory_in_gbs: pulumi.Input[float]
    boot_volume_size_in_gbs: pulumi.Input[int]
    ssh_public_key: str
    ssh_private_key: str | None
    image_id: pulumi.Input[str]
    cloud_init_script: str | None
    min_instances: int
    max_instances: int
    initial_instances: int
    load_balancer_config: OciLoadBalancerConfig
    scaling_policy: MetricScalingPolicy | ScheduleScalingPolicy | None
    auto_generated_keys: bool

    # Resources
    load_balancer: oci.loadbalancer.LoadBalancer
    backend_set: oci.loadbalancer.BackendSet
    listeners: list[oci.loadbalancer.Listener]
    instance_configuration: oci.core.InstanceConfiguration
    instance_pool: oci.core.InstancePool
    autoscaling_configuration: oci.autoscaling.AutoScalingConfiguration | None
    id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        image_id: pulumi.Input[str],
        stack_name: str | None = None,
        # Instance configuration
        shape: pulumi.Input[str] = "VM.Standard.E4.Flex",
        ocpus: pulumi.Input[float] = 1,
        memory_in_gbs: pulumi.Input[float] = 16,
        ssh_public_key: pulumi.Input[str] | None = None,
        cloud_init_script: str | bytes | None = None,
        boot_volume_size_in_gbs: pulumi.Input[int] = 50,
        # Pool configuration
        min_instances: int = 1,
        max_instances: int = 5,
        initial_instances: int | None = None,
        # Load balancer configuration
        load_balancer_config: OciLoadBalancerConfig | None = None,
        # Scaling policy (metric OR schedule, not both); pass None to disable autoscaling
        scaling_policy: MetricScalingPolicy | ScheduleScalingPolicy | _UnsetType | None = _UNSET,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a scalable workload with load balancer, instance pool, and autoscaling.

        Args:
            name: Logical name for the workload (e.g. `"web"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` providing the 4-tier network.  The load
                balancer is placed in the public subnet and the instance pool
                in the private subnet.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            shape: OCI compute shape for instance pool VMs
                (default: `"VM.Standard.E4.Flex"`).
            ocpus: Number of OCPUs per instance (default: `1`).
            memory_in_gbs: RAM in GiB per instance (default: `16`).
            image_id: Boot image OCID for pool instances
                (e.g. `"ocid1.image.oc1.phx.aaaaaa..."`).  Must be an
                explicit OCID — CloudSpells does not perform
                auto-discovery.  Obtain the OCID from the OCI Console or
                CLI and commit it to your Pulumi stack config.
            ssh_public_key: OpenSSH public key to install on instances.
                When `None` or empty, a key pair is auto-generated and
                exported as Pulumi secrets.
            cloud_init_script: Cloud-init script as a plain `str` or `bytes`.
                Must start with a shebang line (e.g. `#!/bin/bash`) when
                provided as a non-empty `str`; CloudSpells validates this
                and raises `ValueError` otherwise.  CloudSpells
                base64-encodes the script before passing to OCI.  When
                `None`, no cloud-init script is injected.  If the
                configured `health_check_path` requires a running HTTP
                server, the script must open the port matching
                `OciLoadBalancerConfig.backend_port`.

                Security:
                    Callers must not embed secrets (API keys, passwords,
                    tokens) in the cloud-init script — it is stored
                    base64-encoded in OCI instance metadata and is
                    readable by any user with access to the instance's
                    metadata service or instance details.
            boot_volume_size_in_gbs: Boot volume size in GiB (default:
                `50`).
            min_instances: Minimum number of instances in the pool
                (default: `1`).
            max_instances: Maximum number of instances the autoscaler may
                create (default: `5`).
            initial_instances: Initial instance count when the pool is first
                created.  Defaults to `min_instances`.
            load_balancer_config: `OciLoadBalancerConfig` dataclass.  Defaults
                to `OciLoadBalancerConfig()` (port 80, health check `/health`,
                10-100 Mbps, public).
            scaling_policy: Autoscaling policy.  Pass a `MetricScalingPolicy`
                (CPU/memory threshold), a `ScheduleScalingPolicy`
                (cron-based), or `None` to disable autoscaling entirely.
                When omitted, defaults to `MetricScalingPolicy()`
                (80% CPU scale-out).
            opts: Pulumi resource options forwarded to the component.

        Raises:
            RuntimeError: If the VCN public or private subnet is absent after
                `finalize_network()` completes.
            ValueError: If `cloud_init_script` is a non-empty string that does
                not start with a shebang line (e.g. `#!/bin/bash`).

        """
        super().__init__("custom:compute:ScalableWorkload", name, compartment_id, stack_name, opts)

        self.vcn = vcn
        self.shape = shape
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs
        self.image_id = image_id
        self.boot_volume_size_in_gbs = boot_volume_size_in_gbs
        self.min_instances = min_instances
        self.max_instances = max_instances
        self.initial_instances = initial_instances if initial_instances is not None else min_instances
        self.load_balancer_config = load_balancer_config or OciLoadBalancerConfig()
        if scaling_policy is _UNSET:
            self.scaling_policy = MetricScalingPolicy()
        else:
            # cast: _UnsetType is exhausted by the isinstance guard above
            self.scaling_policy = cast("MetricScalingPolicy | ScheduleScalingPolicy | None", scaling_policy)
        self.listeners = []
        self.autoscaling_configuration = None

        # Validate + base64-encode cloud_init_script; OCI metadata["user_data"] requires base64.
        if cloud_init_script is not None:
            if isinstance(cloud_init_script, str) and cloud_init_script and not cloud_init_script.startswith("#!"):
                raise ValueError("cloud_init_script must start with a shebang line (e.g. '#!/bin/bash')")
            raw: bytes = cloud_init_script.encode() if isinstance(cloud_init_script, str) else cloud_init_script
            self.cloud_init_script = base64.b64encode(raw).decode()
        else:
            self.cloud_init_script = None
        # Handle SSH key - either use provided or auto-generate
        self._setup_ssh_keys(ssh_public_key)

        # Add security rules for load balancer and instance pool.
        # Security list rules only apply to a live Vcn — the guard is inside
        # _add_scalable_workload_security_rules (skipped for VcnRef, which is
        # read-only and has no mutable security lists).
        self._add_scalable_workload_security_rules()

        # Finalize the VCN network
        self.vcn.finalize_network()

        # Verify subnets exist after finalization (accessors raise RuntimeError if None)
        self.vcn.get_public_subnet_id()
        self.vcn.get_private_subnet_id()

        # Create resources in order
        self._create_load_balancer()
        self._create_instance_configuration()
        self._create_instance_pool()
        self._create_autoscaling_configuration()

        self.id = self.instance_pool.id

        # Register outputs
        outputs: dict[str, pulumi.Output[str] | str] = {
            "instance_pool_id": self.instance_pool.id,
            "load_balancer_id": self.load_balancer.id,
            "load_balancer_ip": self.get_load_balancer_ip(),
        }

        outputs.update(self._get_ssh_outputs())

        self.register_outputs(outputs)

    def _add_scalable_workload_security_rules(self) -> None:
        """Add security rules for load balancer and instance pool communication.

        The rule set depends on `OciLoadBalancerConfig.is_public`:

        **Public load balancer** (`is_public=True`, default):

        - Public subnet ingress: HTTP (80) and HTTPS (443) from internet
          (`0.0.0.0/0`).  Added via the provider-internal unique accumulator so
          that if an `INTERNET_EDGE` NSG with HTTP/HTTPS is also present the
          rules are deduplicated rather than appearing twice.
        - Public subnet egress: Backend port
          (`OciLoadBalancerConfig.backend_port`) to private subnet CIDR.
        - Private subnet ingress: Backend port from public subnet CIDR
          (load balancer health checks and forwarded traffic).

        **Internal load balancer** (`is_public=False`):

        - Private subnet ingress: HTTP (80) and HTTPS (443) from the VCN
          CIDR block only — no internet exposure.  Since the load balancer
          lives in the private subnet alongside the instance pool, a
          single ingress rule on `backend_port` from the VCN CIDR also
          covers LB-to-backend traffic.

        Egress to OCI services is not added here — the baseline VCN rules
        injected by `Vcn._inject_baseline_rules` already provide
        all-protocol egress to the OCI service CIDR for every private-tier
        subnet.

        **Note:** SSH access to pool instances is not managed here.  Deploy a
        `Bastion` spell alongside this workload to enable time-limited
        SSH via the OCI Bastion Service.

        Must be called before `Vcn.finalize_network`.
        """
        backend_port = self.load_balancer_config.backend_port
        is_public = self.load_balancer_config.is_public

        # Security list rules are only applicable when vcn is a live Vcn —
        # VcnRef is read-only and raises on any non-empty rule list.
        if isinstance(self.vcn, Vcn):
            public_subnet_cidr: pulumi.Input[str] = self.vcn.get_public_subnet_cidr()
            private_subnet_cidr: pulumi.Input[str] = self.vcn.get_private_subnet_cidr()
            vcn_cidr: pulumi.Input[str] = self.vcn.cidr_block

            if is_public:
                # Public subnet ingress rules (Load Balancer) — use fingerprinted calls
                # matching the Nsg INTERNET_EDGE convention so that if an INTERNET_EDGE
                # NSG with HTTP/HTTPS ports is also present in the same VCN, the rules
                # are deduplicated rather than appearing twice in the security list.
                self.vcn.add_unique_security_rules(
                    "public-ingress-tcp-80",
                    SecurityRules(
                        public_ingress=[
                            IngressRule(
                                protocol="tcp",
                                source="0.0.0.0/0",
                                port_min=80,
                                port_max=80,
                                description="HTTP traffic from internet to load balancer",
                            )
                        ],
                    ),
                )
                self.vcn.add_unique_security_rules(
                    "public-ingress-tcp-443",
                    SecurityRules(
                        public_ingress=[
                            IngressRule(
                                protocol="tcp",
                                source="0.0.0.0/0",
                                port_min=443,
                                port_max=443,
                                description="HTTPS traffic from internet to load balancer",
                            )
                        ],
                    ),
                )

                # Workload-specific rules (LB ↔ backend port).  Egress to OCI
                # services is already covered by the baseline VCN rules.
                self.vcn.add_security_rules(
                    SecurityRules(
                        public_egress=[
                            EgressRule(
                                protocol="tcp",
                                destination=private_subnet_cidr,
                                port_min=backend_port,
                                port_max=backend_port,
                                description=(
                                    f"Load balancer forwards traffic to backend instances on port {backend_port}"
                                ),
                            )
                        ],
                        private_ingress=[
                            IngressRule(
                                protocol="tcp",
                                source=public_subnet_cidr,
                                port_min=backend_port,
                                port_max=backend_port,
                                description=f"Traffic from load balancer to application on port {backend_port}",
                            )
                        ],
                    )
                )
            else:
                # Internal LB — HTTP/HTTPS ingress from the VCN CIDR only, applied to
                # the private subnet (where both the LB and backend pool reside).
                self.vcn.add_security_rules(
                    SecurityRules(
                        private_ingress=[
                            IngressRule(
                                protocol="tcp",
                                source=vcn_cidr,
                                port_min=80,
                                port_max=80,
                                description="HTTP traffic from VCN to internal load balancer",
                            ),
                            IngressRule(
                                protocol="tcp",
                                source=vcn_cidr,
                                port_min=443,
                                port_max=443,
                                description="HTTPS traffic from VCN to internal load balancer",
                            ),
                            IngressRule(
                                protocol="tcp",
                                source=vcn_cidr,
                                port_min=backend_port,
                                port_max=backend_port,
                                description=f"Traffic from VCN to application on port {backend_port}",
                            ),
                        ],
                    )
                )

    def _create_load_balancer(self) -> None:
        """Create the OCI Load Balancer, backend set, and HTTP/HTTPS listeners.

        Always creates an HTTP listener on port 80.  When
        `LoadBalancerConfig.ssl_certificate_name` is set, an additional HTTPS
        listener on port 443 is created using that certificate.

        Sets `self.load_balancer`, `self.backend_set`, and `self.listeners`
        on the instance.

        Raises:
            RuntimeError: If `vcn.public_subnet` is `None` after
                `finalize_network()`.
        """
        lb_config = self.load_balancer_config

        # Create load balancer
        lb_name = self.create_resource_name("lb")
        self.load_balancer = oci.loadbalancer.LoadBalancer(
            lb_name,
            compartment_id=self.compartment_id,
            display_name=lb_name,
            shape="flexible",
            shape_details=oci.loadbalancer.LoadBalancerShapeDetailsArgs(
                minimum_bandwidth_in_mbps=lb_config.min_bandwidth_mbps,
                maximum_bandwidth_in_mbps=lb_config.max_bandwidth_mbps,
            ),
            subnet_ids=[self.vcn.get_public_subnet_id() if lb_config.is_public else self.vcn.get_private_subnet_id()],
            is_private=not lb_config.is_public,
            freeform_tags=self.create_freeform_tags(lb_name, "load-balancer"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Create backend set with health check on the backend port
        bs_name = self.create_resource_name("bs")
        self.backend_set = oci.loadbalancer.BackendSet(
            bs_name,
            load_balancer_id=self.load_balancer.id,
            name=bs_name,
            policy="ROUND_ROBIN",
            health_checker=oci.loadbalancer.BackendSetHealthCheckerArgs(
                protocol="HTTP",
                port=lb_config.backend_port,
                url_path=lb_config.health_check_path,
                interval_ms=10000,
                timeout_in_millis=3000,
                retries=3,
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Always create HTTP listener on port 80
        http_listener_name = self.create_resource_name("listener-http")
        self.listeners.append(
            oci.loadbalancer.Listener(
                http_listener_name,
                load_balancer_id=self.load_balancer.id,
                name=http_listener_name,
                default_backend_set_name=self.backend_set.name,
                port=80,
                protocol="HTTP",
                opts=pulumi.ResourceOptions(parent=self),
            )
        )

        # Optionally create HTTPS listener on port 443
        if lb_config.ssl_certificate_name:
            https_listener_name = self.create_resource_name("listener-https")
            self.listeners.append(
                oci.loadbalancer.Listener(
                    https_listener_name,
                    load_balancer_id=self.load_balancer.id,
                    name=https_listener_name,
                    default_backend_set_name=self.backend_set.name,
                    port=443,
                    protocol="HTTPS",
                    ssl_configuration=oci.loadbalancer.ListenerSslConfigurationArgs(
                        certificate_name=lb_config.ssl_certificate_name,
                        verify_peer_certificate=True,
                    ),
                    opts=pulumi.ResourceOptions(parent=self),
                )
            )

    def _create_instance_configuration(self) -> None:
        """Create the OCI Instance Configuration as a launch template for the pool.

        The configuration captures the shape, image, SSH key, cloud-init user
        data, and private-subnet placement so that the instance pool can
        provision identical VMs automatically.

        Sets `self.instance_configuration` on the instance.

        Raises:
            RuntimeError: If `vcn.private_subnet` is `None` after
                `finalize_network()`.
        """
        ic_name = self.create_resource_name("ic")

        # Build metadata
        metadata: dict[str, str] = {
            "ssh_authorized_keys": self.ssh_public_key,
        }
        if self.cloud_init_script:
            metadata["user_data"] = self.cloud_init_script

        self.instance_configuration = oci.core.InstanceConfiguration(
            ic_name,
            compartment_id=self.compartment_id,
            display_name=ic_name,
            instance_details=oci.core.InstanceConfigurationInstanceDetailsArgs(
                instance_type="compute",
                launch_details=oci.core.InstanceConfigurationInstanceDetailsLaunchDetailsArgs(
                    compartment_id=self.compartment_id,
                    shape=self.shape,
                    shape_config=oci.core.InstanceConfigurationInstanceDetailsLaunchDetailsShapeConfigArgs(
                        ocpus=self.ocpus,
                        memory_in_gbs=self.memory_in_gbs,
                    ),
                    source_details=oci.core.InstanceConfigurationInstanceDetailsLaunchDetailsSourceDetailsArgs(
                        source_type="image",
                        image_id=self.image_id,
                        boot_volume_size_in_gbs=str(self.boot_volume_size_in_gbs),
                    ),
                    create_vnic_details=oci.core.InstanceConfigurationInstanceDetailsLaunchDetailsCreateVnicDetailsArgs(
                        assign_public_ip=False,
                        subnet_id=self.vcn.get_private_subnet_id(),
                    ),
                    metadata=metadata,
                ),
            ),
            freeform_tags=self.create_freeform_tags(ic_name, "instance-configuration"),
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_instance_pool(self) -> None:
        """Create the OCI Instance Pool and attach it to the load balancer backend set.

        Spreads instances across all availability domains in the region.  The
        pool size starts at `initial_instances` and is managed by the
        autoscaling configuration between `min_instances` and `max_instances`.

        Sets `self.instance_pool` on the instance.

        Raises:
            RuntimeError: If `vcn.private_subnet` is `None` after
                `finalize_network()`.
        """
        pool_name = self.create_resource_name("pool")

        private_subnet_id = self.vcn.get_private_subnet_id()

        # Build placement configurations for all ADs using the async Output so
        # the blocking get_availability_domains() call is never made at __init__
        # time.  pulumi.Output.all ensures both the AD list and subnet ID are
        # fully resolved before the list comprehension runs.
        ads_output = oci.identity.get_availability_domains_output(compartment_id=self.compartment_id)
        placement_configs = pulumi.Output.all(
            ads_output.availability_domains,
            private_subnet_id,
        ).apply(
            lambda args: [
                oci.core.InstancePoolPlacementConfigurationArgs(
                    availability_domain=str(getattr(ad, "name", None) or ad.get("name")),
                    primary_subnet_id=args[1],
                )
                for ad in args[0]
            ]
        )

        self.instance_pool = oci.core.InstancePool(
            pool_name,
            compartment_id=self.compartment_id,
            display_name=pool_name,
            instance_configuration_id=self.instance_configuration.id,
            size=self.initial_instances,
            placement_configurations=placement_configs,
            load_balancers=[
                oci.core.InstancePoolLoadBalancerArgs(
                    backend_set_name=self.backend_set.name,
                    load_balancer_id=self.load_balancer.id,
                    port=self.load_balancer_config.backend_port,
                    vnic_selection="PrimaryVnic",
                ),
            ],
            freeform_tags=self.create_freeform_tags(pool_name, "instance-pool"),
            # OCI rejects pool attachment when the backend set or listeners are
            # not yet live; pin ordering explicitly.
            opts=pulumi.ResourceOptions(
                parent=self,
                depends_on=[self.backend_set, *self.listeners],
            ),
        )

    def _create_autoscaling_configuration(self) -> None:
        """Dispatch to the appropriate autoscaling factory based on *scaling_policy*.

        Delegates to `_create_metric_autoscaling` or
        `_create_schedule_autoscaling`.  Does nothing when `scaling_policy`
        is `None`.

        Sets `self.autoscaling_configuration` on the instance (or leaves it
        `None` if autoscaling is disabled).
        """
        if self.scaling_policy is None:
            return

        asc_name = self.create_resource_name("asc")

        if isinstance(self.scaling_policy, MetricScalingPolicy):
            self._create_metric_autoscaling(asc_name)
        else:
            self._create_schedule_autoscaling(asc_name)

    def _create_metric_autoscaling(self, asc_name: str) -> None:
        """Create a threshold-based autoscaling configuration for the instance pool.

        Configures two rules against the metric specified in
        `MetricScalingPolicy.metric`:

        - **Scale out**: fires when the metric exceeds
          `MetricScalingPolicy.scale_out_threshold` (`GT` operator)
          and adds `MetricScalingPolicy.scale_out_value` instances.
        - **Scale in**: fires when the metric falls below
          `MetricScalingPolicy.scale_in_threshold` (`LT` operator)
          and removes `abs(scale_in_value)` instances.

        Args:
            asc_name: Fully-qualified OCI resource name for the autoscaling
                configuration (created by `BaseResource.create_resource_name`).

        Raises:
            RuntimeError: If `scaling_policy` is not a `MetricScalingPolicy`.
                This should never occur in practice because the caller
                `_create_autoscaling_configuration` performs an `isinstance`
                check before dispatching here.
        """
        if not isinstance(self.scaling_policy, MetricScalingPolicy):
            raise RuntimeError(
                f"_create_metric_autoscaling called with wrong policy type: {type(self.scaling_policy)!r}"
            )
        policy = self.scaling_policy

        self.autoscaling_configuration = oci.autoscaling.AutoScalingConfiguration(
            asc_name,
            compartment_id=self.compartment_id,
            display_name=asc_name,
            auto_scaling_resources=oci.autoscaling.AutoScalingConfigurationAutoScalingResourcesArgs(
                id=self.instance_pool.id,
                type="instancePool",
            ),
            cool_down_in_seconds=policy.cooldown_in_seconds,
            is_enabled=True,
            policies=[
                oci.autoscaling.AutoScalingConfigurationPolicyArgs(
                    display_name=f"{asc_name}-policy",
                    policy_type="threshold",
                    capacity=oci.autoscaling.AutoScalingConfigurationPolicyCapacityArgs(
                        initial=self.initial_instances,
                        max=self.max_instances,
                        min=self.min_instances,
                    ),
                    rules=[
                        # Scale out rule
                        oci.autoscaling.AutoScalingConfigurationPolicyRuleArgs(
                            action=oci.autoscaling.AutoScalingConfigurationPolicyRuleActionArgs(
                                type="CHANGE_COUNT_BY",
                                value=policy.scale_out_value,
                            ),
                            display_name="Scale Out",
                            metric=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricArgs(
                                metric_type=policy.metric.value,
                                threshold=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricThresholdArgs(
                                    operator="GT",
                                    value=policy.scale_out_threshold,
                                ),
                            ),
                        ),
                        # Scale in rule
                        oci.autoscaling.AutoScalingConfigurationPolicyRuleArgs(
                            action=oci.autoscaling.AutoScalingConfigurationPolicyRuleActionArgs(
                                type="CHANGE_COUNT_BY",
                                value=policy.scale_in_value,
                            ),
                            display_name="Scale In",
                            metric=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricArgs(
                                metric_type=policy.metric.value,
                                threshold=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricThresholdArgs(
                                    operator="LT",
                                    value=policy.scale_in_threshold,
                                ),
                            ),
                        ),
                    ],
                ),
            ],
            freeform_tags=self.create_freeform_tags(asc_name, "autoscaling-configuration"),
            opts=pulumi.ResourceOptions(parent=self, delete_before_replace=True),
        )

    def _create_schedule_autoscaling(self, asc_name: str) -> None:
        """Create a cron-schedule-based autoscaling configuration for the instance pool.

        Creates a single `oci.autoscaling.AutoScalingConfiguration` whose
        `policies` list contains one policy per `ScheduleEntry` in
        `ScheduleScalingPolicy.schedules`.  Each policy uses a Quartz cron
        expression in UTC and adjusts instance pool capacity according to the
        `ScheduleEntry.action` (`CHANGE_COUNT_BY` or `CHANGE_COUNT_TO`) and
        `ScheduleEntry.value`.

        OCI scheduled autoscaling for instance pools uses `policy_type="scheduled"`
        with `execution_schedule` (cron) and `capacity` (min/max/initial).  The
        `resource_action` field is for power-management actions and must not be
        used for scaling policies — it would deploy an instance power on/off
        action instead of a capacity change.

        Args:
            asc_name: Fully-qualified OCI resource name for the autoscaling
                configuration (created by `BaseResource.create_resource_name`).

        Raises:
            RuntimeError: If `scaling_policy` is not a `ScheduleScalingPolicy`.
                This should never occur in practice because the caller
                `_create_autoscaling_configuration` performs an `isinstance`
                check before dispatching here.
        """
        if not isinstance(self.scaling_policy, ScheduleScalingPolicy):
            raise RuntimeError(
                f"_create_schedule_autoscaling called with wrong policy type: {type(self.scaling_policy)!r}"
            )
        policy = self.scaling_policy

        # Build one scheduled policy per ScheduleEntry.
        # Each entry drives a capacity change via execution_schedule + capacity;
        # CHANGE_COUNT_TO sets capacity directly, CHANGE_COUNT_BY adjusts relative
        # to the current pool size using min/max as guard rails.
        policies = []
        for entry in policy.schedules:
            if entry.action.value == "CHANGE_COUNT_TO":
                target = entry.value
                new_min = min(entry.value, self.min_instances)
                new_max = max(entry.value, self.max_instances)
            else:
                # CHANGE_COUNT_BY: clamp delta within [min_instances, max_instances]
                target = max(self.min_instances, min(self.max_instances, self.initial_instances + entry.value))
                new_min = self.min_instances
                new_max = self.max_instances

            policies.append(
                oci.autoscaling.AutoScalingConfigurationPolicyArgs(
                    display_name=entry.display_name,
                    policy_type="scheduled",
                    capacity=oci.autoscaling.AutoScalingConfigurationPolicyCapacityArgs(
                        initial=target,
                        min=new_min,
                        max=new_max,
                    ),
                    execution_schedule=oci.autoscaling.AutoScalingConfigurationPolicyExecutionScheduleArgs(
                        expression=entry.cron_expression,
                        timezone="UTC",
                        type="cron",
                    ),
                ),
            )

        self.autoscaling_configuration = oci.autoscaling.AutoScalingConfiguration(
            asc_name,
            compartment_id=self.compartment_id,
            display_name=asc_name,
            auto_scaling_resources=oci.autoscaling.AutoScalingConfigurationAutoScalingResourcesArgs(
                id=self.instance_pool.id,
                type="instancePool",
            ),
            is_enabled=True,
            policies=policies,
            freeform_tags=self.create_freeform_tags(asc_name, "autoscaling-configuration"),
            opts=pulumi.ResourceOptions(parent=self, delete_before_replace=True),
        )

    def export(self) -> None:
        """Export standard scalable workload stack outputs.

        Publishes load balancer IP, load balancer OCID, and instance pool
        OCID under keys derived from the spell's logical name.  The SSH
        private key is exported as a Pulumi secret only when it was
        auto-generated.

        Example:
            ```python
            pool = ScalableWorkload(name="web-pool", ...)
            pool.export()
            # Exports: web_pool_lb_ip, web_pool_lb_id, web_pool_pool_id,
            #          and conditionally web_pool_ssh_private_key (secret)
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_lb_ip", self.get_load_balancer_ip())
        pulumi.export(f"{prefix}_lb_id", self.get_load_balancer_id())
        pulumi.export(f"{prefix}_pool_id", self.get_instance_pool_id())
        if self.auto_generated_keys and self.ssh_private_key:
            pulumi.export(f"{prefix}_ssh_private_key", pulumi.Output.secret(self.ssh_private_key))

    def get_load_balancer_ip(self) -> pulumi.Output[str]:
        """Return the public IP address of the load balancer.

        Resolves the first entry in the load balancer's `ip_address_details`
        list, which is the public VIP when `LoadBalancerConfig.is_public`
        is `True`.

        Returns:
            `pulumi.Output[str]` resolving to the IP address string, or an
            empty string if the load balancer has no IP details yet.
        """
        return self.load_balancer.ip_address_details.apply(
            lambda details: (details[0].ip_address or "") if details else ""
        )

    def get_instance_pool_id(self) -> pulumi.Output[str]:
        """Return the OCID of the instance pool.

        Returns:
            `pulumi.Output[str]` resolving to the instance pool OCID.
        """
        return self.instance_pool.id

    def get_load_balancer_id(self) -> pulumi.Output[str]:
        """Return the OCID of the load balancer.

        Returns:
            `pulumi.Output[str]` resolving to the load balancer OCID.
        """
        return self.load_balancer.id


__all__ = [
    "MetricScalingPolicy",
    "OciLoadBalancerConfig",
    "ScalableWorkload",
    "ScalingAction",
    "ScalingMetric",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
