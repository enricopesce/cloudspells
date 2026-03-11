"""VCN + ComputeInstance test — deploys a single compute instance in a VCN."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi
from blocks.vcn import Vcn, SUBNET_PUBLIC
from blocks.compute.instance import ComputeInstance

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
ssh_key: str | None = config.get("ssh_key")


# Create VCN
vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# ComputeInstance adds security rules and calls finalize_network()
web_server: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    subnet=SUBNET_PUBLIC,
)

vcn.export()
web_server.export()
