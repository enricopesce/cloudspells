# How to Use a Bastion for Private Access

This guide shows you how to add the OCI Bastion service to a CloudSpells stack so you can SSH into private-subnet instances without a public IP or jump host.

## When to use this

- You have a `ComputeInstance` in the private or secure subnet and need SSH access for operations or debugging.
- You need a port-forwarding tunnel to a database or other TCP service in the private subnet.
- Compliance requires audited, time-limited access rather than a persistent jump host.

```
Internet
   │
   ▼  (OCI Bastion service — no public IP on instance)
┌──────────────────────────────────────────────────────┐
│ Private subnet  ← NAT GW + Service GW               │
│  instance  [APP_SERVER role]                         │
│  OCI Bastion service (attached to private subnet)    │
└──────────────────────────────────────────────────────┘
```

---

## Steps

### 1. Declare the Bastion before the compute instance

`Bastion` must be constructed **before** any spell that calls `finalize_network()` (such as `ComputeInstance`, `ScalableWorkload`, or `OkeCluster`). The Bastion needs to register its SSH ingress rule — TCP port 22 from `0.0.0.0/0` on the private security list — before the security list is materialised. If `ComputeInstance` is constructed first, `finalize_network()` will have already run and `Bastion` will raise a `RuntimeError`.

```python
from cloudspells.core import Config
from cloudspells.providers.oci.bastion import Bastion
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

config = Config()
compartment_id = config.require("compartment_ocid")

vcn = Vcn("lab", compartment_id=compartment_id)

app_nsg = Nsg("app-server", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

# Bastion comes BEFORE ComputeInstance — it must register its SSH rule first.
bastion = Bastion(
    name="mgmt",
    compartment_id=compartment_id,
    vcn=vcn,
    max_session_ttl_in_seconds=10800,            # 3 hours (default)
    client_cidr_block_allow_list=["0.0.0.0/0"],  # restrict to your IP in production
)

# ComputeInstance calls finalize_network() — Bastion rule is already registered.
instance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    image_id=config.require("image_ocid"),
    nsg=app_nsg,
)
```

`Bastion` attaches to the **private subnet** automatically. No subnet argument is needed.

### 2. Export the stack outputs

```python
vcn.export()
bastion.export()
instance.export()
```

### 3. Deploy

```bash
pulumi up
```

Note the required OCIDs from the outputs:

```bash
pulumi stack output mgmt_bastion_id
pulumi stack output web_server_id
```

---

## Create a session

Sessions are ephemeral (max 3-hour TTL) and created on demand via the OCI CLI. There is no persistent tunnel — you request access when needed and it expires automatically.

### Managed SSH session (recommended)

A managed SSH session lets you SSH directly to the instance's private IP. OCI handles key injection — no need to manage `known_hosts` entries.

```bash
oci bastion session create-managed-ssh \
    --bastion-id $(pulumi stack output mgmt_bastion_id) \
    --target-resource-id $(pulumi stack output web_server_id) \
    --target-os-username opc \
    --ssh-public-key-file ~/.ssh/id_rsa.pub \
    --session-ttl 3600
```

This returns a session OCID. Wait for it to become `ACTIVE` (typically 30–60 seconds):

```bash
oci bastion session get --session-id <session-ocid> --query 'data.{"state":"lifecycle-state"}'
```

Then connect using the SSH command printed in the session details:

```bash
oci bastion session get --session-id <session-ocid> --query 'data."ssh-metadata".command' --raw-output
```

Copy and run that command — it is a ready-to-use `ssh` invocation with all proxy settings pre-filled.

### Port-forwarding session (for non-SSH services)

To reach a database or other TCP service on the private subnet, use a port-forwarding session:

```bash
oci bastion session create-port-forwarding \
    --bastion-id $(pulumi stack output mgmt_bastion_id) \
    --target-private-ip $(pulumi stack output web_server_private_ip) \
    --target-port 5432 \
    --ssh-public-key-file ~/.ssh/id_rsa.pub
```

Once the session is `ACTIVE`, the SSH command in the session details sets up a local port forward you can connect to with `psql`, a database GUI, or any other client.

---

## Restrict client access

In production, limit the `client_cidr_block_allow_list` to your team's egress IP range:

```python
bastion = Bastion(
    name="mgmt",
    compartment_id=compartment_id,
    vcn=vcn,
    client_cidr_block_allow_list=["203.0.113.0/24"],  # your office / VPN CIDR
)
```

---

## Complete example

```python
from cloudspells.core import Config
from cloudspells.providers.oci.bastion import Bastion
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

config = Config()
compartment_id = config.require("compartment_ocid")

vcn = Vcn("lab", compartment_id=compartment_id)

app_nsg = Nsg("app-server", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

# Bastion must come before any spell that triggers finalize_network().
bastion = Bastion(
    name="mgmt",
    compartment_id=compartment_id,
    vcn=vcn,
    client_cidr_block_allow_list=["203.0.113.0/24"],  # restrict in production
)

instance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    image_id=config.require("image_ocid"),
    nsg=app_nsg,
)

vcn.export()
bastion.export()
instance.export()
```

---

## Configuration reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_session_ttl_in_seconds` | `10800` (3 h) | Maximum TTL for any session created through this bastion |
| `client_cidr_block_allow_list` | `["0.0.0.0/0"]` | Source CIDRs allowed to create sessions |

---

## Outputs

After `bastion.export()`:

| Output | Description |
|--------|-------------|
| `mgmt_bastion_id` | Bastion OCID — required for session creation |
| `mgmt_bastion_endpoint` | Private endpoint IP — used in the SSH proxy command |

(The prefix `mgmt` comes from `name="mgmt"` in the example above.)

---

## Security note

The OCI Bastion service authenticates users through your OCI IAM policy, not just SSH keys. Audit logs for every session (creation, connection, termination) are available in OCI Audit. For compliance-sensitive environments this is preferable to a self-managed jump host.
