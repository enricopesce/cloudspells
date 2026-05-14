# How to Enable VCN Flow Logs

This guide shows you how to attach VCN Flow Logs to all subnet tiers for network audit and compliance using the `VcnFlowLogs` spell.

## When to use this

- You need visibility into accepted and rejected network traffic on every subnet.
- Compliance requires audit logging of all VCN traffic (PCI-DSS, CIS benchmarks).
- You want to debug connectivity issues between subnets or to/from the internet.

```
┌─────────────────────────────────────────────┐
│ VCN                                         │
│  Public subnet   ── flow-log-public ──┐     │
│  Private subnet  ── flow-log-private ─┤     │
│  Secure subnet   ── flow-log-secure ──┤     │
│  Management sub  ── flow-log-mgmt ────┘     │
│                          │                  │
│            ┌─────────────┴──────────┐       │
│            │  Log Group             │       │
│            │  {stack}-{name}-       │       │
│            │   network-audit        │       │
│            └────────────────────────┘       │
└─────────────────────────────────────────────┘
```

---

## Basic usage with a live VCN

When you pass a `Vcn`, the spell calls `finalize_network()` automatically and creates flow logs for all four subnet tiers:

```python
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.network_logging import VcnFlowLogs

vcn = Vcn(name="prod", compartment_id=compartment_id)

flow_logs = VcnFlowLogs(name="prod", vcn=vcn)
flow_logs.export()
```

`compartment_id` is inferred from the live `Vcn` — no need to pass it separately.
Because this finalizes the network, declare any NSGs, Bastion components, load
balancers, or other spells that need to register VCN security-list rules before
`VcnFlowLogs`.

---

## Cross-stack usage with VcnRef

When using a `VcnRef`, the spell attaches flow logs to the subnets exported by
the upstream stack. `compartment_id` must be supplied explicitly because
`VcnRef` does not carry a compartment ID:

```python
from cloudspells.providers.oci.network import VcnRef
from cloudspells.providers.oci.network_logging import VcnFlowLogs

vcn_ref = VcnRef.from_stack_reference("network-prod")

flow_logs = VcnFlowLogs(
    name="prod",
    vcn=vcn_ref,
    compartment_id=compartment_id,
)
flow_logs.export()
```

`VcnRef.from_stack_reference()` now requires all four CloudSpells subnet
outputs: public, private, secure, and management. Use `Vcn.export()` in the
source stack so the secure and management subnet IDs and CIDRs are present.
Only manually constructed `VcnRef` objects may omit secure or management
subnets; in that case the corresponding flow log attributes are `None`.

---

## Custom retention

OCI accepts only discrete retention values: `30`, `60`, `90`, `120`, `150`, `180` days. Any other value raises `ValueError`:

```python
flow_logs = VcnFlowLogs(
    name="prod",
    vcn=vcn,
    retention_duration=180,  # 6 months
)
```

The default is `90` days.

---

## Complete example

```python
from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.network_logging import VcnFlowLogs
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

config = Config()
compartment_id = config.require("compartment_ocid")

vcn = Vcn("prod", compartment_id=compartment_id)
nsg = Nsg("app", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

instance = ComputeInstance(
    name="web",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    nsg=nsg,
)

# ComputeInstance finalizes the VCN after the NSG has registered its rules.
# VcnFlowLogs can be declared after that and attaches logs to the created subnets.
flow_logs = VcnFlowLogs(name="prod", vcn=vcn, retention_duration=180)

vcn.export()
flow_logs.export()
instance.export()
```

---

## Outputs

| Output | Description |
|--------|-------------|
| `{name}_log_group_id` | OCID of the network-audit Log Group |

---

## Checking flow logs

After deployment, query flow logs via the OCI CLI:

```bash
oci logging search \
    --search-query "search \"$(pulumi stack output prod_log_group_id)\"" \
    --time-start 2024-01-01T00:00:00Z \
    --time-end 2024-01-02T00:00:00Z
```

Or view them in the OCI Console under **Logging > Log Groups**.

---

## Configuration reference

| Parameter | Default | Accepted values | Description |
|-----------|---------|-----------------|-------------|
| `retention_duration` | `90` | `30`, `60`, `90`, `120`, `150`, `180` | Log retention in days |
| `compartment_id` | inferred from `Vcn` | any OCID | Required when `vcn` is a `VcnRef` |
