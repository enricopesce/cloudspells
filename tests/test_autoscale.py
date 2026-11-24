"""Unit tests for AutoScale workload block."""

import unittest
from unittest.mock import patch

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import OCIMocks, set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci.autoscale import (
    MetricScalingPolicy,
    OciLoadBalancerConfig,
    ScalableWorkload,
    ScalingAction,
    ScalingMetric,
    ScheduleEntry,
    ScheduleScalingPolicy,
)
from cloudspells.providers.oci.network import Vcn, VcnRef


class TestAutoscaleWorkload(unittest.TestCase):
    """Test cases for AutoScale workload block."""

    def _make_vcn(self) -> Vcn:
        """Create a fresh VCN for each test to prevent shared mutable state."""
        return Vcn(
            name="autoscale-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

    @pulumi.runtime.test
    def test_creates_load_balancer(self):
        """Test that ScalableWorkload creates a load balancer."""
        workload = ScalableWorkload(
            name="test-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        def check_load_balancer(lb_id):
            self.assertIsNotNone(lb_id, "Load balancer must be created")

        return workload.load_balancer.id.apply(check_load_balancer)

    @pulumi.runtime.test
    def test_creates_instance_pool(self):
        """Test that ScalableWorkload creates an instance pool."""
        workload = ScalableWorkload(
            name="test-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        def check_instance_pool(pool_id):
            self.assertIsNotNone(pool_id, "Instance pool must be created")

        return workload.instance_pool.id.apply(check_instance_pool)

    @pulumi.runtime.test
    def test_creates_instance_configuration(self):
        """Test that ScalableWorkload creates an instance configuration."""
        workload = ScalableWorkload(
            name="test-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        def check_instance_config(config_id):
            self.assertIsNotNone(config_id, "Instance configuration must be created")

        return workload.instance_configuration.id.apply(check_instance_config)

    @pulumi.runtime.test
    def test_creates_backend_set(self):
        """Test that ScalableWorkload creates a backend set."""
        workload = ScalableWorkload(
            name="test-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        def check_backend_set(bs_name):
            self.assertIsNotNone(bs_name, "Backend set must be created")

        return workload.backend_set.name.apply(check_backend_set)

    @pulumi.runtime.test
    def test_finalizes_vcn(self):
        """Test that ScalableWorkload calls finalize_network() on VCN."""
        vcn = Vcn(
            name="finalize-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        # Subnets should be None before ScalableWorkload
        self.assertIsNone(vcn.public_subnet)
        self.assertIsNone(vcn.private_subnet)

        ScalableWorkload(
            name="test-workload",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        # After ScalableWorkload, subnets should exist
        self.assertIsNotNone(vcn.public_subnet, "VCN should be finalized by ScalableWorkload")
        self.assertIsNotNone(vcn.private_subnet, "VCN should be finalized by ScalableWorkload")

    @patch.object(OCIMocks, "new_resource", autospec=True, side_effect=OCIMocks.new_resource)
    @pulumi.runtime.test
    def test_shared_vcn_scopes_pool_ingress_to_its_own_load_balancer(self, mock_resource):
        """Two workloads have disjoint policies even when the VCN is already finalized."""
        vcn = self._make_vcn()
        vcn.finalize_network()
        workloads = [
            ScalableWorkload(
                name=name,
                compartment_id="ocid1.compartment.test",
                vcn=vcn,
                image_id="ocid1.image.oc1.phx.test",
                ssh_public_key="ssh-rsa test",
                load_balancer_config=config,
            )
            for name, config in (
                ("outer", OciLoadBalancerConfig(backend_port=8080)),
                ("inner", OciLoadBalancerConfig(backend_port=9090, is_public=False, ssl_certificate_name="test-cert")),
            )
        ]

        def check(values):
            resources = [call.args[1] for call in mock_resource.call_args_list]
            rules = [r.inputs for r in resources if r.typ.endswith(":NetworkSecurityGroupSecurityRule")]
            for workload, (frontend, backend, groups, details, listener_ports, _pool) in zip(
                workloads, values, strict=True
            ):
                self.assertEqual(list(groups), [frontend])
                self.assertEqual(list(details["launch_details"]["create_vnic_details"]["nsg_ids"]), [backend])
                port = workload.load_balancer_config.backend_port
                for group, direction, field, peer in (
                    (backend, "INGRESS", "source", frontend),
                    (frontend, "EGRESS", "destination", backend),
                ):
                    matching = [
                        r for r in rules if r["networkSecurityGroupId"] == group and r["direction"] == direction
                    ]
                    self.assertEqual(len(matching), 1)
                    self.assertEqual(matching[0][field], peer)
                    self.assertEqual(matching[0][f"{field}Type"], "NETWORK_SECURITY_GROUP")
                    self.assertEqual(matching[0]["tcpOptions"]["destinationPortRange"], {"min": port, "max": port})
                clients = [r for r in rules if r["networkSecurityGroupId"] == frontend and r["direction"] == "INGRESS"]
                source = "0.0.0.0/0" if workload.load_balancer_config.is_public else vcn.cidr_block
                expected_ports = [80, 443] if workload.load_balancer_config.ssl_certificate_name else [80]
                self.assertEqual(sorted(listener_ports), expected_ports)
                self.assertEqual(
                    sorted(
                        (
                            r["source"],
                            r["tcpOptions"]["destinationPortRange"]["min"],
                            r["tcpOptions"]["destinationPortRange"]["max"],
                        )
                        for r in clients
                    ),
                    [(source, port, port) for port in expected_ports],
                )
            self.assertNotEqual(values[0][1], values[1][1])
            for resource in resources:
                if resource.typ.endswith(":SecurityList"):
                    self.assertFalse(any(r["protocol"] == "6" for r in resource.inputs["ingressSecurityRules"]))

        return pulumi.Output.all(
            *(
                pulumi.Output.all(
                    workload.load_balancer_nsg.id,
                    workload.backend_nsg.id,
                    workload.load_balancer.network_security_group_ids,
                    workload.instance_configuration.instance_details,
                    pulumi.Output.all(*(listener.port for listener in workload.listeners)),
                    workload.instance_pool.id,
                )
                for workload in workloads
            )
        ).apply(check)

    @pulumi.runtime.test
    def test_imported_network_uses_workload_security_groups(self):
        """An imported VCN can host its own workload NSGs."""
        vcn = VcnRef("test-vcn", "test-public", "test-private", "10.0.48.0/21", "10.0.0.0/19", "10.0.0.0/18")
        workload = ScalableWorkload(
            name="imported",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa test",
            load_balancer_config=OciLoadBalancerConfig(is_public=False),
        )

        def check(values):
            self.assertEqual(list(values[0]), ["test-private"])
            self.assertEqual(list(values[1]), [values[2]])

        return pulumi.Output.all(
            workload.load_balancer.subnet_ids,
            workload.load_balancer.network_security_group_ids,
            workload.load_balancer_nsg.id,
        ).apply(check)

    def test_auto_generates_ssh_key(self):
        """Test that ScalableWorkload auto-generates SSH keys when not provided."""
        workload = ScalableWorkload(
            name="auto-key-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            # No ssh_public_key provided
        )

        self.assertTrue(workload.auto_generated_keys, "Keys should be auto-generated")
        self.assertIsNotNone(workload.ssh_public_key, "Public key should be generated")
        self.assertIsNotNone(workload.ssh_private_key, "Private key should be generated")
        self.assertTrue(workload.ssh_public_key.startswith("ssh-rsa"), "Public key should be RSA format")

    def test_uses_provided_ssh_key(self):
        """Test that ScalableWorkload uses provided SSH key."""
        provided_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAA... user@host"

        workload = ScalableWorkload(
            name="provided-key-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key=provided_key,
        )

        self.assertFalse(workload.auto_generated_keys, "Keys should not be auto-generated")
        self.assertEqual(workload.ssh_public_key, provided_key, "Should use provided key")
        self.assertIsNone(workload.ssh_private_key, "Private key should be None when provided")

    def test_default_instances(self):
        """Test that ScalableWorkload uses default instance counts."""
        workload = ScalableWorkload(
            name="default-instances-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        self.assertEqual(workload.min_instances, 1, "Default min_instances should be 1")
        self.assertEqual(workload.max_instances, 5, "Default max_instances should be 5")
        self.assertEqual(workload.initial_instances, 1, "Default initial_instances should equal min_instances")

    def test_custom_instances(self):
        """Test that ScalableWorkload accepts custom instance counts."""
        workload = ScalableWorkload(
            name="custom-instances-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            min_instances=2,
            max_instances=10,
            initial_instances=3,
        )

        self.assertEqual(workload.min_instances, 2)
        self.assertEqual(workload.max_instances, 10)
        self.assertEqual(workload.initial_instances, 3)

    def test_default_shape(self):
        """Test that ScalableWorkload uses default shape."""
        workload = ScalableWorkload(
            name="default-shape-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        self.assertEqual(workload.shape, "VM.Standard.E4.Flex", "Default shape should be E4.Flex")

    def test_custom_shape(self):
        """Test that ScalableWorkload accepts custom shape."""
        workload = ScalableWorkload(
            name="custom-shape-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            shape="VM.Standard.A1.Flex",
            ocpus=4,
            memory_in_gbs=24,
        )

        self.assertEqual(workload.shape, "VM.Standard.A1.Flex")
        self.assertEqual(workload.ocpus, 4)
        self.assertEqual(workload.memory_in_gbs, 24)

    def test_default_metric_scaling_policy(self):
        """Test that ScalableWorkload uses MetricScalingPolicy by default."""
        workload = ScalableWorkload(
            name="default-policy-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        self.assertIsInstance(workload.scaling_policy, MetricScalingPolicy)
        self.assertIsNotNone(workload.autoscaling_configuration, "Autoscaling config should be created by default")

    def test_with_metric_scaling_policy(self):
        """Test that ScalableWorkload accepts metric scaling policy."""
        policy = MetricScalingPolicy(
            scale_out_threshold=70,
            scale_in_threshold=30,
            scale_out_value=2,
            cooldown_in_seconds=600,
        )

        workload = ScalableWorkload(
            name="metric-scaling-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            scaling_policy=policy,
        )

        self.assertIsNotNone(workload.autoscaling_configuration, "Autoscaling config should be created")
        self.assertIsInstance(workload.scaling_policy, MetricScalingPolicy)

    def test_with_schedule_scaling_policy(self):
        """Test that ScalableWorkload accepts schedule scaling policy."""
        policy = ScheduleScalingPolicy(
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
        )

        workload = ScalableWorkload(
            name="schedule-scaling-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            scaling_policy=policy,
        )

        self.assertIsNotNone(workload.autoscaling_configuration, "Autoscaling config should be created")
        self.assertIsInstance(workload.scaling_policy, ScheduleScalingPolicy)

    def test_disable_autoscaling(self):
        """Test that passing scaling_policy=None disables autoscaling."""
        workload = ScalableWorkload(
            name="no-scaling-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            scaling_policy=None,
        )

        self.assertIsNone(workload.autoscaling_configuration, "No autoscaling config when policy=None")

    def test_custom_load_balancer_config(self):
        """Test that ScalableWorkload accepts custom load balancer config."""
        lb_config = OciLoadBalancerConfig(
            backend_port=8080,
            health_check_path="/api/health",
            min_bandwidth_mbps=50,
            max_bandwidth_mbps=200,
        )

        workload = ScalableWorkload(
            name="custom-lb-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            load_balancer_config=lb_config,
        )

        self.assertEqual(workload.load_balancer_config.backend_port, 8080)
        self.assertEqual(workload.load_balancer_config.health_check_path, "/api/health")
        self.assertEqual(workload.load_balancer_config.min_bandwidth_mbps, 50)
        self.assertEqual(workload.load_balancer_config.max_bandwidth_mbps, 200)

    def test_cloud_init_script_requires_shebang(self):
        """Test that a non-empty cloud_init_script without a shebang raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            ScalableWorkload(
                name="no-shebang-workload",
                compartment_id="ocid1.compartment.test",
                vcn=self._make_vcn(),
                image_id="ocid1.image.oc1.phx.test",
                ssh_public_key="ssh-rsa AAAAB3... test-key",
                cloud_init_script="echo hello",
            )

        self.assertIn("shebang", str(ctx.exception))

    def test_cloud_init_script_accepts_shebang(self):
        """Test that a cloud_init_script starting with a shebang is accepted."""
        workload = ScalableWorkload(
            name="shebang-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            cloud_init_script="#!/bin/bash\necho hello\n",
        )

        self.assertIsNotNone(workload.cloud_init_script, "Encoded cloud-init script should be stored")

    @pulumi.runtime.test
    async def test_export_publishes_backend_nsg_and_secret_key(self):
        """The backend NSG is available for migrations and generated SSH keys stay secret."""
        workload = ScalableWorkload(
            name="web-pool",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.test",
        )
        published = {}
        with patch("pulumi.export", side_effect=published.__setitem__):
            workload.export()

        self.assertEqual(
            set(published),
            {
                "web_pool_lb_ip",
                "web_pool_lb_id",
                "web_pool_pool_id",
                "web_pool_backend_nsg_id",
                "web_pool_ssh_private_key",
            },
        )
        self.assertEqual(await published["web_pool_backend_nsg_id"].future(), await workload.backend_nsg.id.future())
        self.assertTrue(await published["web_pool_ssh_private_key"].is_secret())

    def test_getter_methods(self):
        """Test ScalableWorkload getter methods."""
        workload = ScalableWorkload(
            name="getter-test-workload",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        # Verify getter methods return Output types
        self.assertIsNotNone(workload.get_load_balancer_ip())
        self.assertIsNotNone(workload.get_instance_pool_id())
        self.assertIsNotNone(workload.get_load_balancer_id())
        self.assertIsNotNone(workload.get_ssh_public_key())


class TestDataclasses(unittest.TestCase):
    """Test configuration dataclasses."""

    def test_metric_scaling_policy_defaults(self):
        """Test MetricScalingPolicy default values."""
        policy = MetricScalingPolicy()

        self.assertEqual(policy.metric, ScalingMetric.CPU_UTILIZATION)
        self.assertEqual(policy.scale_out_threshold, 80)
        self.assertEqual(policy.scale_in_threshold, 20)
        self.assertEqual(policy.scale_out_value, 1)
        self.assertEqual(policy.scale_in_value, -1)
        self.assertEqual(policy.cooldown_in_seconds, 300)

    def test_metric_scaling_policy_custom(self):
        """Test MetricScalingPolicy with custom values."""
        policy = MetricScalingPolicy(
            scale_out_threshold=70,
            scale_in_threshold=30,
            metric=ScalingMetric.MEMORY_UTILIZATION,
        )

        self.assertEqual(policy.scale_out_threshold, 70)
        self.assertEqual(policy.scale_in_threshold, 30)
        self.assertEqual(policy.metric, ScalingMetric.MEMORY_UTILIZATION)

    def test_load_balancer_config_defaults(self):
        """Test OciLoadBalancerConfig default values."""
        config = OciLoadBalancerConfig()

        self.assertTrue(config.is_public)
        self.assertEqual(config.backend_port, 80)
        self.assertEqual(config.health_check_path, "/health")
        self.assertEqual(config.min_bandwidth_mbps, 10)
        self.assertEqual(config.max_bandwidth_mbps, 100)
        self.assertIsNone(config.ssl_certificate_name)

    def test_load_balancer_config_https(self):
        """Test OciLoadBalancerConfig HTTPS configuration."""
        config = OciLoadBalancerConfig(ssl_certificate_name="my-cert")

        self.assertEqual(config.ssl_certificate_name, "my-cert")

    def test_schedule_entry(self):
        """Test ScheduleEntry creation."""
        entry = ScheduleEntry(
            cron_expression="0 0 9 ? * MON *",
            action=ScalingAction.CHANGE_COUNT_BY,
            value=5,
            display_name="Monday morning scale up",
        )

        self.assertEqual(entry.cron_expression, "0 0 9 ? * MON *")
        self.assertEqual(entry.action, ScalingAction.CHANGE_COUNT_BY)
        self.assertEqual(entry.value, 5)
        self.assertEqual(entry.display_name, "Monday morning scale up")


if __name__ == "__main__":
    unittest.main()
