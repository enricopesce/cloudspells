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

The `INTERNET_EDGE` role registers the inbound TCP security list rules for
the public subnet.  No manual security list or NSG rule calls needed.

## Configuration

Required:

- `compartment_ocid` — OCID of the target compartment.

Optional:

- `ssh_key` — SSH public key installed on the VM.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import HTTP, HTTPS, SSH, Nsg
from cloudspells.providers.oci.roles import INTERNET_EDGE
from cloudspells.providers.oci.volume import VolumeSpec

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
# INTERNET_EDGE: public subnet, accepts HTTP/HTTPS/SSH from 0.0.0.0/0.

web_nsg: Nsg = Nsg(
    "web-server",
    role=INTERNET_EDGE,
    ports=[HTTP, HTTPS, SSH],
    vcn=vcn,
    compartment_id=compartment_id,
)

# ── Step 3 — Compute instance ─────────────────────────────────────────────────
#
# nsg= infers subnet=SUBNET_PUBLIC from the INTERNET_EDGE role.

web_server: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    image_id=config.require("image_ocid"),
    ssh_public_key=ssh_key,
    nsg=web_nsg,
    volumes=[
        VolumeSpec(size_in_gbs=100, label="data"),
        VolumeSpec(size_in_gbs=200, label="logs", vpus_per_gb=VolumeSpec.PERF_LOW),
    ],
)

vcn.export()
web_server.export()
