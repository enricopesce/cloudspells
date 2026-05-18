# How to Deploy a Load Balancer

This guide shows you how to deploy internet-facing HTTPS and internal HTTP load balancers using the CloudSpells load balancer spells.

## When to use this

- You need to terminate TLS at the edge and route HTTPS traffic to backend instances.
- You need an internal service-to-service load balancer reachable only from within the VCN.
- You want HTTP-to-HTTPS redirect handled automatically.

---

## Internet-facing HTTPS load balancer

`LoadBalancer` creates a public-facing load balancer in the VCN public subnet with TLS termination and automatic HTTP-to-HTTPS redirect.

```
Internet
   │  HTTP 80 → 301 → HTTPS 443
   ▼
┌──────────────────────────────────────────┐
│ Public subnet  ← Internet Gateway        │
│  LoadBalancer (flexible 10-100 Mbps)     │
│    ├─ HTTPS:443 → TLS termination        │
│    └─ HTTP:80  → 301 redirect            │
│                                          │
│ Private subnet                           │
│  Backend instances ← port 8080           │
└──────────────────────────────────────────┘
```

### Prerequisites

Upload a TLS certificate to the OCI Load Balancer service before deploying. Note the certificate name — you will pass it as `certificate_name`.

### Code

```python
from cloudspells.providers.oci.loadbalancer import LoadBalancer
from cloudspells.providers.oci.network import Vcn

vcn = Vcn(name="prod", compartment_id=compartment_id)

lb = LoadBalancer(
    name="web-frontend",
    compartment_id=compartment_id,
    vcn=vcn,
    certificate_name="my-tls-cert",
    backend_port=8080,
    health_check_path="/healthz",
)
lb.export()
```

`LoadBalancer` registers VCN security-list rules and calls
`finalize_network()` during construction. Declare any other spell that must add
rules to the same live `Vcn` before the load balancer. After finalization,
`Vcn.add_security_rules()` raises for new non-empty rule sets.

### What gets created

- 1 flexible-shape Load Balancer (public subnet, public IP)
- 1 BackendSet (ROUND_ROBIN, HTTP health check on `backend_port`)
- 1 RuleSet (HTTP-to-HTTPS 301 redirect)
- 2 Listeners (HTTPS:443 with SSL termination, HTTP:80 with redirect)
- Security list rules: TCP 80 + 443 ingress on public subnet, backend port egress to private subnet

### Adding backends

Backends are registered separately — either via `oci.loadbalancer.Backend` resources in your Pulumi program, or via the OCI Console/CLI after deployment:

```bash
# Backend set name follows the CloudSpells pattern: {stack}-{spell-name}-bs
# e.g. for name="web-frontend" on stack "dev": dev-web-frontend-bs
oci lb backend create \
    --load-balancer-id $(pulumi stack output web_frontend_lb_id) \
    --backend-set-name <stack>-web-frontend-bs \
    --ip-address 10.0.0.10 \
    --port 8080
```

---

## Internal load balancer

`InternalLoadBalancer` creates a private load balancer in the VCN private subnet. No public IP is assigned.

```python
from cloudspells.providers.oci.loadbalancer import InternalLoadBalancer
from cloudspells.providers.oci.network import Vcn

vcn = Vcn(name="prod", compartment_id=compartment_id)

ilb = InternalLoadBalancer(
    name="api-gateway",
    compartment_id=compartment_id,
    vcn=vcn,
    backend_port=8080,
)
ilb.export()
```

`InternalLoadBalancer` follows the same rule: it registers its private subnet
rules, then finalizes the VCN. Declare rule-registering dependencies first.

### What gets created

- 1 flexible-shape Load Balancer (private subnet, `is_private=True`)
- 1 BackendSet (ROUND_ROBIN, HTTP health check)
- 1 Listener (HTTP:80)
- Security list rules: TCP 80 ingress from VCN CIDR, backend port egress within private subnet

---

## Composition order

The first spell that calls `finalize_network()` materializes the VCN security
lists and subnets. Later calls are no-ops, but later attempts to add new VCN
security-list rules fail. For a live `Vcn`, construct all NSGs, Bastion
components, and other rule-registering dependencies before the load balancer
spell that finalizes the network.

Do not use separate live `LoadBalancer` and `InternalLoadBalancer` declarations
against the same unfinalized `Vcn` as an order-independent pattern. Each spell
registers its own VCN rules and finalizes during construction.

---

## Outputs

| Output | Description |
|--------|-------------|
| `{name}_lb_id` | Load balancer OCID |
| `{name}_lb_ip` | Public VIP (LoadBalancer) or private VIP (InternalLoadBalancer) |

---

## Configuration reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `certificate_name` | _(required, LoadBalancer only)_ | Pre-uploaded TLS certificate name |
| `backend_port` | `80` | Port backends listen on |
| `health_check_path` | `"/health"` | HTTP path for health checks |
