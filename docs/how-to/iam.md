# How to Set Up IAM Principals and Admin Groups

This guide shows you how to grant compute instances access to OCI services using instance principals, and how to delegate compartment administration to a team.

## When to use this

- Your compute instances or OKE node pools need to call OCI APIs (Object Storage, Vault, Container Registry) without embedding credentials.
- You want to delegate full compartment management to a team without granting tenancy-level access.

---

## Instance principal for compute workloads

`ComputeInstancePrincipal` creates a dynamic group matching all instances in a compartment, plus an IAM policy granting caller-specified permissions.

```python
from cloudspells.providers.oci.iam import ComputeInstancePrincipal

principal = ComputeInstancePrincipal(
    name="app",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
    grants=[
        "read secret-family",     # fetch DB password from Vault
        "read object-family",     # read app config from Object Storage
    ],
)
principal.export()
```

Each entry in `grants` is a `"<verb> <resource-type>"` fragment in OCI's policy language. The spell assembles the full statement:

```text
Allow dynamic-group <stack>-app-dg to read secret-family in compartment id <cid>
```

If you omit `grants`, the defaults are `["read object-family", "read secret-family"]`.

### Why `tenancy_id` is required

OCI creates dynamic groups at the tenancy root compartment level. The workload compartment is used only for policy scoping. Both OCIDs must be supplied.

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
from cloudspells.providers.oci.iam import ComputeInstancePrincipal, OkeNodePrincipal
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

vcn = Vcn("prod", compartment_id=compartment_id)
nsg = Nsg("app", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

# IAM — no VCN dependency, can be declared in any order.
principal = ComputeInstancePrincipal(
    name="app",
    compartment_id=compartment_id,
    tenancy_id=tenancy_id,
    grants=["read secret-family", "read object-family"],
)

instance = ComputeInstance(
    name="web",
    compartment_id=compartment_id,
    vcn=vcn,
    image_id=image_id,
    nsg=nsg,
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
| `ComputeInstancePrincipal` | `grants` | `["read object-family", "read secret-family"]` | OCI policy verb+resource fragments |
| `BackupBucket` | `retention_days` | `90` | Retention before deletion |
| `CompartmentAdminGroup` | _(none)_ | — | Group is created empty; add users post-deploy |
