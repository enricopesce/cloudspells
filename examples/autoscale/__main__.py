"""VCN + ScalableWorkload test — deploys an autoscaling instance pool with load balancer."""

import pulumi
from blocks.vcn.network import Vcn
from blocks.autoscale import (
    ScalableWorkload,
    MetricScalingPolicy,
    MetricThreshold,
    ScalingMetric,
    LoadBalancerConfig,
    HealthCheckConfig,
)

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")

ssh_key: str | None = config.get("ssh_key")
if ssh_key == "":
    ssh_key = None

# Create VCN
vcn: Vcn = Vcn(
    name="scalable",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack(),
)

# ScalableWorkload adds security rules and calls finalize_network()
scalable_pool: ScalableWorkload = ScalableWorkload(
    name="web-pool",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
    shape="VM.Standard.E4.Flex",
    ocpus=1,
    memory_in_gbs=16,
    min_instances=1,
    max_instances=3,
    initial_instances=1,
    load_balancer_config=LoadBalancerConfig(
        is_public=True,
        minimum_bandwidth_in_mbps=10,
        maximum_bandwidth_in_mbps=100,
        health_check=HealthCheckConfig(
            protocol="HTTP",
            port=80,
            url_path="/",
        ),
        backend_port=80,
    ),
    scaling_policy=MetricScalingPolicy(
        threshold=MetricThreshold(
            metric=ScalingMetric.CPU_UTILIZATION,
            scale_out_threshold=70,
            scale_in_threshold=30,
            scale_out_value=1,
            scale_in_value=-1,
        ),
        cooldown_in_seconds=300,
    ),
)

# VCN outputs
pulumi.export("vcn_id", vcn.id)
pulumi.export("cidr_block", vcn.cidr_block)

# ScalableWorkload outputs
pulumi.export("lb_ip", scalable_pool.get_load_balancer_ip())
pulumi.export("lb_id", scalable_pool.get_load_balancer_id())
pulumi.export("pool_id", scalable_pool.get_instance_pool_id())

if scalable_pool.auto_generated_keys:
    pulumi.export("ssh_private_key", pulumi.Output.secret(scalable_pool.get_ssh_private_key()))
