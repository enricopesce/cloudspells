"""VCN + ComputeInstance example — deploys a VM with multiple block volumes."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

import pulumi
from providers.oci.network import Vcn
from providers.oci.compute import ComputeInstance
from providers.oci.volume import VolumeSpec

config: pulumi.Config = pulumi.Config()
compartment_id: str = config.require("compartment_ocid")
ssh_key: str | None = config.get("ssh_key")

# Create VCN
vcn: Vcn = Vcn(
    name="lab",
    compartment_id=compartment_id,
)

# ComputeInstance with multiple block volumes at different performance tiers.
# ComputeInstance adds security rules and calls finalize_network() automatically.
web_server: ComputeInstance = ComputeInstance(
    name="web-server",
    compartment_id=compartment_id,
    vcn=vcn,
    ssh_public_key=ssh_key,
    subnet=Vcn.SUBNET_PUBLIC,
    volumes=[
        VolumeSpec(size_in_gbs=100, label="data"),
        VolumeSpec(size_in_gbs=200, label="logs", vpus_per_gb=VolumeSpec.PERF_LOW),
    ],
)

vcn.export()
web_server.export()
