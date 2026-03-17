# How to Configure NSG Rules

CloudSpells uses **Network Security Groups (NSGs)** as the primary security mechanism. NSGs are role-based policies: one NSG represents the security posture of a class of resources (all web servers, all databases, all load balancers). The same NSG can be shared across many instances, and one instance can hold multiple NSGs.

---

## Predefined roles

The fastest path is to use a predefined role constant. Roles encode which subnet tier a resource belongs to and what ambient network access it needs.

| Constant | Subnet tier | Egress | Typical use |
|----------|-------------|--------|-------------|
| `INTERNET_EDGE` | Public | None (entry point) | Load balancers, internet-facing VMs |
| `APP_SERVER` | Private | NAT + Services | Application servers, APIs |
| `DATABASE` | Secure | Services only | Databases, secret stores |
| `CACHE` | Private | NAT + Services | Redis, Kafka, Memcached |
| `MANAGEMENT` | Management | Services only | Monitoring agents, tooling |

```python
from cloudspells.providers.oci.nsg import Nsg, HTTP, HTTPS, SSH
from cloudspells.providers.oci.roles import INTERNET_EDGE, APP_SERVER, DATABASE

lb_nsg  = Nsg("load-balancer", role=INTERNET_EDGE, ports=[HTTP, HTTPS],
               vcn=vcn, compartment_id=compartment_id)

web_nsg = Nsg("web-backend",   role=APP_SERVER,
               vcn=vcn, compartment_id=compartment_id)

db_nsg  = Nsg("database",      role=DATABASE,
               vcn=vcn, compartment_id=compartment_id)
```

When you pass `role=`, CloudSpells automatically:

- Adds ambient ingress/egress rules to the NSG (ICMP path-MTU, service egress, NAT egress — depending on role)
- Accumulates the matching rules into the VCN's security list for that subnet tier
- Records the subnet tier so `ComputeInstance` can infer subnet placement without an explicit `subnet=` argument

---

## Declaring traffic relationships with `serves()`

`Nsg.serves(target, port)` generates the full bilateral rule set for a directed traffic relationship in a single call:

- Egress from this NSG to `target` on `port`
- Ingress on `target` from this NSG on `port`
- (By default) SSH management channel in both directions — omit with `with_ssh=False`
- Cross-subnet security list rules when the two NSGs are in different tiers

```python
# LB → web backend (port 8080) + SSH management
lb_nsg.serves(web_nsg, port=8080)

# Web backend → database (PostgreSQL) + SSH management
web_nsg.serves(db_nsg, port=5432)

# Data-only path — no SSH management channel
web_nsg.serves(db_nsg, port=6379, with_ssh=False)
```

### Why serves() instead of individual allow_* calls

A two-tier relationship (LB → app server) requires four NSG rules and potentially four security list rules. Writing them individually is tedious and error-prone — one missing rule causes a silent connectivity failure. `serves()` generates all required rules from the relationship intent.

---

## Port constants

```python
from cloudspells.providers.oci.nsg import SSH, HTTP, HTTPS, POSTGRES, MYSQL, ORACLE_DB, REDIS, KAFKA, NFS

# SSH=22, HTTP=80, HTTPS=443, POSTGRES=5432, MYSQL=3306
# ORACLE_DB=1521, REDIS=6379, KAFKA=9092, NFS=2049
```

Or construct a custom port:

```python
from cloudspells.providers.oci.nsg import tcp_port
my_port = tcp_port(8443)
```

---

## Attaching NSGs to instances

Pass the NSG to `ComputeInstance` via `nsg=`. The subnet is inferred from the role:

```python
from cloudspells.providers.oci.compute import ComputeInstance

web = ComputeInstance(
    name="web",
    compartment_id=compartment_id,
    vcn=vcn,
    nsg=web_nsg,   # subnet=SUBNET_PRIVATE inferred from APP_SERVER role
)
```

---

## Full three-tier example

```python
from cloudspells.providers.oci.nsg import Nsg, HTTP, HTTPS, SSH, POSTGRES
from cloudspells.providers.oci.roles import INTERNET_EDGE, APP_SERVER, DATABASE
from cloudspells.providers.oci.compute import ComputeInstance

# ── NSGs ──────────────────────────────────────────────────────────────────────

lb_nsg = Nsg(
    "load-balancer",
    role=INTERNET_EDGE,
    ports=[HTTP, HTTPS, SSH],
    vcn=vcn,
    compartment_id=compartment_id,
)

web_nsg = Nsg(
    "web-backend",
    role=APP_SERVER,
    vcn=vcn,
    compartment_id=compartment_id,
)

db_nsg = Nsg(
    "database",
    role=DATABASE,
    vcn=vcn,
    compartment_id=compartment_id,
)

# ── Relationships ─────────────────────────────────────────────────────────────

lb_nsg.serves(web_nsg, port=HTTP)       # LB → app server (port 80 + SSH)
web_nsg.serves(db_nsg, port=POSTGRES)   # app server → DB  (port 5432 + SSH)

# ── Instances ─────────────────────────────────────────────────────────────────

lb  = ComputeInstance("lb",  compartment_id=compartment_id, vcn=vcn, nsg=lb_nsg)
web = ComputeInstance("web", compartment_id=compartment_id, vcn=vcn, nsg=web_nsg)
db  = ComputeInstance("db",  compartment_id=compartment_id, vcn=vcn, nsg=db_nsg)
```

---

## Custom roles

If a predefined role does not match your use-case, compose one from `Role`:

```python
from cloudspells.providers.oci.roles import Role
from cloudspells.providers.oci.network import SUBNET_PRIVATE

# Private-tier proxy — internet + service egress, SSH delivered via Bastion
proxy_role = Role(
    subnet_tier=SUBNET_PRIVATE,
    egress_internet=True,
    egress_services=True,
    accept_management_ssh=False,   # SSH via Bastion, not upstream NSG
)

proxy_nsg = Nsg("proxy", role=proxy_role, vcn=vcn, compartment_id=compartment_id)
```

---

## Low-level rule methods

For cases that `serves()` does not cover, use the individual allow methods directly:

| Method | Purpose |
|--------|---------|
| `allow_from_cidr(name, port, cidr)` | Inbound TCP from a CIDR |
| `allow_to_cidr(name, port, cidr)` | Outbound TCP to a CIDR |
| `allow_from_nsg(name, nsg, port)` | Inbound TCP from another NSG |
| `allow_to_nsg(name, nsg, port)` | Outbound TCP to another NSG |
| `allow_to_services(name)` | Egress to Oracle Services CIDR |
| `allow_icmp_path_mtu_in(name)` | ICMP type 3 code 4 inbound |
| `allow_icmp_path_mtu_out(name)` | ICMP type 3 code 4 outbound |

```python
from cloudspells.providers.oci.nsg import INTERNET

# Allow inbound HTTPS from any IP
my_nsg.allow_from_cidr("https-in", HTTPS, INTERNET)

# Allow outbound to a specific CIDR (on-premises VPN)
my_nsg.allow_to_cidr("vpn-out", 443, "192.168.100.0/24")
```
