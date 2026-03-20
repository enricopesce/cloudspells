# Autoscale Example

Deploys a horizontally-scalable web tier with an OCI Load Balancer, Instance Pool, and CPU-based autoscaling. Instances run nginx and are bootstrapped via cloud-init.

## What Gets Created

- VCN with public and private subnets
- OCI Load Balancer (public, in the public subnet)
- Instance Configuration (template for pool members)
- Instance Pool (in the private subnet, 1–3 instances)
- Autoscaling Configuration (scales out at 70% CPU, scales in at 30% CPU)
- Security list rules for HTTP (port 80) and SSH (port 22)

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
| `vcn_cidr_block` | No | `10.0.0.0/16` | CIDR block for the VCN |
| `ssh_key` | No | _(auto-generated)_ | SSH public key to deploy to instances |

## Deploy

```bash
cd examples/autoscale

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
pulumi stack output ssh_private_key --show-secrets > ~/.ssh/oci_pool
chmod 600 ~/.ssh/oci_pool
```

## Scaling Policy

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU utilization | > 70% | Add 1 instance |
| CPU utilization | < 30% | Remove 1 instance |
| Cooldown | — | 300 seconds between scaling events |

Min instances: **1** — Max instances: **3**

## Test the Load Balancer

```bash
LB_IP=$(pulumi stack output lb_ip)
curl http://$LB_IP/
```

Each response shows the hostname of the instance that served the request.

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `cidr_block` | VCN CIDR block |
| `lb_ip` | Public IP of the load balancer |
| `lb_id` | OCID of the load balancer |
| `pool_id` | OCID of the instance pool |
| `ssh_private_key` | _(secret)_ Private key, only present when auto-generated |

## Teardown

```bash
pulumi destroy
```
