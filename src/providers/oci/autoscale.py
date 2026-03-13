"""Scalable Workload building block for OCIBlocks.

Provides :class:`ScalableWorkload`, which creates a complete horizontally-scalable
OCI compute tier with load balancing and autoscaling:

* **OCI Load Balancer** (flexible shape) in the VCN's public subnet with HTTP
  and optional HTTPS listeners.
* **Instance Configuration** as a launch template for pool instances.
* **Instance Pool** in the VCN's private subnet, spread across all
  availability domains.
* **Autoscaling Configuration** – metric-based (CPU/memory) or schedule-based
  (cron expressions).

Supporting configuration dataclasses
-------------------------------------
:class:`LoadBalancerConfig`
    Customise LB port, health check path, bandwidth, and SSL.

:class:`MetricScalingPolicy`
    Scale in/out based on CPU or memory utilisation thresholds.

:class:`ScheduleScalingPolicy`
    Scale in/out on a Quartz cron schedule (e.g. business hours).

:class:`ScheduleEntry`
    A single cron-schedule scaling action.

:class:`ScalingMetric`
    Enum of available metric types.

:class:`ScalingAction`
    Enum of available scaling action types.
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from core.abstractions.autoscale import (
    AbstractScalableWorkload,
    ScalingMetric,
    ScalingAction,
    MetricScalingPolicy,
    ScheduleEntry,
    ScheduleScalingPolicy,
    LoadBalancerConfig as _BaseLoadBalancerConfig,
)
from providers.oci.network import Vcn, VcnRef
from providers.oci.helper import OciHelper
from dataclasses import dataclass

# Sentinel to distinguish "not provided" from explicitly passing None
_UNSET: object = object()


@dataclass
class OciLoadBalancerConfig(_BaseLoadBalancerConfig):
    """OCI-specific load balancer configuration extending the cloud-neutral base.

    Adds OCI flexible-shape bandwidth parameters to the base
    :class:`~core.abstractions.autoscale.LoadBalancerConfig`.

    Attributes:
        backend_port: Port on backend instances to receive traffic and health checks.
        health_check_path: URL path for HTTP health checks.
        is_public: Whether the load balancer has a public IP.
        min_bandwidth_mbps: Minimum bandwidth for the OCI flexible LB shape.
            Default: ``10``.
        max_bandwidth_mbps: Maximum bandwidth for the OCI flexible LB shape.
            Default: ``100``.
        ssl_certificate_name: SSL certificate name for HTTPS.  If set, creates
            an HTTPS listener on port 443 in addition to HTTP on port 80.
    """

    min_bandwidth_mbps: int = 10
    max_bandwidth_mbps: int = 100


# Alias so existing callers using ``LoadBalancerConfig(min_bandwidth_mbps=...)``
# continue to work without modification.
LoadBalancerConfig = OciLoadBalancerConfig


class ScalableWorkload(BaseResource, AbstractScalableWorkload):
    """OCI Scalable Workload with load balancer, instance pool, and autoscaling.

    Creates a complete horizontally-scalable compute tier following OCI best
    practices:

    * OCI Load Balancer (flexible shape) in the VCN **public** subnet —
      internet-facing, with HTTP and optional HTTPS listeners.
    * Instance Configuration as the launch template for pool VMs.
    * Instance Pool in the VCN **private** subnet, spread across all
      availability domains.
    * Autoscaling Configuration — metric-based (CPU/memory thresholds) or
      schedule-based (Quartz cron).  Pass ``None`` to disable autoscaling.

    Security rules are added automatically to the VCN via
    :meth:`~blocks.vcn.network.Vcn.add_security_list_rules` before
    :meth:`~blocks.vcn.network.Vcn.finalize_network` is called.

    Attributes:
        vcn: The :class:`~blocks.vcn.network.Vcn` or
            :class:`~blocks.vcn.network.VcnRef` this workload is deployed into.
        shape: Compute shape for instance pool VMs
            (e.g. ``"VM.Standard.E4.Flex"``).
        ocpus: Number of OCPUs per instance.
        memory_in_gbs: RAM in GiB per instance.
        ssh_public_key: OpenSSH public key installed on instances.
        ssh_private_key: Corresponding private key, or ``None`` when the caller
            supplied their own public key.
        image_id: OCID of the boot image resolved for the pool instances.
        user_data: Base64-encoded cloud-init user data string, or ``None``.
        min_instances: Minimum (floor) number of instances for autoscaling.
        max_instances: Maximum (ceiling) number of instances for autoscaling.
        initial_instances: Instance count when the pool is first created.
        load_balancer_config: :class:`LoadBalancerConfig` in use.
        scaling_policy: :class:`MetricScalingPolicy`,
            :class:`ScheduleScalingPolicy`, or ``None``.
        auto_generated_keys: ``True`` when SSH keys were auto-generated.
        load_balancer: The ``oci.loadbalancer.LoadBalancer`` resource.
        backend_set: The ``oci.loadbalancer.BackendSet`` resource.
        listeners: List of ``oci.loadbalancer.Listener`` resources (HTTP,
            and optionally HTTPS).
        instance_configuration: The ``oci.core.InstanceConfiguration``
            resource used as the pool launch template.
        instance_pool: The ``oci.core.InstancePool`` resource.
        autoscaling_configuration: The
            ``oci.autoscaling.AutoScalingConfiguration`` resource, or
            ``None`` when autoscaling is disabled.
        id: ``pulumi.Output[str]`` of the instance pool OCID.

    Example::

        vcn = Vcn(name="app", compartment_id=comp_id, cidr_block="10.0.0.0/16")

        pool = ScalableWorkload(
            name="web",
            compartment_id=comp_id,
            vcn=vcn,
            min_instances=2,
            max_instances=10,
            load_balancer_config=LoadBalancerConfig(backend_port=8080),
            scaling_policy=MetricScalingPolicy(scale_out_threshold=70),
        )

        pulumi.export("lb_ip", pool.get_load_balancer_ip())
    """

    vcn: Vcn | VcnRef
    shape: pulumi.Input[str]
    ocpus: pulumi.Input[float]
    memory_in_gbs: pulumi.Input[float]
    ssh_public_key: str
    ssh_private_key: str | None
    image_id: pulumi.Input[str] | None
    user_data: str | None
    min_instances: int
    max_instances: int
    initial_instances: int
    load_balancer_config: LoadBalancerConfig
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
        stack_name: str | None = None,
        # Instance configuration
        shape: pulumi.Input[str] = "VM.Standard.E4.Flex",
        ocpus: pulumi.Input[float] = 1,
        memory_in_gbs: pulumi.Input[float] = 16,
        image_id: pulumi.Input[str] | None = None,
        ssh_public_key: pulumi.Input[str] | None = None,
        user_data: str | None = None,
        boot_volume_size_in_gbs: pulumi.Input[int] = 50,
        # Pool configuration
        min_instances: int = 1,
        max_instances: int = 5,
        initial_instances: int | None = None,
        # Load balancer configuration
        load_balancer_config: LoadBalancerConfig | None = None,
        # Scaling policy (metric OR schedule, not both); pass None to disable autoscaling
        scaling_policy: MetricScalingPolicy | ScheduleScalingPolicy | None = _UNSET,  # type: ignore[assignment]
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a scalable workload with load balancer, instance pool, and autoscaling.

        Args:
            name: Logical name for the workload (e.g. ``"web"``).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: :class:`~blocks.vcn.Vcn` or :class:`~blocks.vcn.VcnRef`
                providing the 4-tier network.  The load balancer is placed in
                the public subnet and the instance pool in the private subnet.
            stack_name: Pulumi stack name.  Defaults to
                ``pulumi.get_stack()`` when ``None``.
            shape: OCI compute shape for instance pool VMs
                (default: ``"VM.Standard.E4.Flex"``).
            ocpus: Number of OCPUs per instance (default: ``1``).
            memory_in_gbs: RAM in GiB per instance (default: ``16``).
            image_id: Explicit boot image OCID.  When ``None``, the latest
                Oracle Linux 8 image compatible with *shape* is resolved
                automatically.
            ssh_public_key: OpenSSH public key to install on instances.
                When ``None`` or empty, a key pair is auto-generated and
                exported as Pulumi secrets.
            user_data: Cloud-init user data script, **base64-encoded**.
                Passed to instances via OCI instance metadata.
            boot_volume_size_in_gbs: Boot volume size in GiB (default:
                ``50``).
            min_instances: Minimum number of instances in the pool
                (default: ``1``).
            max_instances: Maximum number of instances the autoscaler may
                create (default: ``5``).
            initial_instances: Initial instance count when the pool is first
                created.  Defaults to *min_instances*.
            load_balancer_config: :class:`LoadBalancerConfig` dataclass.
                Defaults to ``LoadBalancerConfig()`` (port 80, health check
                ``/health``, 10-100 Mbps, public).
            scaling_policy: Autoscaling policy.  Pass a
                :class:`MetricScalingPolicy` (CPU/memory threshold),
                a :class:`ScheduleScalingPolicy` (cron-based), or ``None``
                to disable autoscaling entirely.  When omitted, defaults to
                ``MetricScalingPolicy()`` (80 % CPU scale-out).
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:compute:ScalableWorkload", name, compartment_id, stack_name, opts)

        self.name = name
        self.vcn = vcn
        self.compartment_id = compartment_id
        self.shape = shape
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs
        self.image_id = image_id
        self.user_data = user_data
        self.boot_volume_size_in_gbs = boot_volume_size_in_gbs
        self.min_instances = min_instances
        self.max_instances = max_instances
        self.initial_instances = initial_instances if initial_instances is not None else min_instances
        self.load_balancer_config = load_balancer_config or LoadBalancerConfig()
        self.scaling_policy = MetricScalingPolicy() if scaling_policy is _UNSET else scaling_policy
        self.listeners = []
        self.autoscaling_configuration = None

        # Handle SSH key - either use provided or auto-generate
        self._setup_ssh_keys(ssh_public_key)

        # Add security rules for load balancer and instance pool
        self._add_scalable_workload_security_rules()

        # Finalize the VCN network
        self.vcn.finalize_network()

        # Verify subnets exist after finalization
        assert self.vcn.public_subnet is not None, "VCN public subnet must exist after finalization"
        assert self.vcn.private_subnet is not None, "VCN private subnet must exist after finalization"

        # Get the latest Oracle Linux 8 image if no custom image specified
        resolved_image_id = str(image_id) if image_id is not None else None
        self.image_id = OciHelper().resolve_image_id(str(compartment_id), str(shape), resolved_image_id)

        # Get availability domains
        ads = oci.identity.get_availability_domains(compartment_id=str(compartment_id))
        self.availability_domains = ads.availability_domains

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
        }

        outputs.update(self._get_ssh_outputs())

        self.register_outputs(outputs)

    def _add_scalable_workload_security_rules(self) -> None:
        """Add security rules for load balancer and instance pool communication.

        Calls :meth:`~blocks.vcn.network.Vcn.add_security_list_rules` with:

        *Public subnet (Load Balancer)*:

        * Ingress: HTTP (80) and HTTPS (443) from internet (``0.0.0.0/0``).
        * Egress: Backend port (``LoadBalancerConfig.backend_port``) to
          private subnet CIDR.

        *Private subnet (Instance Pool)*:

        * Ingress: Backend port from public subnet CIDR (load balancer
          health checks and forwarded traffic).
        * Egress: HTTPS (443) to OCI service CIDR block (monitoring,
          telemetry, software updates).

        Note:
            SSH access to pool instances is not managed here.  Deploy a
            :class:`~blocks.compute.bastion.Bastion` block alongside this
            workload to enable time-limited SSH via the OCI Bastion Service.

            Must be called before :meth:`~blocks.vcn.network.Vcn.finalize_network`.
        """
        public_subnet_cidr: pulumi.Input[str] = self.vcn.get_public_subnet_cidr()
        private_subnet_cidr: pulumi.Input[str] = self.vcn.get_private_subnet_cidr()
        backend_port = self.load_balancer_config.backend_port

        # Public subnet ingress rules (Load Balancer)
        public_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="HTTP traffic from internet to load balancer",
                protocol="6",  # TCP
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=80,
                    max=80,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="HTTPS traffic from internet to load balancer",
                protocol="6",  # TCP
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=443,
                    max=443,
                ),
            ),
        ]

        # Public subnet egress rules (Load Balancer to backend instances)
        public_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            oci.core.SecurityListEgressSecurityRuleArgs(
                description=f"Load balancer forwards traffic to backend instances on port {backend_port}",
                protocol="6",  # TCP
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=backend_port,
                    max=backend_port,
                ),
            ),
        ]

        # Private subnet ingress rules (Instance Pool)
        private_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            oci.core.SecurityListIngressSecurityRuleArgs(
                description=f"Traffic from load balancer to application on port {backend_port}",
                protocol="6",  # TCP
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=backend_port,
                    max=backend_port,
                ),
            ),
        ]

        # Private subnet egress rules (Instance Pool to OCI services)
        private_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Instances access OCI services for monitoring, telemetry, and updates",
                protocol="6",  # TCP
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=443,
                    max=443,
                ),
            ),
        ]

        # Add rules to VCN security lists
        self.vcn.add_security_list_rules(
            public_ingress=public_ingress_rules,
            public_egress=public_egress_rules,
            private_ingress=private_ingress_rules,
            private_egress=private_egress_rules,
        )

    def _create_load_balancer(self) -> None:
        """Create the OCI Load Balancer, backend set, and HTTP/HTTPS listeners.

        Always creates an HTTP listener on port 80.  When
        :attr:`LoadBalancerConfig.ssl_certificate_name` is set, an additional
        HTTPS listener on port 443 is created using that certificate.

        Sets ``self.load_balancer``, ``self.backend_set``, and
        ``self.listeners`` on the instance.
        """
        lb_config = self.load_balancer_config

        assert self.vcn.public_subnet is not None

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
            subnet_ids=[self.vcn.public_subnet.id],
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
                        verify_peer_certificate=False,
                    ),
                    opts=pulumi.ResourceOptions(parent=self),
                )
            )

    def _create_instance_configuration(self) -> None:
        """Create the OCI Instance Configuration as a launch template for the pool.

        The configuration captures the shape, image, SSH key, cloud-init user
        data, and private-subnet placement so that the instance pool can
        provision identical VMs automatically.

        Sets ``self.instance_configuration`` on the instance.
        """
        ic_name = self.create_resource_name("ic")

        # Subnets are guaranteed to exist after finalize_network()
        assert self.vcn.private_subnet is not None

        # Build metadata
        metadata: dict[str, str] = {
            "ssh_authorized_keys": self.ssh_public_key,
        }
        if self.user_data:
            metadata["user_data"] = self.user_data

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
                        subnet_id=self.vcn.private_subnet.id,
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
        pool size starts at :attr:`initial_instances` and is managed by the
        autoscaling configuration between :attr:`min_instances` and
        :attr:`max_instances`.

        Sets ``self.instance_pool`` on the instance.
        """
        pool_name = self.create_resource_name("pool")

        # Subnets are guaranteed to exist after finalize_network()
        assert self.vcn.private_subnet is not None

        # Build placement configurations for all ADs
        placement_configs = [
            oci.core.InstancePoolPlacementConfigurationArgs(
                availability_domain=ad.name,
                primary_subnet_id=self.vcn.private_subnet.id,
            )
            for ad in self.availability_domains
        ]

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
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_autoscaling_configuration(self) -> None:
        """Dispatch to the appropriate autoscaling factory based on *scaling_policy*.

        Delegates to :meth:`_create_metric_autoscaling` or
        :meth:`_create_schedule_autoscaling`.  Does nothing when
        :attr:`scaling_policy` is ``None``.

        Sets ``self.autoscaling_configuration`` on the instance (or leaves it
        ``None`` if autoscaling is disabled).
        """
        if self.scaling_policy is None:
            return

        asc_name = self.create_resource_name("asc")

        if isinstance(self.scaling_policy, MetricScalingPolicy):
            self._create_metric_autoscaling(asc_name)
        elif isinstance(self.scaling_policy, ScheduleScalingPolicy):
            self._create_schedule_autoscaling(asc_name)

    def _create_metric_autoscaling(self, asc_name: str) -> None:
        """Create a threshold-based autoscaling configuration for the instance pool.

        Configures two rules against the metric specified in
        :attr:`MetricScalingPolicy.metric`:

        * **Scale out**: fires when the metric exceeds
          :attr:`~MetricScalingPolicy.scale_out_threshold` (``GT`` operator)
          and adds :attr:`~MetricScalingPolicy.scale_out_value` instances.
        * **Scale in**: fires when the metric falls below
          :attr:`~MetricScalingPolicy.scale_in_threshold` (``LT`` operator)
          and removes ``abs(scale_in_value)`` instances.

        Args:
            asc_name: Fully-qualified OCI resource name for the autoscaling
                configuration (created by
                :meth:`~core.base.BaseResource.create_resource_name`).
        """
        policy = self.scaling_policy
        assert isinstance(policy, MetricScalingPolicy)

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
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_schedule_autoscaling(self, asc_name: str) -> None:
        """Create a cron-schedule-based autoscaling configuration for the instance pool.

        One OCI autoscaling policy is created per :class:`ScheduleEntry` in
        :attr:`ScheduleScalingPolicy.schedules`.  Each policy uses a Quartz
        cron expression in UTC and performs a
        :attr:`~ScheduleEntry.action` of either ``CHANGE_COUNT_BY`` or
        ``CHANGE_COUNT_TO``.

        Args:
            asc_name: Fully-qualified OCI resource name for the autoscaling
                configuration (created by
                :meth:`~core.base.BaseResource.create_resource_name`).
        """
        policy = self.scaling_policy
        assert isinstance(policy, ScheduleScalingPolicy)

        # For schedule-based policies, we create one policy per schedule entry
        policies = []
        for entry in policy.schedules:
            policies.append(
                oci.autoscaling.AutoScalingConfigurationPolicyArgs(
                    display_name=entry.display_name,
                    policy_type="scheduled",
                    capacity=oci.autoscaling.AutoScalingConfigurationPolicyCapacityArgs(
                        initial=self.initial_instances,
                        max=self.max_instances,
                        min=self.min_instances,
                    ),
                    execution_schedule=oci.autoscaling.AutoScalingConfigurationPolicyExecutionScheduleArgs(
                        expression=entry.cron_expression,
                        timezone="UTC",
                        type="cron",
                    ),
                    resource_action=oci.autoscaling.AutoScalingConfigurationPolicyResourceActionArgs(
                        action=entry.action.value,
                        action_type="power",
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
            opts=pulumi.ResourceOptions(parent=self),
        )

    def export(self) -> None:
        """Export standard scalable workload stack outputs.

        Publishes load balancer IP, load balancer OCID, and instance pool
        OCID under keys derived from the block's logical name.  The SSH
        private key is exported as a Pulumi secret only when it was
        auto-generated.

        Example::

            pool = ScalableWorkload(name="web-pool", ...)
            pool.export()
            # Exports: web_pool_lb_ip, web_pool_lb_id, web_pool_pool_id,
            #          and conditionally web_pool_ssh_private_key (secret)
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_lb_ip", self.get_load_balancer_ip())
        pulumi.export(f"{prefix}_lb_id", self.get_load_balancer_id())
        pulumi.export(f"{prefix}_pool_id", self.get_instance_pool_id())
        if self.auto_generated_keys and self.ssh_private_key:
            pulumi.export(f"{prefix}_ssh_private_key", pulumi.Output.secret(self.ssh_private_key))

    def get_load_balancer_ip(self) -> pulumi.Output[str]:
        """Return the public IP address of the load balancer.

        Resolves the first entry in the load balancer's ``ip_address_details``
        list, which is the public VIP when :attr:`LoadBalancerConfig.is_public`
        is ``True``.

        Returns:
            ``pulumi.Output[str]`` resolving to the IP address string, or an
            empty string if the load balancer has no IP details yet.
        """
        return self.load_balancer.ip_address_details.apply(
            lambda details: details[0].ip_address or "" if details else ""
        )

    def get_instance_pool_id(self) -> pulumi.Output[str]:
        """Return the OCID of the instance pool.

        Returns:
            ``pulumi.Output[str]`` resolving to the instance pool OCID.
        """
        return self.instance_pool.id

    def get_load_balancer_id(self) -> pulumi.Output[str]:
        """Return the OCID of the load balancer.

        Returns:
            ``pulumi.Output[str]`` resolving to the load balancer OCID.
        """
        return self.load_balancer.id

    def get_ssh_public_key(self) -> str:
        """Return the SSH public key installed on pool instances.

        Returns:
            OpenSSH public key string (auto-generated or caller-supplied).
        """
        return self.ssh_public_key

    def get_ssh_private_key(self) -> str | None:
        """Return the SSH private key if it was auto-generated.

        Returns:
            PEM-encoded private key string when keys were auto-generated,
            or ``None`` when the caller supplied their own public key.
        """
        return self.ssh_private_key


__all__ = [
    "ScalableWorkload",
    "OciLoadBalancerConfig",
    "LoadBalancerConfig",
    "ScalingMetric",
    "ScalingAction",
    "MetricScalingPolicy",
    "ScheduleEntry",
    "ScheduleScalingPolicy",
]
