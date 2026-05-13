# How to Share a VCN Across Stacks

Share a single VCN across multiple Pulumi stacks using `VcnRef`.

By default, each CloudSpells stack owns its own VCN. For larger deployments you often want a single shared network managed by one stack — a **platform stack** — and multiple service stacks that deploy into it without recreating it.

`VcnRef` is not a generic OCI VCN import mechanism. It only references VCNs created by CloudSpells and exported with the CloudSpells OCI VCN schema. The source stack must publish the standard `Vcn.export()` outputs, including `cloudspells_network_schema` and `cloudspells_network_profiles`.

`VcnRef` is a read-only handle to a VCN owned by another stack. Every spell that accepts `Vcn` also accepts `VcnRef`, so service stacks need no changes when you split them.

---

## When to use VcnRef

Use `VcnRef` when:

- Multiple services (OKE, compute, databases) share the same network
- The network lifecycle differs from the application lifecycle — you want to update services without touching network resources
- You have a platform team that owns networking and application teams that own services

Do **not** use `VcnRef` for small single-stack deployments. The complexity of a split is only worthwhile when stacks genuinely have different owners or lifecycles.

---

## Step 1 — Create the VCN stack

Deploy the VCN standalone so it exports all its subnet OCIDs and CIDRs:

```python
# platform/vcn/__main__.py
from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn

config = Config()
vcn = Vcn(
    name="lab",
    compartment_id=config.require("compartment_ocid"),
)
vcn.export()   # exports vcn_id, *_subnet_id, *_subnet_cidr, *_security_list_id
```

```bash
cd platform/vcn
pulumi stack init platform/dev
pulumi config set compartment_ocid ocid1.compartment.oc1..aaaa...
pulumi up
```

Note the stack reference string. Its format depends on your state backend:

| Backend | Format |
|---------|--------|
| Pulumi Cloud | `<org>/<project>/<stack>` e.g. `acme/platform/dev` |
| Local file | `<project>/<stack>` e.g. `blocks-vcn/dev` |

---

## Step 2 — Reference the VCN from a service stack

```python
# services/app/__main__.py
from cloudspells.core import Config
from cloudspells.providers.oci.network import VcnRef
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

config = Config()
compartment_id = config.require("compartment_ocid")
vcn_stack = config.require("vcn_stack")

# VcnRef reads live outputs from the platform stack — no network resources created
vcn = VcnRef.from_stack_reference(vcn_stack)
app_nsg = Nsg("app-server", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

instance = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    nsg=app_nsg,      # carries the referenced VCN into ComputeInstance
)

instance.export()
```

```bash
cd services/app
pulumi stack init services/dev
pulumi config set compartment_ocid ocid1.compartment.oc1..aaaa...
pulumi config set vcn_stack blocks-vcn/dev   # or acme/platform/dev on Pulumi Cloud
pulumi up
```

---

## What VcnRef does and does not do

| | `Vcn` | `VcnRef` |
|---|-------|---------|
| Creates network resources | Yes | No |
| Accepts arbitrary OCI VCNs | No | No |
| Validates CloudSpells schema | Owns schema | Requires exported schema |
| Network profiles | Installs and exports profiles | Requires pre-exported profiles |
| `add_security_rules()` | Accumulates rules | Raises `RuntimeError` for non-empty rules |
| `finalize_network()` | Materialises subnets | No-op (deliberate) |
| Subnet CIDR accessors | Returns computed `Output[str]` | Returns cross-stack `Output[str]` |
| Usable with spells | Yes | Yes — with conditions (see below) |

`VcnRef.add_security_rules()` raises a `RuntimeError` only when non-empty rule lists are passed — it cannot modify the security lists of a network it does not own. Empty `SecurityRules()` is accepted as a no-op. The error message lists the non-empty rule sets that were requested so you know exactly what to add.

**This means security rules required by a spell must already exist in the source CloudSpells VCN stack before you deploy that spell against a `VcnRef`.** The workflow is:

1. In the source VCN stack, include the spell you intend to deploy here (even if it is a placeholder), so its rules are written to the security lists.
2. Run `pulumi up` on the source stack.
3. Deploy the spell against the `VcnRef` in this stack.

In practice this is straightforward: the platform team owns the VCN stack and provisions the baseline security rules; application teams deploy spells against the `VcnRef` knowing the rules are already in place.

---

## OKE with VcnRef

OKE requires subnet-level security-list rules. Because `VcnRef` is read-only, those rules must be installed in the source VCN stack before the OKE stack references it:

```python
# platform/vcn/__main__.py
vcn = Vcn(name="platform", compartment_id=compartment_id)
vcn.enable_oke_profile(kubectl_allowed_cidrs=["203.0.113.0/24"])
vcn.export()
```

```python
# services/oke/__main__.py
vcn = VcnRef.from_stack_reference("org/platform/prod")
cluster = OkeCluster(
    name="app",
    compartment_id=compartment_id,
    vcn=vcn,
    kubernetes_version="v1.32.1",
    node_pools=[pool],
    kubectl_allowed_cidrs=["203.0.113.0/24"],
)
```

The `kubectl_allowed_cidrs` list must match between the source VCN profile and the OKE stack. If it does not match, `OkeCluster` fails with a required network profile error.

---

## Updating the VCN stack later

Because `VcnRef` only reads exported outputs, changes to the VCN stack (adding new subnets, changing CIDRs) are reflected in service stacks automatically on their next `pulumi up`. No changes to service stack code are needed.

If you delete or rename a VCN output that a service stack depends on, `pulumi preview` on the service stack will show a failure. Fix the VCN stack exports before running `pulumi up` on services.

---

## Outputs consumed by VcnRef

`VcnRef.from_stack_reference()` reads these specific outputs from the source stack. All are exported automatically by `vcn.export()`:

| Output key | Used for |
|------------|---------|
| `vcn_id` | Spell attach points |
| `cidr_block` | CIDR calculations |
| `public_subnet_id` | `SUBNET_PUBLIC` placement |
| `private_subnet_id` | `SUBNET_PRIVATE` placement |
| `secure_subnet_id` | `SUBNET_SECURE` placement |
| `management_subnet_id` | `SUBNET_MANAGEMENT` placement |
| `public_subnet_cidr` | Security rule generation |
| `private_subnet_cidr` | Security rule generation |
| `secure_subnet_cidr` | Security rule generation |
| `management_subnet_cidr` | Security rule generation |
| `public_security_list_id` | Security list attach points |
| `private_security_list_id` | Security list attach points |
| `secure_security_list_id` | Security list attach points |
| `management_security_list_id` | Security list attach points |
| `drg_id` | DRG attach points (required output key; value is `None` when no DRG is attached) |
| `cloudspells_network_schema` | CloudSpells VCN compatibility contract |
| `cloudspells_network_profiles` | Pre-installed network profiles available to service stacks |

All listed output keys must exist in the source stack or `VcnRef.from_stack_reference()` will fail. `drg_id` is exported explicitly with value `None` when no DRG is attached. All are exported automatically by `vcn.export()`.
