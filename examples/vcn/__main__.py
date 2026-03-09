"""Standalone VCN — deploys only a VCN with subnets and gateways.

All outputs are consumed by ``examples/import-vcn`` via
``VcnRef.from_stack_reference()``.
"""

import pulumi
from blocks.vcn.network import Vcn

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")

vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# No service block to trigger finalize, so call it manually
vcn.finalize_network()
vcn.export()