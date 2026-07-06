# Landing Zone Example

Deploys the CloudSpells **foundation layer** on its own: everything an
environment needs *before* the first real workload, in one spell.

This is the first half of the layered model — deploy the reusable foundation
once, then create services (OKE, VMs, autoscaling workloads) inside it from
the same stack or from separate workload stacks.

For the same-stack variant (foundation + application VM together) see
[`examples/landing-zone-app`](../landing-zone-app/).

## What gets created

| Component | Resources |
|-----------|-----------|
| Network | 4-tier VCN (public / private / secure / management), Internet + NAT + Service gateways, route tables, security lists |
| Audit | Log Group + one VCN flow log per subnet tier (always on, 90-day retention) |
| Access | OCI Bastion in the private subnet — session-based SSH, no public jump host |
| IAM baseline | Compartment admin group + `manage all-resources` policy |

None of these components is optional — they are the architecture. You name
the landing zone, pick a compartment, and state who may open Bastion
sessions. Everything else is fixed by design.

## Prerequisites

- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed
- OCI credentials configured at `~/.oci/config`
- Repo virtualenv built (`pip install -r requirements.txt` from the repo root)

## Quick start

```bash
cd examples/landing-zone
pulumi stack init prod
pulumi config set compartment_ocid    <COMPARTMENT_OCID>
pulumi config set tenancy_ocid        <TENANCY_OCID>
pulumi config set bastion_client_cidr 203.0.113.0/24   # your office / VPN CIDR
pulumi up
```

## Deploying services inside the foundation

### Same stack

Pass `lz.vcn` wherever a spell accepts `vcn=`, and declare workloads
*before* `lz.export()`:

```python
lz = LandingZone(name="foundation", ...)

app_nsg = Nsg("app", role=APP_SERVER, vcn=lz.vcn, compartment_id=compartment_id)
app = ComputeInstance(name="app-1", compartment_id=compartment_id,
                      image_id=image_id, nsg=app_nsg)

lz.export()
```

### Separate workload stacks (recommended)

`lz.export()` publishes the full CloudSpells network contract
(`cloudspells_network_schema` + `cloudspells_network_profiles`), so any
workload stack can consume the foundation read-only:

```python
vcn = VcnRef.from_stack_reference("<org>/blocks-landing-zone/prod")
cluster = OkeCluster(name="app", vcn=vcn, compartment_id=comp_id, ...)
```

Workload spells validate the contract at deploy time and fail fast when the
foundation has not enabled the network profile they need. Register profiles
in this stack before `lz.export()`:

```python
lz.vcn.enable_oke_profile(kubectl_allowed_cidrs=["203.0.113.0/24"])  # OKE
Nsg("app-profile", role=APP_SERVER, vcn=lz.vcn, compartment_id=cid)  # VMs
```

See `examples/import-vcn` for a complete consumer stack.

## Opening an SSH session through the Bastion

```bash
oci bastion session create-managed-ssh \
    --bastion-id $(pulumi stack output bastion_id) \
    --target-resource-id <instance_id> \
    --target-os-username opc \
    --ssh-public-key-file ~/.ssh/id_rsa.pub
```

## Stack outputs

Everything `examples/vcn` exports (the `VcnRef` contract), plus:

- `compartment_id` — compartment the foundation lives in
- `bastion_id`, `bastion_endpoint` — session-based SSH access
- `admin_group_id`, `admin_policy_id` — IAM baseline
- `network_audit_log_group_id` — flow-log group for compliance tooling

## Clean up

```bash
pulumi destroy
```
