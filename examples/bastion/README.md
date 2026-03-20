# Bastion Example

Deploys a private compute instance accessible only through an OCI managed Bastion service. No public IP is assigned to the instance — all SSH access goes through the Bastion.

## What Gets Created

- VCN with public and private subnets
- Compute instance in the private subnet (no public IP)
- OCI Bastion service attached to the private subnet
- SSH key pair (auto-generated if not provided)
- Security list rules allowing SSH from the public subnet to the private subnet

## Architecture

```
Internet → Bastion (public subnet) → Port-forwarding session → Instance (private subnet)
```

The Bastion acts as a managed jump host. You create a session through the OCI Console or CLI and tunnel your SSH connection through it.

## Prerequisites

- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed
- OCI credentials configured (`~/.oci/config`)
- Python virtual environment set up from the repository root:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | — | OCI compartment OCID |
| `vcn_cidr_block` | No | `10.0.0.0/16` | CIDR block for the VCN |
| `ssh_key` | No | _(auto-generated)_ | SSH public key to deploy to the instance |

## Deploy

```bash
cd examples/bastion

# Create a new stack
pulumi stack init dev

# Set required config
pulumi config set compartment_ocid <your-compartment-ocid>

# Optional: provide your SSH public key (skip to auto-generate)
pulumi config set ssh_key "$(cat ~/.ssh/id_dsa.key.pub)"

# Preview changes
pulumi preview

# Deploy
pulumi up
```

## SSH Key Behaviour

- If `ssh_key` is **not set** (or left empty), an RSA key pair is auto-generated and the private key is stored as a secret Pulumi output.
- If `ssh_key` **is set**, your provided public key is used and no private key is exported.

### Retrieve an auto-generated private key

```bash
pulumi stack output ssh_private_key --show-secrets > ~/.ssh/oci_bastion
chmod 600 ~/.ssh/oci_bastion
```

## Connecting via Bastion

1. Get the outputs:
   ```bash
   pulumi stack output bastion_endpoint
   pulumi stack output instance_private_ip
   ```

2. Create a Bastion session (OCI CLI):
   ```bash
   oci bastion session create-port-forwarding \
     --bastion-id $(pulumi stack output bastion_id) \
     --target-private-ip $(pulumi stack output instance_private_ip) \
     --target-port 22 \
     --session-ttl 3600
   ```

3. Follow the SSH proxy command provided in the session details to connect.

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `public_subnet_id` | OCID of the public subnet |
| `private_subnet_id` | OCID of the private subnet |
| `instance_id` | OCID of the compute instance |
| `instance_private_ip` | Private IP of the instance |
| `bastion_id` | OCID of the Bastion service |
| `bastion_endpoint` | Bastion endpoint hostname |
| `ssh_public_key` | Public key deployed to the instance |
| `ssh_private_key` | _(secret)_ Private key, only present when auto-generated |

## Teardown

```bash
pulumi destroy
```
