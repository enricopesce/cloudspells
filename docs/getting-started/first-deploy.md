# First Deploy

This guide creates a new CloudSpells project from scratch and deploys a Virtual Cloud Network (VCN) — the foundation for every CloudSpells architecture. You will end up with a fully-wired 4-tier network in OCI: public, private, secure, and management subnets, all gateways, and correct routing — from a single Python call.

## What gets created

```
VCN  10.0.0.0/18
│
├── private     10.0.0.0/19    ← NAT GW + Service GW  (app servers, K8s nodes)
├── secure      10.0.32.0/20   ← Service GW only       (databases, secrets)
├── public      10.0.48.0/21   ← Internet GW           (load balancers)
└── management  10.0.56.0/21   ← Service GW only       (monitoring, bastion)
```

Three gateways (Internet, NAT, Service), four route tables, four security lists, four subnets.

---

## Step 1 — Find your compartment OCID

In the OCI Console, navigate to **Identity & Security → Compartments** and copy the OCID of the compartment where you want to deploy.

It looks like: `ocid1.compartment.oc1..aaaa...`

---

## Step 2 — Create a new project directory

```bash
mkdir my-vcn
cd my-vcn
```

---

## Step 3 — Create the project files

**`Pulumi.yaml`** — the Pulumi project descriptor:

```yaml
name: my-vcn
runtime:
  name: python
  options:
    virtualenv: .venv
description: My first CloudSpells VCN
```

**`requirements.txt`** — Python dependencies:

```
cloudspells-oci
```

**`__main__.py`** — the infrastructure program:

```python
from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn

config = Config()
compartment_id = config.require("compartment_ocid")

vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

vcn.export()
```

Two lines of infrastructure code create a production-grade, fully-routed network. There are no subnet CIDRs to calculate, no route tables to attach, no gateways to wire — CloudSpells handles all of it.

---

## Step 4 — Initialise a Pulumi stack

```bash
pulumi stack init dev
```

Pulumi will create a `.venv` and install `requirements.txt` automatically on the first `pulumi up`. To install dependencies now:

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

---

## Step 5 — Set required configuration

```bash
pulumi config set compartment_ocid ocid1.compartment.oc1..aaaa...
```

That is the only required value. The VCN CIDR is fixed inside the spell at `10.0.0.0/18` by default. To use a different range, pass `cidr_block=` directly to `Vcn(...)` in your Python program:

```python
vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
    cidr_block="10.10.0.0/16",
)
```

CloudSpells delegates CIDR validation to OCI — any valid RFC 1918 CIDR is accepted.

---

## Step 6 — Preview the changes

```bash
pulumi preview
```

You should see roughly 17 resources planned: 1 VCN, 1 default security list, 3 gateways (IGW + NAT + Service), 4 route tables, 4 security lists, and 4 subnets.

---

## Step 7 — Deploy

```bash
pulumi up
```

Confirm when prompted. Deployment typically takes 2–4 minutes.

---

## Step 8 — Inspect the outputs

```bash
pulumi stack output
```

You will see the OCIDs and CIDRs for every subnet and security list, for example:

```
vcn_id                     ocid1.vcn.oc1.eu-frankfurt-1...
private_subnet_id          ocid1.subnet.oc1...
public_subnet_id           ocid1.subnet.oc1...
secure_subnet_id           ocid1.subnet.oc1...
management_subnet_id       ocid1.subnet.oc1...
...
```

These outputs are consumed automatically when another stack references this VCN via `VcnRef.from_stack_reference()`.

---

## Teardown

To destroy the resources when you are done:

```bash
pulumi destroy
```

---

## What's next

- [Add a compute instance →](../tutorials/compute.md) — deploy a VM into this VCN
- [Share a VCN across stacks →](../how-to/vcnref.md) — use `VcnRef` to reference this VCN from another project
- [Deploy an OKE cluster →](../tutorials/oke.md) — run Kubernetes on top of this network
