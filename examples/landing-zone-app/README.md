# Landing Zone + Application Example

Deploys the CloudSpells **layered model in one stack**: a `LandingZone`
foundation with a real application VM inside it. The VM lives in the private
subnet with **zero public surface** — no public IP, no SSH from the internet.
Management access goes exclusively through the landing zone's Bastion.

For the foundation-only, cross-stack variant see
[`examples/landing-zone`](../landing-zone/).

## What gets created

| Layer | Resources |
|-------|-----------|
| Foundation | 4-tier VCN + gateways, flow logs on every tier, OCI Bastion, compartment admin group |
| Service | 1 `APP_SERVER` NSG, 1 private compute instance, 1 data volume, 1 SSH key pair (auto-generated when `ssh_key` is omitted) |

## The ordering contract

Workload spells are declared **between** `LandingZone(...)` and
`lz.export()`:

```python
lz = LandingZone(name="foundation", ...)        # 1. foundation declared

app_nsg = Nsg("app-server", role=APP_SERVER,    # 2. services accumulate
              vcn=lz.vcn, compartment_id=cid)   #    their security rules
app = ComputeInstance(..., nsg=app_nsg)

lz.export()                                     # 3. network materialised,
                                                #    Bastion created
```

This is the standard CloudSpells accumulate-then-materialise pattern — the
landing zone pre-registers the Bastion SSH rule at construction, so the
ordering can never lock the Bastion out.

## Quick start

```bash
cd examples/landing-zone-app
pulumi stack init dev
pulumi config set compartment_ocid     <COMPARTMENT_OCID>
pulumi config set tenancy_ocid         <TENANCY_OCID>
pulumi config set bastion_client_cidr  203.0.113.0/24   # your office / VPN CIDR
pulumi config set availability_domain  <AVAILABILITY_DOMAIN>
pulumi config set image_ocid           <IMAGE_OCID>
pulumi up
```

## SSH into the private VM

The instance has no public IP. Open a session through the Bastion:

```bash
oci bastion session create-managed-ssh \
    --bastion-id $(pulumi stack output bastion_id) \
    --target-resource-id $(pulumi stack output app_server_id) \
    --target-os-username opc \
    --ssh-public-key-file ~/.ssh/id_rsa.pub
```

Sessions are time-limited (3 h max) and can only be created from
`bastion_client_cidr`.

## Clean up

```bash
pulumi destroy
```
