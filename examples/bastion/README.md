# Bastion Example

Deploys a private compute instance accessible only through an OCI managed Bastion service. No public IP is assigned to the instance — all SSH access goes through the Bastion.

## What Gets Created

- VCN with public, private, secure, and management subnets
- Role-bearing `APP_SERVER` NSG for private instance placement
- Compute instance in the private subnet (no public IP)
- OCI Bastion service attached to the private subnet
- SSH key pair (auto-generated if not provided)
- Bastion-owned SSH security-list rule registered before the VCN is finalized

## Architecture

```
Internet -> OCI Bastion service (private subnet) -> managed SSH session -> Instance (private subnet)
```

The Bastion service is an OCI-managed access point, not a VM jump host. The example constructs `Bastion` before `ComputeInstance` so the Bastion SSH rule is registered before `ComputeInstance` finalizes the VCN.

CloudSpells intentionally attaches OCI Bastion to the private subnet. The management tier remains reserved for monitoring, VPN/FastConnect, and other operations tooling that only needs OCI service-plane access.

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
| `availability_domain` | Yes | — | Availability Domain for the compute instance |
| `image_ocid` | Yes | — | Compute image OCID for the instance |
| `ssh_key` | No | _(auto-generated)_ | SSH public key to deploy to the instance |

## Deploy

```bash
cd examples/bastion

# Create a new stack
pulumi stack init dev

# Set required config
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set availability_domain "<availability-domain-name>"
pulumi config set image_ocid <your-image-ocid>

# Optional: provide your SSH public key (skip to auto-generate)
pulumi config set ssh_key "$(cat ~/.ssh/id_rsa.pub)"

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
pulumi stack output web_server_ssh_private_key --show-secrets > ~/.ssh/oci_bastion
chmod 600 ~/.ssh/oci_bastion
```

## Connecting via Bastion

1. Get the outputs:
   ```bash
   pulumi stack output mgmt_bastion_endpoint
   pulumi stack output web_server_private_ip
   ```

2. Create a managed SSH session (OCI CLI):
   ```bash
   oci bastion session create-managed-ssh \
     --bastion-id $(pulumi stack output mgmt_bastion_id) \
     --target-resource-id $(pulumi stack output web_server_id) \
     --target-os-username opc \
     --ssh-public-key-file ~/.ssh/id_rsa.pub
   ```

3. Follow the SSH proxy command provided in the session details to connect.

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `public_subnet_id` | OCID of the public subnet |
| `private_subnet_id` | OCID of the private subnet |
| `secure_subnet_id` | OCID of the secure subnet |
| `management_subnet_id` | OCID of the management subnet |
| `web_server_id` | OCID of the compute instance |
| `web_server_private_ip` | Private IP of the instance |
| `web_server_availability_domain` | Availability Domain used by the instance |
| `web_server_shape` | Compute shape |
| `web_server_fault_domain` | Fault domain, if set |
| `mgmt_bastion_id` | OCID of the Bastion service |
| `mgmt_bastion_endpoint` | Bastion private endpoint IP address |
| `web_server_ssh_public_key` | Public key deployed to the instance |
| `web_server_ssh_private_key` | _(secret)_ Private key, only present when auto-generated |

## Teardown

```bash
pulumi destroy
```
