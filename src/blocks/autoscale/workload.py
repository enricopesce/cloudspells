from __future__ import annotations

import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from blocks.vcn.network import Vcn
from typing import Literal
from dataclasses import dataclass, field
from enum import Enum
import subprocess
import os
import tempfile


class ScalingMetric(Enum):
    """Metrics available for autoscaling policies."""

    CPU_UTILIZATION = "CPU_UTILIZATION"
    MEMORY_UTILIZATION = "MEMORY_UTILIZATION"


class ScalingAction(Enum):
    """Actions for scheduled scaling policies."""

    CHANGE_COUNT_BY = "CHANGE_COUNT_BY"
    CHANGE_COUNT_TO = "CHANGE_COUNT_TO"


@dataclass
class MetricThreshold:
    """Configuration for metric-based scaling thresholds.

    Attributes:
        metric: The metric to monitor (CPU or memory utilization).
        scale_out_threshold: Percentage threshold to trigger scale out (add instances).
        scale_in_threshold: Percentage threshold to trigger scale in (remove instances).
        scale_out_value: Number of instances to add when scaling out.
        scale_in_value: Number of instances to remove when scaling in (negative value).
    """

    metric: ScalingMetric = ScalingMetric.CPU_UTILIZATION
    scale_out_threshold: int = 80
    scale_in_threshold: int = 20
    scale_out_value: int = 1
    scale_in_value: int = -1


@dataclass
class MetricScalingPolicy:
    """Metric-based autoscaling policy configuration.

    Attributes:
        threshold: The metric threshold configuration.
        cooldown_in_seconds: Time to wait between scaling actions (300-3600 seconds).
    """

    threshold: MetricThreshold = field(default_factory=MetricThreshold)
    cooldown_in_seconds: int = 300


@dataclass
class ScheduleEntry:
    """A single scheduled scaling action.

    Attributes:
        cron_expression: Quartz cron format expression in UTC.
        action: Whether to change count by or to a specific value.
        value: The value for the scaling action.
        display_name: Human-readable name for this schedule entry.
    """

    cron_expression: str
    action: ScalingAction
    value: int
    display_name: str


@dataclass
class ScheduleScalingPolicy:
    """Schedule-based autoscaling policy configuration.

    Attributes:
        schedules: List of scheduled scaling entries (max 50).
    """

    schedules: list[ScheduleEntry] = field(default_factory=list)


@dataclass
class HealthCheckConfig:
    """Health check configuration for load balancer backend set.

    Attributes:
        protocol: Health check protocol (HTTP or TCP).
        port: Port to use for health checks.
        url_path: URL path for HTTP health checks.
        interval_ms: Time between health checks in milliseconds.
        timeout_in_millis: Timeout for health check response in milliseconds.
        retries: Number of retries before marking unhealthy.
    """

    protocol: Literal["HTTP", "TCP"] = "HTTP"
    port: int = 80
    url_path: str = "/health"
    interval_ms: int = 10000
    timeout_in_millis: int = 3000
    retries: int = 3


@dataclass
class ListenerConfig:
    """Load balancer listener configuration.

    Attributes:
        port: Port the listener accepts connections on.
        protocol: Protocol for the listener (HTTP or HTTPS).
        ssl_certificate_name: Name of SSL certificate for HTTPS listeners.
    """

    port: int
    protocol: Literal["HTTP", "HTTPS"] = "HTTP"
    ssl_certificate_name: str | None = None


@dataclass
class LoadBalancerConfig:
    """Load balancer configuration.

    Attributes:
        is_public: Whether the load balancer has a public IP.
        minimum_bandwidth_in_mbps: Minimum bandwidth for flexible shape.
        maximum_bandwidth_in_mbps: Maximum bandwidth for flexible shape.
        listeners: List of listener configurations.
        health_check: Health check configuration for backend set.
        backend_port: Port on backend instances to forward traffic to.
    """

    is_public: bool = True
    minimum_bandwidth_in_mbps: int = 10
    maximum_bandwidth_in_mbps: int = 100
    listeners: list[ListenerConfig] = field(default_factory=lambda: [ListenerConfig(port=80)])
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    backend_port: int = 80


