# Compute Instance Block - Usage Guide

This guide shows how to use the new `ComputeInstance` block to create OCI compute instances with attached storage.

## Overview

The `ComputeInstance` block creates:
- A compute instance with Oracle Linux 8 (or custom image)
- Deployment to VCN's private subnet (secure by default)
- An attached block volume for data storage
- SSH access security rules (from public subnet for bastion access)

## Quick Start

### 1. Basic Usage with Defaults

```python
import pulumi
from blocks.vcn.network import Vcn
from blocks.compute.instance import ComputeInstance

config = pulumi.Config()
compartment_id = config.require("compartment_ocid")
ssh_key = config.require("ssh_key")

# Create VCN
vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack()
)

# Create compute instance with defaults
# - Shape: VM.Standard.E4.Flex
# - OCPUs: 1
# - Memory: 16GB
# - Boot volume: 50GB
# - Data volume: 100GB
web_server = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key
)

# Export outputs
pulumi.export("instance_id", web_server.get_instance_id())
pulumi.export("private_ip", web_server.get_private_ip())
pulumi.export("data_volume_id", web_server.get_block_volume_id())
```

### 2. Custom Configuration

```python
# Create a larger instance with custom storage
app_server = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
    shape="VM.Standard.E4.Flex",
    ocpus=4,
    memory_in_gbs=64,
    boot_volume_size_in_gbs=100,
    block_volume_size_in_gbs=500
)
```

### 3. Using a Custom Image

```python
# Use your custom image
custom_instance = ComputeInstance(
    name="custom-server",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
    image_id="ocid1.image.oc1...."  # Your custom image OCID
)
```

## Configuration Parameters

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | str | Instance name (used for resource naming) |
| `compartment_id` | pulumi.Input[str] | OCI compartment OCID |
| `vcn` | Vcn | VCN instance to deploy into |
| `stack_name` | str | Stack identifier for naming/tagging |
| `ssh_public_key` | pulumi.Input[str] | SSH public key for instance access |

### Optional Parameters (with defaults)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `shape` | pulumi.Input[str] | `VM.Standard.E4.Flex` | Compute shape |
| `ocpus` | pulumi.Input[float] | `1` | Number of OCPUs |
| `memory_in_gbs` | pulumi.Input[float] | `16` | Memory in GB |
| `image_id` | pulumi.Input[str] | `None` | Custom image OCID (defaults to Oracle Linux 8) |
| `boot_volume_size_in_gbs` | pulumi.Input[int] | `50` | Boot volume size in GB |
| `block_volume_size_in_gbs` | pulumi.Input[int] | `100` | Data volume size in GB |

## Security Configuration

The compute instance is deployed with these security settings:

### Network Placement
- **Private Subnet**: Instance is deployed to the private subnet (no direct internet access)
- **No Public IP**: Instance does not get a public IP address
- **NAT Gateway**: Outbound internet access via NAT Gateway

### Security Rules
The block automatically adds these rules to the VCN's private security list:

**Ingress Rules:**
- SSH (port 22) from public subnet (for bastion host access)

To add additional rules (HTTP, HTTPS, custom ports), use the VCN's `add_security_list_rules()` method before creating the instance.

## Example: Multiple Instances

```python
# Create VCN
vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    stack_name=pulumi.get_stack()
)

# Web server (small)
web_server = ComputeInstance(
    name="web-01",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
    ocpus=2,
    memory_in_gbs=32
)

# App server (medium)
app_server = ComputeInstance(
    name="app-01",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
    ocpus=4,
    memory_in_gbs=64,
    block_volume_size_in_gbs=200
)

# Database server (large)
db_server = ComputeInstance(
    name="db-01",
    compartment_id=compartment_id,
    vcn=vcn,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
    ocpus=8,
    memory_in_gbs=128,
    boot_volume_size_in_gbs=100,
    block_volume_size_in_gbs=1000
)
```

## Running the Example

1. Configure your Pulumi stack:
```bash
cd examples
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set ssh_key "ssh-rsa AAAA..."
```

2. Optional configurations:
```bash
pulumi config set instance_shape VM.Standard.E4.Flex
pulumi config set instance_ocpus 2
pulumi config set instance_memory_in_gbs 32
pulumi config set boot_volume_size_in_gbs 50
pulumi config set block_volume_size_in_gbs 100
```

3. Run the example:
```bash
# Use the compute example
pulumi up -f example_compute.py
```

## Outputs

The instance exports these outputs:

- `instance_id`: The OCID of the compute instance
- `private_ip`: The private IP address of the instance
- `block_volume_id`: The OCID of the attached data volume

## Accessing the Instance

Since the instance is in a private subnet, you'll need a bastion host to access it:

1. Create a bastion host in the public subnet
2. SSH to the bastion host
3. From the bastion, SSH to the compute instance using its private IP

```bash
# SSH to bastion (public IP)
ssh -i ~/.ssh/id_rsa opc@<bastion-public-ip>

# From bastion, SSH to compute instance (private IP)
ssh -i ~/.ssh/id_rsa opc@<instance-private-ip>
```

## Block Volume

The attached block volume needs to be mounted inside the instance:

```bash
# SSH into the instance
ssh opc@<instance-private-ip>

# List available block devices
lsblk

# Create filesystem on the block volume (e.g., /dev/sdb)
sudo mkfs.ext4 /dev/sdb

# Create mount point
sudo mkdir /data

# Mount the volume
sudo mount /dev/sdb /data

# Add to /etc/fstab for persistent mount
echo '/dev/sdb /data ext4 defaults,_netdev,nofail 0 2' | sudo tee -a /etc/fstab
```

## Common Shapes

| Shape | Architecture | OCPU Range | Memory per OCPU | Use Case |
|-------|-------------|------------|-----------------|----------|
| VM.Standard.E4.Flex | x86 | 1-64 | 1-64 GB | General purpose |
| VM.Standard.E5.Flex | x86 | 1-94 | 1-64 GB | Latest generation |
| VM.Standard.A1.Flex | ARM | 1-80 | 1-64 GB | Cost-optimized |
| VM.Optimized3.Flex | x86 | 1-18 | 64 GB (fixed) | Compute-intensive |

## Next Steps

- Add a Load Balancer block to distribute traffic
- Create a Bastion Host block for secure access
- Implement Object Storage block for backups
- Add Database blocks for data persistence
