# How to Configure NSG Rules

CloudSpells uses **Network Security Groups (NSGs)** as the primary security mechanism. NSGs are role-based policies: one NSG represents the security posture and subnet tier for a class of resources (all web servers, all databases, all load balancers). The same NSG can be shared across many instances.

---

## Predefined roles

The fastest path is to use a predefined role constant. Roles encode which subnet tier a resource belongs to and what ambient network access it needs.

| Constant | Subnet tier | Egress | Typical use |
|----------|-------------|--------|-------------|
| `INTERNET_EDGE` | Public | Internet GW (via route table; no ambient NSG egress rules) | Load balancers, internet-facing VMs |
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

- Adds ambient ingress/egress rules to the NSG (service egress, NAT egress — depending on role)
- Accumulates the matching rules into the VCN's security list for that subnet tier
- Records the VCN and subnet tier so `ComputeInstance` can derive placement without explicit `vcn=` or `subnet=` arguments

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

All 24 port constants exported from `cloudspells.providers.oci.nsg`:

```python
# Web / access
from cloudspells.providers.oci.nsg import HTTP, HTTPS, HTTP_ALT, HTTPS_ALT, SSH, RDP
# HTTP=80, HTTPS=443, HTTP_ALT=8080, HTTPS_ALT=8443, SSH=22, RDP=3389

# Databases
from cloudspells.providers.oci.nsg import MYSQL, POSTGRES, ORACLE_DB, MSSQL, CASSANDRA, MONGODB
# MYSQL=3306, POSTGRES=5432, ORACLE_DB=1521, MSSQL=1433, CASSANDRA=9042, MONGODB=27017

# Caching / messaging
from cloudspells.providers.oci.nsg import REDIS, MEMCACHED, RABBITMQ, KAFKA
# REDIS=6379, MEMCACHED=11211, RABBITMQ=5672, KAFKA=9092

# File / directory
from cloudspells.providers.oci.nsg import NFS, SMB, LDAP, LDAPS
# NFS=2049, SMB=445, LDAP=389, LDAPS=636

# Search / observability
from cloudspells.providers.oci.nsg import ELASTICSEARCH
# ELASTICSEARCH=9200

# Mail
from cloudspells.providers.oci.nsg import SMTP, SMTPS
# SMTP=25, SMTPS=587

# DNS
from cloudspells.providers.oci.nsg import DNS
# DNS=53
```

Or pass a custom port number directly to an allow helper:

```python
my_nsg.allow_from_cidr("custom-api-in", 8443, "10.0.0.0/16")
```

---

## Attaching NSGs to instances

Pass the role-bearing NSG to `ComputeInstance` via the required `nsg=` argument. The VCN and subnet are derived from that NSG:

```python
from cloudspells.providers.oci.compute import ComputeInstance

web = ComputeInstance(
    name="web",
    compartment_id=compartment_id,
    image_id=image_id,
    nsg=web_nsg,   # VCN + SUBNET_PRIVATE derived from APP_SERVER role
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

lb  = ComputeInstance("lb",  compartment_id=compartment_id, image_id=image_id, nsg=lb_nsg)
web = ComputeInstance("web", compartment_id=compartment_id, image_id=image_id, nsg=web_nsg)
db  = ComputeInstance("db",  compartment_id=compartment_id, image_id=image_id, nsg=db_nsg)
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

## Allow Methods

For cases that `serves()` does not cover, use the individual allow methods directly:

| Method | Signature | Purpose |
|--------|-----------|---------|
| `allow_from_cidr` | `(label, port, cidr)` | Inbound TCP from a CIDR |
| `allow_udp_from_cidr` | `(label, port, cidr)` | Inbound UDP from a CIDR |
| `allow_to_cidr` | `(label, cidr)` | Outbound all-protocol egress to a CIDR |
| `allow_udp_to_cidr` | `(label, port, cidr)` | Outbound UDP to a CIDR |
| `allow_from_nsg` | `(label, nsg, port)` | Inbound TCP from another NSG |
| `allow_to_nsg` | `(label, nsg, port)` | Outbound TCP to another NSG |
| `allow_to_services` | `(label)` | Egress to Oracle Services CIDR (all protocols) |
| `allow_icmp_from_cidr` | `(label, cidr, icmp_type, code)` | Inbound ICMP from a CIDR |

All methods accept an optional `description` keyword argument for the OCI Console label.

```python
from cloudspells.providers.oci.nsg import INTERNET

# Allow inbound HTTPS from any IP
my_nsg.allow_from_cidr("https-in", HTTPS, INTERNET)

# Allow all-protocol outbound to a specific CIDR (on-premises VPN)
my_nsg.allow_to_cidr("vpn-out", "192.168.100.0/24")

# Allow ICMP type 3 code 4 (path-MTU discovery) from the internet
my_nsg.allow_icmp_from_cidr("pmtu-in", INTERNET, icmp_type=3, code=4)

# UDP DNS egress
from cloudspells.providers.oci.nsg import DNS
my_nsg.allow_udp_to_cidr("dns-out", DNS, "10.0.0.2/32")
```