class ScalableWorkload(BaseResource):
    """OCI Scalable Workload with load balancer, instance pool, and autoscaling.

    This block creates a complete horizontally-scalable compute architecture:
    - OCI Load Balancer with configurable listeners and health checks
    - Instance Configuration as a template for pool instances
    - Instance Pool for managing multiple identical instances
    - Autoscaling Configuration with metric-based or schedule-based policies

    The architecture follows OCI best practices:
    - Load balancer deployed to public subnet (internet-facing)
    - Instance pool deployed to private subnet (not directly exposed)
    - Automatic health checking and traffic distribution
    - Automatic scaling based on metrics or schedule

    Usage Patterns:

    1. Simple web workload with CPU-based autoscaling:
        ```python
        vcn = Vcn(name="app", compartment_id=comp_id, stack_name="prod")

        pool = ScalableWorkload(
            name="web",
            compartment_id=comp_id,
            vcn=vcn,
            stack_name="prod",
            min_instances=2,
            max_instances=10,
            scaling_policy=MetricScalingPolicy(
                threshold=MetricThreshold(scale_out_threshold=70)
            ),
        )

        pulumi.export("lb_ip", pool.get_load_balancer_ip())
        ```

    2. Custom configuration with HTTPS:
        ```python
        pool = ScalableWorkload(
            name="api",
            compartment_id=comp_id,
            vcn=vcn,
            stack_name="prod",
            shape="VM.Standard.E4.Flex",
            ocpus=2,
            memory_in_gbs=32,
            min_instances=3,
            max_instances=20,
            load_balancer_config=LoadBalancerConfig(
                listeners=[
                    ListenerConfig(port=443, protocol="HTTPS", ssl_certificate_name="my-cert"),
                ],
                health_check=HealthCheckConfig(url_path="/api/health"),
                backend_port=8080,
            ),
        )
        ```

    3. Schedule-based scaling for predictable load:
        ```python
        pool = ScalableWorkload(
            name="batch",
            compartment_id=comp_id,
            vcn=vcn,
            stack_name="prod",
            scaling_policy=ScheduleScalingPolicy(
                schedules=[
                    ScheduleEntry(
                        cron_expression="0 0 8 ? * MON-FRI *",
                        action=ScalingAction.CHANGE_COUNT_TO,
                        value=10,
                        display_name="Scale up for business hours",
                    ),
                    ScheduleEntry(
                        cron_expression="0 0 18 ? * MON-FRI *",
                        action=ScalingAction.CHANGE_COUNT_TO,
                        value=2,
                        display_name="Scale down after hours",
                    ),
                ],
            ),
        )
        ```
    """

    vcn: Vcn
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
        vcn: Vcn,
        stack_name: str,
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
        # Scaling policy (metric OR schedule, not both)
        scaling_policy: MetricScalingPolicy | ScheduleScalingPolicy | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a scalable workload with load balancer, instance pool, and autoscaling.

        :param str name: The name of the workload
        :param pulumi.Input[str] compartment_id: The OCID of the compartment
        :param Vcn vcn: The VCN instance to deploy into
        :param str stack_name: Stack identifier for naming and tagging
        :param pulumi.Input[str] shape: Compute shape (default: VM.Standard.E4.Flex)
        :param pulumi.Input[float] ocpus: Number of OCPUs (default: 1)
        :param pulumi.Input[float] memory_in_gbs: Memory in GB (default: 16)
        :param pulumi.Input[str] image_id: Optional custom image OCID (defaults to Oracle Linux 8)
        :param pulumi.Input[str] ssh_public_key: SSH public key (optional - auto-generates if not provided)
        :param str user_data: Cloud-init user data script (base64 encoded)
        :param pulumi.Input[int] boot_volume_size_in_gbs: Boot volume size (default: 50GB)
        :param int min_instances: Minimum instances in pool (default: 1)
        :param int max_instances: Maximum instances in pool (default: 5)
        :param int initial_instances: Initial instance count (defaults to min_instances)
        :param LoadBalancerConfig load_balancer_config: Load balancer configuration
        :param MetricScalingPolicy | ScheduleScalingPolicy scaling_policy: Autoscaling policy
        :param pulumi.ResourceOptions opts: Options for the resource
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
        self.scaling_policy = scaling_policy
        self.listeners = []
        self.autoscaling_configuration = None

        # Handle SSH key - either use provided or auto-generate
        if ssh_public_key is None or (isinstance(ssh_public_key, str) and ssh_public_key.strip() == ""):
            public_key, private_key = self._generate_ssh_key_pair()
            self.ssh_public_key = public_key
            self.ssh_private_key = private_key
            self.auto_generated_keys = True
        else:
            self.ssh_public_key = str(ssh_public_key)
            self.ssh_private_key = None
            self.auto_generated_keys = False

        # Add security rules for load balancer and instance pool
        self._add_scalable_workload_security_rules()

        # Finalize the VCN network
        self.vcn.finalize_network()

        # Verify subnets exist after finalization
        assert self.vcn.public_subnet is not None, "VCN public subnet must exist after finalization"
        assert self.vcn.private_subnet is not None, "VCN private subnet must exist after finalization"

        # Get the latest Oracle Linux 8 image if no custom image specified
        if image_id is None:
            images = oci.core.get_images(
                compartment_id=str(compartment_id),
                operating_system="Oracle Linux",
                operating_system_version="8",
                shape=str(shape),
                sort_by="TIMECREATED",
                sort_order="DESC",
            )
            self.image_id = images.images[0].id

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

        if self.auto_generated_keys:
            outputs["ssh_public_key"] = pulumi.Output.secret(self.ssh_public_key)
            if self.ssh_private_key:
                outputs["ssh_private_key"] = pulumi.Output.secret(self.ssh_private_key)

        self.register_outputs(outputs)

    def _add_scalable_workload_security_rules(self) -> None:
        """Add security rules for load balancer and instance pool communication.

        Security Rules Added:
        ---------------------
        Public Subnet (Load Balancer):
        - Ingress: HTTP (80) and HTTPS (443) from internet
        - Egress: Backend port to private subnet

        Private Subnet (Instance Pool):
        - Ingress: Backend port from public subnet (load balancer)
        - Ingress: Health check port from public subnet
        - Ingress: SSH (22) from public subnet (bastion access)
        - Egress: HTTPS (443) to OCI services (monitoring, telemetry)
        """
        public_subnet_cidr = self.vcn.get_public_subnet_cidr()
        private_subnet_cidr = self.vcn.get_private_subnet_cidr()
        backend_port = self.load_balancer_config.backend_port
        health_port = self.load_balancer_config.health_check.port

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

        # Add health check port egress if different from backend port
        if health_port != backend_port:
            public_egress_rules.append(
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description=f"Load balancer health checks to instances on port {health_port}",
                    protocol="6",  # TCP
                    destination=private_subnet_cidr,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        min=health_port,
                        max=health_port,
                    ),
                ),
            )

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
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="SSH access from public subnet for bastion host access",
                protocol="6",  # TCP
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=22,
                    max=22,
                ),
            ),
        ]

        # Add health check ingress if different from backend port
        if health_port != backend_port:
            private_ingress_rules.append(
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description=f"Health check from load balancer on port {health_port}",
                    protocol="6",  # TCP
                    source=public_subnet_cidr,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        min=health_port,
                        max=health_port,
                    ),
                ),
            )

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
        """Create the load balancer, backend set, and listeners."""
        lb_config = self.load_balancer_config

        # Subnets are guaranteed to exist after finalize_network()
        assert self.vcn.public_subnet is not None
        assert self.vcn.private_subnet is not None

        # Create load balancer
        lb_name = self.create_resource_name("lb")
        self.load_balancer = oci.loadbalancer.LoadBalancer(
            lb_name,
            compartment_id=self.compartment_id,
            display_name=lb_name,
            shape="flexible",
            shape_details=oci.loadbalancer.LoadBalancerShapeDetailsArgs(
                minimum_bandwidth_in_mbps=lb_config.minimum_bandwidth_in_mbps,
                maximum_bandwidth_in_mbps=lb_config.maximum_bandwidth_in_mbps,
            ),
            subnet_ids=[self.vcn.public_subnet.id],
            is_private=not lb_config.is_public,
            freeform_tags=self.create_freeform_tags(
                lb_name,
                "load-balancer",
                {
                    "IsPublic": str(lb_config.is_public),
                    "MinBandwidth": str(lb_config.minimum_bandwidth_in_mbps),
                    "MaxBandwidth": str(lb_config.maximum_bandwidth_in_mbps),
                },
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Create backend set with health check
        bs_name = self.create_resource_name("bs")
        health_check = lb_config.health_check
        self.backend_set = oci.loadbalancer.BackendSet(
            bs_name,
            load_balancer_id=self.load_balancer.id,
            name=bs_name,
            policy="ROUND_ROBIN",
            health_checker=oci.loadbalancer.BackendSetHealthCheckerArgs(
                protocol=health_check.protocol,
                port=health_check.port,
                url_path=health_check.url_path if health_check.protocol == "HTTP" else None,
                interval_ms=health_check.interval_ms,
                timeout_in_millis=health_check.timeout_in_millis,
                retries=health_check.retries,
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Create listeners
        for i, listener_config in enumerate(lb_config.listeners):
            listener_name = self.create_resource_name(f"listener-{i}")
            listener = oci.loadbalancer.Listener(
                listener_name,
                load_balancer_id=self.load_balancer.id,
                name=listener_name,
                default_backend_set_name=self.backend_set.name,
                port=listener_config.port,
                protocol=listener_config.protocol,
                ssl_configuration=oci.loadbalancer.ListenerSslConfigurationArgs(
                    certificate_name=listener_config.ssl_certificate_name,
                    verify_peer_certificate=False,
                ) if listener_config.protocol == "HTTPS" and listener_config.ssl_certificate_name else None,
                opts=pulumi.ResourceOptions(parent=self),
            )
            self.listeners.append(listener)

    def _create_instance_configuration(self) -> None:
        """Create the instance configuration as a template for the pool."""
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
            freeform_tags=self.create_freeform_tags(
                ic_name,
                "instance-configuration",
                {
                    "Shape": str(self.shape),
                    "OCPUs": str(self.ocpus),
                    "MemoryGB": str(self.memory_in_gbs),
                },
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_instance_pool(self) -> None:
        """Create the instance pool with load balancer attachment."""
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
            freeform_tags=self.create_freeform_tags(
                pool_name,
                "instance-pool",
                {
                    "MinInstances": str(self.min_instances),
                    "MaxInstances": str(self.max_instances),
                    "InitialInstances": str(self.initial_instances),
                },
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_autoscaling_configuration(self) -> None:
        """Create autoscaling configuration based on the scaling policy."""
        if self.scaling_policy is None:
            return

        asc_name = self.create_resource_name("asc")

        if isinstance(self.scaling_policy, MetricScalingPolicy):
            self._create_metric_autoscaling(asc_name)
        elif isinstance(self.scaling_policy, ScheduleScalingPolicy):
            self._create_schedule_autoscaling(asc_name)

    def _create_metric_autoscaling(self, asc_name: str) -> None:
        """Create metric-based autoscaling configuration."""
        policy = self.scaling_policy
        assert isinstance(policy, MetricScalingPolicy)
        threshold = policy.threshold

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
                                value=threshold.scale_out_value,
                            ),
                            display_name="Scale Out",
                            metric=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricArgs(
                                metric_type=threshold.metric.value,
                                threshold=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricThresholdArgs(
                                    operator="GT",
                                    value=threshold.scale_out_threshold,
                                ),
                            ),
                        ),
                        # Scale in rule
                        oci.autoscaling.AutoScalingConfigurationPolicyRuleArgs(
                            action=oci.autoscaling.AutoScalingConfigurationPolicyRuleActionArgs(
                                type="CHANGE_COUNT_BY",
                                value=threshold.scale_in_value,
                            ),
                            display_name="Scale In",
                            metric=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricArgs(
                                metric_type=threshold.metric.value,
                                threshold=oci.autoscaling.AutoScalingConfigurationPolicyRuleMetricThresholdArgs(
                                    operator="LT",
                                    value=threshold.scale_in_threshold,
                                ),
                            ),
                        ),
                    ],
                ),
            ],
            freeform_tags=self.create_freeform_tags(
                asc_name,
                "autoscaling-configuration",
                {
                    "PolicyType": "metric",
                    "Metric": threshold.metric.value,
                    "ScaleOutThreshold": str(threshold.scale_out_threshold),
                    "ScaleInThreshold": str(threshold.scale_in_threshold),
                },
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _create_schedule_autoscaling(self, asc_name: str) -> None:
        """Create schedule-based autoscaling configuration."""
        policy = self.scaling_policy
        assert isinstance(policy, ScheduleScalingPolicy)

        # Build execution schedules from schedule entries
        execution_schedules = [
            oci.autoscaling.AutoScalingConfigurationPolicyExecutionScheduleArgs(
                expression=entry.cron_expression,
                timezone="UTC",
                type="cron",
            )
            for entry in policy.schedules
        ]

        # For schedule-based policies, we create one policy per schedule entry
        policies = []
        for i, entry in enumerate(policy.schedules):
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
            freeform_tags=self.create_freeform_tags(
                asc_name,
                "autoscaling-configuration",
                {
                    "PolicyType": "scheduled",
                    "ScheduleCount": str(len(policy.schedules)),
                },
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

    def _generate_ssh_key_pair(self) -> tuple[str, str]:
        """Generate an SSH key pair for instances.

        Returns:
            Tuple of (public_key, private_key) as strings.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "id_rsa")

            subprocess.run(
                [
                    "ssh-keygen",
                    "-t",
                    "rsa",
                    "-b",
                    "4096",
                    "-f",
                    key_path,
                    "-N",
                    "",
                    "-C",
                    f"ociblocks-{self.stack_name}-{self.name}",
                ],
                check=True,
                capture_output=True,
            )

            with open(f"{key_path}.pub", "r") as f:
                public_key = f.read().strip()

            with open(key_path, "r") as f:
                private_key = f.read()

        return public_key, private_key

    def get_load_balancer_ip(self) -> pulumi.Output[str]:
        """Get the public IP address of the load balancer.

        Returns:
            The load balancer's public IP address as a Pulumi Output.
        """
        return self.load_balancer.ip_address_details.apply(
            lambda details: details[0].ip_address or "" if details else ""
        )

    def get_instance_pool_id(self) -> pulumi.Output[str]:
        """Get the OCID of the instance pool.

        Returns:
            The instance pool OCID as a Pulumi Output.
        """
        return self.instance_pool.id

    def get_load_balancer_id(self) -> pulumi.Output[str]:
        """Get the OCID of the load balancer.

        Returns:
            The load balancer OCID as a Pulumi Output.
        """
        return self.load_balancer.id

    def get_ssh_public_key(self) -> str:
        """Get the SSH public key used for instances.

        Returns:
            The SSH public key as a string.
        """
        return self.ssh_public_key

    def get_ssh_private_key(self) -> str | None:
        """Get the SSH private key if auto-generated.

        Returns:
            The SSH private key as a string if auto-generated, None otherwise.
        """
        return self.ssh_private_key
