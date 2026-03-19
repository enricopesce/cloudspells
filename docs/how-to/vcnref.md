# How to Share a VCN Across Stacks

By default, each CloudSpells stack owns its own VCN. For larger deployments you often want a single shared network managed by one stack — a **platform stack** — and multiple service stacks that deploy into it without recreating it.

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

config = Config()
compartment_id = config.require("compartment_ocid")
vcn_stack = config.require("vcn_stack")

# VcnRef reads live outputs from the platform stack — no network resources created
vcn = VcnRef.from_stack_reference(vcn_stack)

instance = ComputeInstance(
    name="app-server",
    compartment_id=compartment_id,
    vcn=vcn,          # identical API to a live Vcn
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
| `add_security_list_rules()` | Accumulates rules | Raises `RuntimeError` (deliberate) |
| `finalize_network()` | Materialises subnets | No-op (deliberate) |
| Subnet CIDR accessors | Returns computed `Output[str]` | Returns cross-stack `Output[str]` |
| Usable with spells | Yes | Yes — with conditions (see below) |

`VcnRef.add_security_list_rules()` raises a `RuntimeError` because `VcnRef` cannot modify the security lists of a network it does not own. The error message lists the rule sets that were requested so you know exactly what to add.

**This means security rules required by a spell must already exist in the source CloudSpells VCN stack before you deploy that spell against a `VcnRef`.** The workflow is:

1. In the source VCN stack, include the spell you intend to deploy here (even if it is a placeholder), so its rules are written to the security lists.
2. Run `pulumi up` on the source stack.
3. Deploy the spell against the `VcnRef` in this stack.

In practice this is straightforward: the platform team owns the VCN stack and provisions the baseline security rules; application teams deploy spells against the `VcnRef` knowing the rules are already in place.

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
| `drg_id` | DRG attach points (optional — `None` when no DRG) |

All fourteen outputs must exist in the source stack (except `drg_id`, which is `None` when no DRG is attached) or `VcnRef.from_stack_reference()` will fail. All are exported automatically by `vcn.export()`.
