"""VCN + ComputeInstance example — deploys an internet-facing VM with block volumes.

## Architecture

```
Internet
   │  HTTP 80 / HTTPS 443 / SSH 22
   ▼
┌─────────────────────────────────────────────────────┐
│ Public subnet (/19)  — Internet GW route            │
│  web-server  [web-nsg · INTERNET_EDGE]              │
└─────────────────────────────────────────────────────┘
```

The `INTERNET_EDGE` role is **explicit but compact**: the caller chooses a
public posture by attaching a role-bearing `Nsg` with declared edge ports.
That NSG carries both the VCN handle and the subnet tier, so `ComputeInstance`
does not accept separate `vcn=` or `subnet=` placement inputs.  No manual
`add_security_rules` or `finalize_network` calls are needed from the caller.

## Configuration

Required:

- `compartment_ocid` — OCID of the target compartment.
- `image_ocid` — OCID of the compute image to use.

Optional:

- `ssh_key` — SSH public key installed on the VM.
"""

import os
import sys

# Dev-only path scaffolding — not needed when packages are installed via `pip install -e`.
_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci import (
    INTERNET_EDGE,
    ComputeInstance,
    Nsg,
    Vcn,
    VolumeSpec,
)
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH

config = Config()
compartment_id: str = config.require("compartment_ocid")
ssh_key: str | None = config.get("ssh_key")

# ── Step 1 — VCN ──────────────────────────────────────────────────────────────

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# ── Step 2 — NSG role ─────────────────────────────────────────────────────────
#
# INTERNET_EDGE: public subnet, accepts the declared ports from 0.0.0.0/0.
# Nsg.__init__ registers matching VCN security list rules; ComputeInstance
# finalizes the NSG's VCN later.

web_nsg: Nsg = Nsg(
    "web-server",
    vcn=vcn,
    compartment_id=compartment_id,
    role=INTERNET_EDGE,
    ports=[HTTP, HTTPS, SSH],
)

# ── Step 3 — Compute instance ─────────────────────────────────────────────────
#
# nsg= carries both the VCN and the INTERNET_EDGE role, so the instance is
# placed in the public subnet and the NSG OCID is attached to the primary VNIC.
# availability_domain is auto-discovered (first AD); override via the
# availability_domain= kwarg if needed.

web_server: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    image_id=config.require("image_ocid"),
    ssh_public_key=ssh_key,
    nsg=web_nsg,
    volumes=[
        VolumeSpec(size_in_gbs=100, label="data"),
        VolumeSpec(size_in_gbs=200, label="logs", vpus_per_gb=VolumeSpec.PERF_LOW),
    ],
)

# Exported keys: vcn_id, vcn_cidr, public_subnet_id, private_subnet_id,
#                web_server_id, web_server_public_ip, web_server_private_ip,
#                web_server_availability_domain, web_server_shape, web_server_fault_domain.
vcn.export()
web_server.export()
