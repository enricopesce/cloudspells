"""Example usage of OCIBlocks for creating VCN and Compute Instance infrastructure."""

import pulumi
from blocks.vcn.network import Vcn
# from blocks.oke.cluster import OkeCluster  # Commented out - not using OKE cluster
from blocks.compute.instance import ComputeInstance
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
vcn_cidr_block: str = config.require("vcn_cidr_block")
node_shape: str = config.require("node_shape")
kubernetes_version: str = config.require("kubernetes_version")
oke_min_nodes: int = int(config.require("oke_min_nodes"))
node_image_id: str = config.require("node_image_id")
oke_ocpus: float = float(config.require("oke_ocpus"))
oke_memory_in_gbs: float = float(config.require("oke_memory_in_gbs"))

# SSH key is optional - if not provided, keys will be auto-generated
ssh_key: str | None = config.get("ssh_key")
# Treat empty string as None
if ssh_key == "":
    ssh_key = None


# Create VCN (does NOT create security lists or subnets yet)
vcn_network: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack()
)

# Create OKE cluster (commented out - using Compute Instance instead)
# OKE will add its security rules and call vcn_network.finalize_network()
# which creates the security lists and subnets
# oke: OkeCluster = OkeCluster(
#     "okeinfra",
#     compartment_id=compartment_id,
#     vcn=vcn_network,
#     kubernetes_version="v1.31.1",
#     shape="VM.Standard.A1.Flex",
#     image="ocid1.image.oc1.eu-frankfurt-1.aaaaaaaahn6vygfxr6e5rzxbnz3kjrkey3mdwfjjctcjs4nb5dn7ba2cgdka",
#     display_name="infra",
#     memory_in_gbs=oke_memory_in_gbs,
#     min_nodes=oke_min_nodes,
#     ocpus=oke_ocpus,
#     stack_name=pulumi.get_stack()
# )

# Create Compute Instance with default Oracle Linux 8 image
# ComputeInstance will add its security rules and call vcn_network.finalize_network()
# which creates the security lists and subnets
#
# SSH Key Options:
# 1. Pass your own key: config.set("ssh_key", "ssh-rsa AAAA...")
# 2. Auto-generate: Don't set ssh_key in config (keys will be auto-generated and exported)
web_server: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn_network,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,  # Optional - auto-generates if None
    # Optional: customize the instance
    # shape="VM.Standard.E4.Flex",
    # ocpus=2,
    # memory_in_gbs=32,
    # boot_volume_size_in_gbs=50,
    # block_volume_size_in_gbs=200,
)

# =============================================================================
# ScalableWorkload Example - Horizontally-scalable compute with load balancer
# =============================================================================
# Creates a separate VCN with:
# - Load Balancer (public subnet)
# - Instance Pool with autoscaling (private subnet)
# - Metric-based autoscaling policy

# Create a separate VCN for the scalable workload
scalable_vcn: Vcn = Vcn(
    name="scalable",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack(),
)

# Create the ScalableWorkload with CPU-based autoscaling
scalable_pool: ScalableWorkload = ScalableWorkload(
    name="web-pool",
    compartment_id=compartment_id,
    vcn=scalable_vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,  # Optional - auto-generates if None
    # Instance configuration
    shape="VM.Standard.E4.Flex",
    ocpus=1,
    memory_in_gbs=16,
    # Pool sizing
    min_instances=1,
    max_instances=3,
    initial_instances=1,
    # Load balancer with health check
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
    # Autoscaling policy - scale based on CPU utilization
    scaling_policy=MetricScalingPolicy(
        threshold=MetricThreshold(
            metric=ScalingMetric.CPU_UTILIZATION,
            scale_out_threshold=70,  # Add instance when CPU > 70%
            scale_in_threshold=30,   # Remove instance when CPU < 30%
            scale_out_value=1,       # Add 1 instance at a time
            scale_in_value=-1,       # Remove 1 instance at a time
        ),
        cooldown_in_seconds=300,     # Wait 5 minutes between scaling actions
    ),
)

# Export ScalableWorkload outputs
pulumi.export("scalable_vcn_id", scalable_vcn.id)
pulumi.export("scalable_lb_ip", scalable_pool.get_load_balancer_ip())
pulumi.export("scalable_lb_id", scalable_pool.get_load_balancer_id())
pulumi.export("scalable_pool_id", scalable_pool.get_instance_pool_id())

# SSH Keys for scalable workload
if scalable_pool.auto_generated_keys:
    pulumi.export("scalable_ssh_private_key", pulumi.Output.secret(scalable_pool.get_ssh_private_key()))

# =============================================================================
# ComputeInstance Outputs
# =============================================================================

# Export important values (after ComputeInstance has finalized the network)
# VCN outputs
pulumi.export("vcn_id", vcn_network.id)
pulumi.export("cidr_block", vcn_network.cidr_block)

# Subnets are created after finalize_network() is called by ComputeInstance
assert vcn_network.public_subnet is not None, "public_subnet should exist after finalization"
assert vcn_network.private_subnet is not None, "private_subnet should exist after finalization"
pulumi.export("public_subnet_id", vcn_network.public_subnet.id)
pulumi.export("private_subnet_id", vcn_network.private_subnet.id)
pulumi.export("public_subnet_cidr", vcn_network.public_subnet.cidr_block)
pulumi.export("private_subnet_cidr", vcn_network.private_subnet.cidr_block)

# Compute Instance outputs
pulumi.export("web_server_id", web_server.get_instance_id())
pulumi.export("web_server_private_ip", web_server.get_private_ip())
pulumi.export("web_server_data_volume_id", web_server.get_block_volume_id())

# SSH Keys (auto-generated or provided)
pulumi.export("ssh_public_key", web_server.get_ssh_public_key())
if web_server.auto_generated_keys:
    # Export private key as secret (encrypted in state)
    pulumi.export("ssh_private_key", pulumi.Output.secret(web_server.get_ssh_private_key()))
    pulumi.export("ssh_connection_command", pulumi.Output.concat(
        "Save the private key to a file and run:\n",
        "pulumi stack output ssh_private_key --show-secrets > ~/.ssh/ociblocks_",
        pulumi.get_stack(),
        "\n",
        "chmod 600 ~/.ssh/ociblocks_",
        pulumi.get_stack(),
        "\n",
        "ssh -i ~/.ssh/ociblocks_",
        pulumi.get_stack(),
        " opc@",
        web_server.get_private_ip()
    ))