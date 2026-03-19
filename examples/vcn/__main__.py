"""Standalone VCN — deploys only a VCN with subnets and gateways.

All outputs are consumed by `examples/import-vcn` via
`VcnRef.from_stack_reference()`.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.network import Vcn

config = Config()
compartment_id: str = config.require("compartment_ocid")

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

vcn.export()
