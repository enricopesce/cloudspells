# SSH Key Setup and Connection Guide

This guide shows you how to generate SSH keys and connect to your compute instance.

## Part 1: Generate SSH Key Pair

### Option A: Generate a New SSH Key (Recommended)

```bash
# Generate a new SSH key pair
ssh-keygen -t rsa -b 4096 -f ~/.ssh/ociblocks_key -C "ociblocks-compute"

# This creates two files:
# - ~/.ssh/ociblocks_key       (private key - keep this SECRET!)
# - ~/.ssh/ociblocks_key.pub   (public key - this goes to OCI)
```

**Important**: When prompted:
- Enter a passphrase (recommended) or press Enter for no passphrase
- Remember the passphrase if you set one

### Option B: Use an Existing SSH Key

If you already have an SSH key pair:

```bash
# List your existing keys
ls -la ~/.ssh/

# Common names: id_rsa, id_ed25519, id_ecdsa
# If you have one, you can use it!
```

## Part 2: Configure Pulumi with Your SSH Key

### Get Your Public Key

```bash
# Display your public key (this is what we need for Pulumi config)
cat ~/.ssh/ociblocks_key.pub

# Example output:
# ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC5... ociblocks-compute
```

### Set the SSH Key in Pulumi Config

```bash
cd /home/opc/source/OCIblocks/test

# Set the SSH public key in Pulumi config
# Copy the ENTIRE output from the cat command above
pulumi config set ssh_key "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC5... ociblocks-compute"

# Or read it directly from the file
pulumi config set ssh_key "$(cat ~/.ssh/ociblocks_key.pub)"
```

### Verify Configuration

```bash
# Check that it's set correctly
pulumi config get ssh_key

# Should show your public key
```

## Part 3: Deploy the Infrastructure

```bash
cd /home/opc/source/OCIblocks/test

# Preview what will be created
pulumi preview

# Deploy the infrastructure
pulumi up
```

After deployment, you'll see outputs like:
```
Outputs:
  web_server_id         : "ocid1.instance.oc1...."
  web_server_private_ip : "10.0.1.123"
  ...
```

## Part 4: Connect to Your Compute Instance

### ⚠️ Important: Instance is in Private Subnet

Your compute instance is deployed in a **private subnet** for security. It has **NO public IP address**.

You have **three options** to connect:

### Option 1: Create a Bastion Host (Recommended)

Deploy a bastion host in the public subnet first, then SSH through it.

```python
# Add to __main__.py (before web_server):

bastion: ComputeInstance = ComputeInstance(
    name="bastion",
    compartment_id=compartment_id,
    vcn=vcn_network,
    stack_name=pulumi.get_stack(),
    ssh_public_key=ssh_key,
    # Deploy to public subnet and assign public IP
    # (We'll add this feature next!)
)
```

**Note**: Currently, ComputeInstance only deploys to private subnet. We need to add a `subnet_type` parameter to support public subnet deployment.

### Option 2: Use OCI Bastion Service

OCI provides a managed bastion service:

```bash
# Create a bastion using OCI CLI
oci bastion bastion create \
    --bastion-type STANDARD \
    --compartment-id <compartment-ocid> \
    --target-subnet-id <public-subnet-id> \
    --name "ociblocks-bastion"

# Then create a session to your compute instance
```

### Option 3: Temporarily Modify Instance (Development Only)

**⚠️ Not recommended for production!**

You can temporarily modify the instance to have a public IP:

1. In the OCI Console, go to your instance
2. Stop the instance
3. Detach the primary VNIC
4. Create a new VNIC in the public subnet with a public IP
5. Start the instance

### Option 4: Use VPN or FastConnect

If you have OCI VPN or FastConnect configured, you can connect directly to the private IP.

## Part 5: Connecting via SSH (Once You Have Access)

### Via Bastion Host (Most Common)

```bash
# Get the private IP from Pulumi output
WEB_SERVER_IP=$(pulumi stack output web_server_private_ip)
BASTION_PUBLIC_IP="<bastion-public-ip>"

# Method 1: SSH with jump host
ssh -i ~/.ssh/ociblocks_key -J opc@$BASTION_PUBLIC_IP opc@$WEB_SERVER_IP

# Method 2: Two-step SSH
# Step 1: SSH to bastion
ssh -i ~/.ssh/ociblocks_key opc@$BASTION_PUBLIC_IP

# Step 2: From bastion, SSH to web server (need to copy key to bastion)
ssh -i ~/.ssh/ociblocks_key opc@$WEB_SERVER_IP
```

### Via OCI Bastion Service

```bash
# Create a managed SSH session
oci bastion session create-managed-ssh \
    --bastion-id <bastion-ocid> \
    --target-resource-id <instance-ocid> \
    --target-os-username opc \
    --ssh-public-key-file ~/.ssh/ociblocks_key.pub

# Then use the provided SSH command
```

## Part 6: Once Connected - Mount the Data Volume

After you SSH into the instance, mount the attached block volume:

```bash
# SSH into the instance
ssh -i ~/.ssh/ociblocks_key opc@<instance-ip>

# List available block devices
lsblk

# You should see something like:
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
# sda      8:0    0   50G  0 disk           (boot volume)
# └─sda1   8:1    0   50G  0 part /
# sdb      8:16   0  100G  0 disk           (data volume - NOT MOUNTED)

# Create filesystem on the data volume (ONLY DO THIS ONCE!)
sudo mkfs.ext4 /dev/sdb

# Create mount point
sudo mkdir /data

# Mount the volume
sudo mount /dev/sdb /data

# Make mount persistent across reboots
echo '/dev/sdb /data ext4 defaults,_netdev,nofail 0 2' | sudo tee -a /etc/fstab

# Verify it's mounted
df -h /data

# You can now use /data for your application data
```

## Quick Reference Commands

### Generate SSH Key
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/ociblocks_key -C "ociblocks-compute"
```

### Configure Pulumi
```bash
pulumi config set ssh_key "$(cat ~/.ssh/ociblocks_key.pub)"
```

### Deploy
```bash
cd /home/opc/source/OCIblocks/test
pulumi up
```

### Get Instance IP
```bash
pulumi stack output web_server_private_ip
```

### SSH via Bastion (Jump Host)
```bash
ssh -i ~/.ssh/ociblocks_key -J opc@<bastion-ip> opc@<instance-private-ip>
```

## Troubleshooting

### "Permission denied (publickey)"
- Make sure you're using the correct private key: `-i ~/.ssh/ociblocks_key`
- Check key permissions: `chmod 600 ~/.ssh/ociblocks_key`
- Verify the correct public key was set in Pulumi: `pulumi config get ssh_key`

### "Connection timed out"
- Instance is in private subnet - you need a bastion or VPN
- Check security rules allow SSH (port 22)
- Verify the instance is running: check OCI Console

### "Connection refused"
- Instance might still be booting - wait a minute and try again
- SSH service might not be running - check via OCI Console serial console

## Next Steps

To make connecting easier, consider implementing:
1. **Bastion Host block** - Dedicated jump box in public subnet
2. **VPN block** - Site-to-site VPN for direct private network access
3. **Update ComputeInstance** - Add option to deploy to public subnet with public IP

Would you like me to implement a Bastion Host block next?
