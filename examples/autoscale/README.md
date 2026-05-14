# Autoscale Example

Deploys a horizontally-scalable web tier with an OCI Load Balancer, Instance Pool, and CPU-based autoscaling. Instances run nginx and are bootstrapped via cloud-init.

## What Gets Created

- VCN with public, private, secure, and management subnets
- OCI Load Balancer (public, in the public subnet)
- Instance Configuration (template for pool members)
- Instance Pool (in the private subnet, 1–3 instances)
- Autoscaling Configuration (scales out above 80% CPU, scales in below 20% CPU)
- Security list rules for HTTP load balancer ingress and backend forwarding

## Architecture

```
Internet → Load Balancer (public subnet, port 80)
               ↓
         Instance Pool (private subnet)
         [nginx on each instance]
```

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
| `image_ocid` | Yes | — | Compute image OCID for pool instances |
| `vcn_cidr_block` | No | `10.0.0.0/18` | CIDR block for the VCN |
| `ssh_key` | No | _(auto-generated)_ | SSH public key to deploy to instances |

## Deploy

```bash
cd examples/autoscale

# Create a new stack
pulumi stack init dev

# Set required config
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set image_ocid <your-image-ocid>

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
pulumi stack output web_pool_ssh_private_key --show-secrets > ~/.ssh/oci_pool
chmod 600 ~/.ssh/oci_pool
```

## Scaling Policy

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU utilization | > 80% | Add 1 instance |
| CPU utilization | < 20% | Remove 1 instance |
| Cooldown | — | 300 seconds between scaling events |

Min instances: **1** — Max instances: **3**

## Test the Load Balancer

```bash
LB_IP=$(pulumi stack output web_pool_lb_ip)
curl http://$LB_IP/
```

Each response shows the hostname of the instance that served the request.

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `cidr_block` | VCN CIDR block |
| `public_subnet_id` | OCID of the public subnet |
| `private_subnet_id` | OCID of the private subnet |
| `secure_subnet_id` | OCID of the secure subnet |
| `management_subnet_id` | OCID of the management subnet |
| `web_pool_lb_ip` | Public IP of the load balancer |
| `web_pool_lb_id` | OCID of the load balancer |
| `web_pool_pool_id` | OCID of the instance pool |
| `web_pool_ssh_private_key` | _(secret)_ Private key, only present when auto-generated |

## Teardown

```bash
pulumi destroy
```
