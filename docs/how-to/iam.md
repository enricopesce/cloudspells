# How to Set Up IAM Principals and Admin Groups

This guide shows you how to grant compute instances access to OCI services using instance principals, and how to delegate compartment administration to a team.

## When to use this

- Your compute instances or OKE node pools need to call OCI APIs (Object Storage, Vault, Container Registry) without embedding credentials.
- You want to delegate full compartment management to a team without granting tenancy-level access.

---

## Instance principal for compute workloads

`ComputeInstancePrincipal` creates a dynamic group matching selected compute instance OCIDs, plus an IAM policy granting explicit permissions.

```python
from cloudspells.providers.oci.iam import ComputeInstancePrincipal, IamGrant

principal = ComputeInstancePrincipal(
    name="app",
    tenancy_id=tenancy_id,
    compartment_id=compartment_id,
    instance_ids=[
        "ocid1.instance.oc1..aaaa...",
    ],
    grants=[
        IamGrant.read_secrets(),  # fetch DB password from Vault
        IamGrant.read_objects(),  # read app config from Object Storage
    ],
)
principal.export()
```

Each entry in `grants` is an `IamGrant`. Use named helpers for common CloudSpells access patterns, or `IamGrant.raw("<verb> <resource-type>")` when OCI IAM exposes a permission CloudSpells does not model. The spell assembles the full statement:

```text
Allow dynamic-group id <dynamic_group_ocid> to read secret-family in compartment id <cid>
```

If you omit `grants`, the defaults are `IamGrant.read_objects()` and `IamGrant.read_secrets()`.

When the principal is declared in the same stack as CloudSpells compute instances, pass the objects directly instead of raw OCIDs:

```python
principal = ComputeInstancePrincipal(
    name="app",
    tenancy_id=tenancy_id,
    instances=[web],
    grants=[IamGrant.read_secrets(), IamGrant.read_objects()],
)
```

### Why `tenancy_id` is required

OCI creates dynamic groups at the tenancy root compartment level. The workload compartment is used only for policy scoping. When you pass `instances=[...]`, CloudSpells derives the policy compartment from the first instance. When you pass `instance_ids=[...]`, you must also pass `compartment_id=...` because raw OCIDs do not carry their compartment.

---

## Instance principal for OKE nodes

`OkeNodePrincipal` is a specialised variant with a fixed grant set covering the full OKE node operational permission set:

```python
from cloudspells.providers.oci.iam import OkeNodePrincipal

oke_principal = OkeNodePrincipal(
    name="k8s",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
)
oke_principal.export()
```

The policy grants:

- `manage instance-family`
- `use virtual-network-family`
- `manage load-balancers`
- `use volume-family`
- `read repos`

No `grants` parameter is needed or accepted.

`OkeNodePrincipal` currently follows OCI's compartment-scoped node principal pattern and matches all compute instances in `compartment_id`. Deploy OKE nodes in a compartment dedicated to that cluster or node tier until CloudSpells grows a worker-node defined-tag boundary.

---

## Compartment admin group for operators

`CompartmentAdminGroup` creates an IAM group (initially empty) with `manage all-resources` scoped to the workload compartment:

```python
from cloudspells.providers.oci.iam import CompartmentAdminGroup

admin = CompartmentAdminGroup(
    name="ops-team",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
)
admin.export()
```

After deployment, add users to the group via the OCI CLI:

```bash
oci iam group add-user \
    --group-id $(pulumi stack output ops_team_group_id) \
    --user-id <user-ocid>
```

---

## Combining principals with compute and OKE spells

A typical production stack grants instance principal access alongside the workload:

```python
from cloudspells.providers.oci.iam import ComputeInstancePrincipal, IamGrant, OkeNodePrincipal
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

vcn = Vcn("prod", compartment_id=compartment_id)
nsg = Nsg("app", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

instance = ComputeInstance(
    name="web",
    compartment_id=compartment_id,
    image_id=image_id,
    nsg=nsg,
)

principal = ComputeInstancePrincipal(
    name="app",
    tenancy_id=tenancy_id,
    instances=[instance],
    grants=[IamGrant.read_secrets(), IamGrant.read_objects()],
)

principal.export()
instance.export()
```

The instance picks up the principal automatically at runtime via OCI's instance metadata service — no code or credential injection is needed on the VM.

---

## Outputs

| Spell | Outputs after `export()` |
|-------|-------------------------|
| `ComputeInstancePrincipal` | `{name}_dynamic_group_id`, `{name}_policy_id` |
| `OkeNodePrincipal` | `{name}_dynamic_group_id`, `{name}_policy_id` |
| `CompartmentAdminGroup` | `{name}_group_id`, `{name}_policy_id` |

---

## Configuration reference

| Spell | Parameter | Default | Description |
|-------|-----------|---------|-------------|
| `ComputeInstancePrincipal` | `instances` | _(none)_ | CloudSpells compute instances that should be dynamic-group members |
| `ComputeInstancePrincipal` | `instance_ids` | _(none)_ | Existing compute instance OCIDs; requires `compartment_id` |
| `ComputeInstancePrincipal` | `grants` | `IamGrant.read_objects()`, `IamGrant.read_secrets()` | Explicit `IamGrant` values; use `IamGrant.raw(...)` for custom OCI grant fragments |
| `CompartmentAdminGroup` | _(none)_ | — | Group is created empty; add users post-deploy |
