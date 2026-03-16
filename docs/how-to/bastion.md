# How to Use a Bastion for Private Access

Instances in the private or secure subnet have no public IP. The `Bastion` block provisions the **OCI Bastion service** — a managed, audited jump host — to give you SSH access to those instances without exposing them to the internet.

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

## Add a Bastion to a stack

Declare the `Bastion` block **after** the instance so the VCN is already finalised and the private subnet exists:

```python
from providers.oci.bastion import Bastion
from providers.oci.compute import ComputeInstance
from providers.oci.network import Vcn
from providers.oci.nsg import Nsg
from providers.oci.roles import APP_SERVER

vcn = Vcn("lab", compartment_id=compartment_id)

app_nsg = Nsg("app-server", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

instance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    nsg=app_nsg,
    os_name="ubuntu",
)

# Declare Bastion after ComputeInstance so finalize_network() has already run
bastion = Bastion(
    name="mgmt",
    compartment_id=compartment_id,
    vcn=vcn,
    max_session_ttl_in_seconds=10800,          # 3 hours (default)
    client_cidr_block_allow_list=["0.0.0.0/0"],  # restrict to your IP in production
)

vcn.export()
instance.export()
bastion.export()
```

`Bastion` attaches to the **private subnet** automatically. No subnet argument needed.

---

## Deploy

```bash
pulumi up
```

Note the bastion OCID from the outputs:

```bash
pulumi stack output mgmt_bastion_id
pulumi stack output web_server_id
```

---

## Create a session

Sessions are ephemeral (max 3-hour TTL) and created on demand via the OCI CLI. There is no persistent tunnel — you request access when needed and it expires automatically.

### Managed SSH session (recommended)

A managed SSH session lets you SSH directly to the instance's private IP. OCI handles key injection — no need to manage known_hosts entries.

```bash
oci bastion session create-managed-ssh \
    --bastion-id $(pulumi stack output mgmt_bastion_id) \
    --target-resource-id $(pulumi stack output web_server_id) \
    --target-os-username ubuntu \
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
