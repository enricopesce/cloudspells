# Compute Example

Deploys a single internet-facing compute instance inside a CloudSpells VCN. The `INTERNET_EDGE` NSG role places the instance in the public subnet and opens HTTP, HTTPS, and SSH on the VNIC and matching VCN security list.

## What Gets Created

- VCN with public, private, secure, and management subnets
- Role-bearing NSG with `INTERNET_EDGE` posture
- Compute instance (`VM.Standard.E4.Flex`, 1 OCPU, 16 GB RAM by default)
- Attached `data` and `logs` block volumes
- SSH key pair (auto-generated if not provided)
- Security list rules for HTTP, HTTPS, and SSH on the public tier

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
| `image_ocid` | Yes | — | Compute image OCID for the instance |
| `ssh_key` | No | _(auto-generated)_ | SSH public key to deploy to the instance |

## Deploy

```bash
cd examples/compute

# Create a new stack
pulumi stack init dev

# Set required config
pulumi config set compartment_ocid <your-compartment-ocid>
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
pulumi stack output web_server_ssh_private_key --show-secrets > ~/.ssh/oci_instance
chmod 600 ~/.ssh/oci_instance
```

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `cidr_block` | VCN CIDR block |
| `public_subnet_id` | OCID of the public subnet |
| `private_subnet_id` | OCID of the private subnet |
| `secure_subnet_id` | OCID of the secure subnet |
| `management_subnet_id` | OCID of the management subnet |
| `web_server_id` | OCID of the compute instance |
| `web_server_public_ip` | Public IP of the instance |
| `web_server_private_ip` | Private IP of the instance |
| `web_server_availability_domain` | Availability Domain selected for the instance |
| `web_server_shape` | Compute shape |
| `web_server_fault_domain` | Fault domain, if set |
| `web_server_data_volume_id` | OCID of the attached block volume |
| `web_server_logs_volume_id` | OCID of the attached logs block volume |
| `web_server_ssh_public_key` | Public key deployed to the instance |
| `web_server_ssh_private_key` | _(secret)_ Private key, only present when auto-generated |

## Teardown

```bash
pulumi destroy
```
