# Automated SSH Key Management

The ComputeInstance block now supports **automated SSH key generation**. You have two options:

## Option 1: Auto-Generate SSH Keys (Recommended for Quick Start)

Don't set the `ssh_key` config - keys will be automatically generated during deployment.

```bash
cd /home/opc/source/OCIblocks/test

# Don't set ssh_key - it will auto-generate
pulumi up
```

### Get the Generated Keys

After deployment, the private key is exported as a Pulumi secret:

```bash
# View all outputs (private key is hidden)
pulumi stack output

# Save the private key to a file
pulumi stack output ssh_private_key --show-secrets > ~/.ssh/ociblocks_$(pulumi stack --show-name)
chmod 600 ~/.ssh/ociblocks_$(pulumi stack --show-name)

# Get the connection command
pulumi stack output ssh_connection_command
```

### Connect to Your Instance

```bash
# Get the private IP
INSTANCE_IP=$(pulumi stack output web_server_private_ip)

# SSH (assuming you have a bastion or VPN)
ssh -i ~/.ssh/ociblocks_$(pulumi stack --show-name) opc@$INSTANCE_IP
```

## Option 2: Use Your Own SSH Key

Provide your existing SSH public key via config:

```bash
cd /home/opc/source/OCIblocks/test

# Option A: Set directly
pulumi config set ssh_key "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC... your-comment"

# Option B: Read from file
pulumi config set ssh_key "$(cat ~/.ssh/id_rsa.pub)"

# Deploy
pulumi up
```

### Connect with Your Key

```bash
# Get the private IP
INSTANCE_IP=$(pulumi stack output web_server_private_ip)

# SSH with your private key
ssh -i ~/.ssh/id_rsa opc@$INSTANCE_IP
```

## Complete Example Workflow

### Auto-Generated Keys (Zero Setup)

```bash
cd /home/opc/source/OCIblocks/test

# 1. Deploy (no SSH key config needed)
pulumi up

# 2. Save the generated private key
pulumi stack output ssh_private_key --show-secrets > ~/.ssh/ociblocks_key
chmod 600 ~/.ssh/ociblocks_key

# 3. Get instance IP
INSTANCE_IP=$(pulumi stack output web_server_private_ip)

# 4. SSH (via bastion or VPN)
ssh -i ~/.ssh/ociblocks_key opc@$INSTANCE_IP
```

### Your Own Key

```bash
cd /home/opc/source/OCIblocks/test

# 1. Set your SSH key
pulumi config set ssh_key "$(cat ~/.ssh/id_rsa.pub)"

# 2. Deploy
pulumi up

# 3. Get instance IP
INSTANCE_IP=$(pulumi stack output web_server_private_ip)

# 4. SSH (via bastion or VPN)
ssh -i ~/.ssh/id_rsa opc@$INSTANCE_IP
```

## Code Example

### Auto-Generate Keys

```python
# __main__.py
web_server = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn_network,
    stack_name=pulumi.get_stack(),
    # ssh_public_key=None  # Omit or set to None - auto-generates
)

# Keys are exported automatically
pulumi.export("ssh_private_key", pulumi.Output.secret(web_server.get_ssh_private_key()))
```

### Use Your Own Key

```python
# __main__.py
config = pulumi.Config()
my_key = config.require("ssh_key")

web_server = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn_network,
    stack_name=pulumi.get_stack(),
    ssh_public_key=my_key  # Provide your key
)
```

## Outputs Reference

After deployment, these outputs are available:

| Output | Description | Command |
|--------|-------------|---------|
| `ssh_public_key` | Public key (always available) | `pulumi stack output ssh_public_key` |
| `ssh_private_key` | Private key (only if auto-generated) | `pulumi stack output ssh_private_key --show-secrets` |
| `ssh_connection_command` | Ready-to-use connection instructions | `pulumi stack output ssh_connection_command` |
| `web_server_private_ip` | Instance private IP | `pulumi stack output web_server_private_ip` |

## Security Notes

### Auto-Generated Keys

✅ **Pros:**
- Zero configuration - just run `pulumi up`
- Keys are unique per instance
- Private key stored encrypted in Pulumi state
- Perfect for dev/test environments

⚠️ **Important:**
- Private key is in Pulumi state - protect your state backend!
- For production, consider using your own keys or secrets manager
- The private key is marked as `secret` in Pulumi

### Your Own Keys

✅ **Pros:**
- You control the keys
- Can use existing key management workflows
- Keys never stored in Pulumi state

⚠️ **Notes:**
- You need to manage the private key yourself
- Make sure you don't lose the private key!

## Troubleshooting

### "Permission denied (publickey)"

If using auto-generated keys:
```bash
# Re-download the private key
pulumi stack output ssh_private_key --show-secrets > ~/.ssh/ociblocks_key
chmod 600 ~/.ssh/ociblocks_key
```

If using your own key:
```bash
# Verify the correct public key was set
pulumi config get ssh_key

# Check your private key permissions
chmod 600 ~/.ssh/id_rsa
```

### "Connection timed out"

The instance is in a **private subnet** - you need:
- A bastion host in the public subnet, OR
- OCI Bastion Service session, OR
- VPN/FastConnect to the VCN

See the main README for bastion setup options.

## Next Steps

To make SSH access easier:
1. Implement **Bastion Host block** - Jump box in public subnet
2. Add **subnet type parameter** to ComputeInstance - Allow public subnet deployment
3. Integrate with **OCI Secrets Manager** - Store keys in OCI Vault
