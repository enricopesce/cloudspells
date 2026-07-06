# Tutorial: Deploy a Landing Zone

This tutorial deploys the CloudSpells **foundation layer** — the reusable
architecture an environment needs *before* the first real workload — and then
puts a real service inside it. It uses the `LandingZone` spell, which composes
the four foundation concerns into one call:

- **Network** — 4-tier VCN (public / private / secure / management), all gateways and route tables
- **Audit** — VCN flow logs on every subnet tier, always on
- **Access** — OCI Bastion for session-based SSH, no public jump hosts
- **IAM baseline** — compartment admin group + `manage all-resources` policy

**What you will build:**

```
Internet
   │  (OCI Bastion service — no public IP on any instance)
   ▼
┌───────────────────────────────────────────────────────┐
│ LandingZone "foundation"                              │
│  Private subnet — NAT GW + Service GW routes          │
│   app-server  [app-nsg · APP_SERVER]                  │
│   foundation bastion  ← OCI Bastion service           │
│  Flow logs on every tier · compartment admin group    │
└───────────────────────────────────────────────────────┘
```

**What gets created:** 1 VCN (4 subnets + 3 gateways), 1 log group + 4 flow
logs, 1 Bastion, 1 IAM group + policy, 1 NSG, 1 private compute instance.

None of the foundation components is optional — they are the architecture.
You name the landing zone, pick a compartment, and state who may open Bastion
sessions.

---

## The layered model

CloudSpells separates infrastructure into two layers:

| Layer | Who owns it | Spells |
|-------|-------------|--------|
| **Foundation** | Platform team | `LandingZone` (or a standalone `Vcn`) |
| **Services** | Application teams | `ComputeInstance`, `OkeCluster`, `ScalableWorkload`, `LoadBalancer`, … |

The foundation is deployed once per environment and reused by every service.
Services can live in the **same stack** (this tutorial) or in **separate
workload stacks** that consume the foundation read-only via
`VcnRef.from_stack_reference()` — see
[Share a VCN Across Stacks](../how-to/vcnref.md).

---

## Prerequisites

- Completed [Installation](../getting-started/installation.md)
- OCI compartment OCID and tenancy OCID at hand
- Boot image OCID for the instance
- The CIDR of the network you administer from (office / VPN)

---

## Step 1 — Initialise the stack

```bash
cd examples/landing-zone-app

pulumi stack init dev
pulumi config set compartment_ocid     ocid1.compartment.oc1..example
pulumi config set tenancy_ocid         ocid1.tenancy.oc1..example
pulumi config set bastion_client_cidr  203.0.113.0/24
pulumi config set availability_domain  "IqDk:EU-FRANKFURT-1-AD-1"
pulumi config set image_ocid           ocid1.image.oc1..example
```

`bastion_client_cidr` is a deliberate required input: it states who may
create Bastion sessions, and that is a security decision the spell cannot
make for you. Pass `0.0.0.0/0` only when unrestricted access is intentional.

---

## Step 2 — Walk through the code

Open `examples/landing-zone-app/__main__.py`. It has three logical steps.

### 2a. Declare the foundation

```python
from cloudspells.providers.oci.landing_zone import LandingZone

lz = LandingZone(
    name="foundation",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
    allowed_client_cidrs=[bastion_client_cidr],
)
```

One call declares the entire foundation. `tenancy_id` is required because
the IAM baseline creates its group at tenancy level.

At this point **no subnet exists yet** — the landing zone follows the
CloudSpells accumulate-then-materialise contract, so services declared next
can still register security rules.

### 2b. Declare services inside it

```python
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

app_nsg = Nsg(
    "app-server",
    role=APP_SERVER,
    vcn=lz.vcn,
    compartment_id=compartment_id,
)

app = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    image_id=image_id,
    availability_domain=availability_domain,
    nsg=app_nsg,
)
```

`lz.vcn` is the foundation's network handle — pass it wherever a spell
accepts `vcn=`. The `APP_SERVER` role places the instance in the private
subnet with NAT + service egress; there is no public IP and no SSH ingress
rule from the internet, because management access is the Bastion's job.

### 2c. Materialise and export

```python
lz.export()
app.export()
```

`lz.export()` finalises the network (including every rule the services
registered), creates the Bastion, and publishes the full cross-stack
contract — the same keys a standalone `Vcn` exports, plus:

| Output | Meaning |
|--------|---------|
| `compartment_id` | Compartment the foundation lives in |
| `bastion_id`, `bastion_endpoint` | Session-based SSH access |
| `admin_group_id`, `admin_policy_id` | IAM baseline |
| `network_audit_log_group_id` | Flow-log group for compliance tooling |

!!! warning "Ordering"
    Declare services **between** `LandingZone(...)` and `lz.export()`.
    The Bastion SSH rule itself is pre-registered at construction time, so
    a service that finalises the network early (like `ComputeInstance`)
    can never lock the Bastion out — but new rule-owning spells cannot be
    added after the network is materialised.

---

## Step 3 — Deploy

```bash
pulumi up
```

---

## Step 4 — SSH into the private instance

The VM has no public IP. If you did not supply `ssh_key`, first retrieve the
auto-generated instance key:

```bash
pulumi stack output app_server_ssh_private_key --show-secrets > ~/.ssh/lz_app
chmod 600 ~/.ssh/lz_app
```

Then create a time-limited session through the Bastion (the session key is
your own — it secures the tunnel, not the instance login):

```bash
oci bastion session create-managed-ssh \
    --bastion-id $(pulumi stack output bastion_id) \
    --target-resource-id $(pulumi stack output app_server_id) \
    --target-os-username opc \
    --ssh-public-key-file ~/.ssh/id_rsa.pub
```

Follow the SSH proxy command from the session details, using
`-i ~/.ssh/lz_app` as the instance identity. Sessions expire after 3 hours
and can only be created from `bastion_client_cidr`.

---

## Going multi-stack

For real environments, deploy the foundation **alone** (see
[`examples/landing-zone`](https://github.com/enricopesce/cloudspells/tree/main/examples/landing-zone))
and let each workload team consume it from their own stack:

```python
# foundation stack — register the profiles your teams need before export()
lz = LandingZone(name="foundation", ...)
lz.vcn.enable_oke_profile(kubectl_allowed_cidrs=["203.0.113.0/24"])
Nsg("app-profile", role=APP_SERVER, vcn=lz.vcn, compartment_id=cid)
lz.export()
```

```python
# workload stack — read-only, validated at deploy time
vcn = VcnRef.from_stack_reference("acme/blocks-landing-zone/prod")
cluster = OkeCluster(name="app", vcn=vcn, compartment_id=cid, ...)
```

Workload spells fail fast when the foundation has not enabled the network
profile they need — the contract is checked, not assumed. Details in
[Share a VCN Across Stacks](../how-to/vcnref.md).

---

## Clean up

```bash
pulumi destroy
```

---

## Next steps

- [Share a VCN Across Stacks](../how-to/vcnref.md) — the cross-stack consumer side
- [Use a Bastion](../how-to/bastion.md) — session workflows in depth
- [Enable VCN Flow Logs](../how-to/network-logging.md) — what the audit layer captures
- [Set Up IAM Principals](../how-to/iam.md) — zero-credential access for the services you deploy inside
