# Load Balancer Example

Deploys a VCN and an internet-facing HTTPS load balancer in the public subnet. HTTP traffic on port 80 is automatically redirected to HTTPS (301). TLS is terminated at the load balancer using a pre-uploaded certificate; backends receive plain HTTP on the configured backend port.

## What Gets Created

- VCN with public, private, secure, and management subnets
- OCI Load Balancer (flexible shape, 10–100 Mbps, public subnet)
- Backend set (ROUND_ROBIN, HTTP health check on `/health`)
- Rule set (HTTP → HTTPS 301 redirect)
- HTTPS listener on port 443 (TLS termination)
- HTTP listener on port 80 (redirect only)
- Security list rules: TCP 80 and 443 inbound, TCP 8080 to private subnet

## Architecture

```
Internet → :80  → Load Balancer → 301 redirect → client
Internet → :443 → Load Balancer (TLS termination)
                       ↓ :8080
               Backend instances (private subnet)
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
- A TLS certificate uploaded to the OCI Load Balancer service in your compartment. Upload via the OCI Console (**Networking → Load Balancers → Certificates**) or the OCI CLI, then pass the certificate name to the stack config.

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | — | OCI compartment OCID |
| `certificate_name` | Yes | — | Name of a TLS certificate pre-uploaded to OCI Load Balancer |
| `vcn_cidr_block` | No | `10.0.0.0/18` | CIDR block for the VCN |

## Deploy

```bash
cd examples/loadbalancer

# Create a new stack
pulumi stack init dev

# Set required config
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set certificate_name <your-certificate-name>

# Preview changes
pulumi preview

# Deploy
pulumi up
```

## Adding Backends

After deploying, register backend instances with the load balancer. The backend set name follows the pattern `{stack}-web-frontend-bs`. Register a backend via the OCI CLI:

```bash
oci lb backend create \
  --load-balancer-id <lb-ocid> \
  --backend-set-name <backend-set-name> \
  --ip-address <instance-private-ip> \
  --port 8080
```

Or use a raw Pulumi `oci.loadbalancer.Backend` resource in a consuming stack that reads the `web_frontend_lb_id` output.

## Outputs

| Output | Description |
|--------|-------------|
| `vcn_id` | OCID of the VCN |
| `cidr_block` | VCN CIDR block |
| `web_frontend_lb_id` | OCID of the load balancer |
| `web_frontend_lb_ip` | Public IP of the load balancer |

## Teardown

```bash
pulumi destroy
```

## Other Load Balancer Variants

- **`InternalLoadBalancer`** — private HTTP load balancer in the private subnet, reachable only from within the VCN. Useful for service-to-service routing without a public IP.
