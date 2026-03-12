"""Compute building blocks for OCIBlocks.

Provides components for deploying OCI compute resources into a
:class:`~blocks.vcn.network.Vcn`:

:class:`~blocks.compute.instance.ComputeInstance`
    A single VM with one or more attached block volumes and optional SSH key
    auto-generation.  Deployed to the VCN's private subnet by default with a
    minimal SSH security rule added automatically.

:class:`~blocks.compute.volume.VolumeSpec`
    Typed descriptor for a single block volume to attach to a
    :class:`~blocks.compute.instance.ComputeInstance`.  Controls size,
    label, performance tier, and read-only flag.

:class:`~blocks.compute.bastion.Bastion`
    An OCI Bastion Service endpoint attached to the VCN's private subnet,
    enabling time-limited SSH sessions without exposing instances directly to
    the internet.

Typical usage::

    from blocks.vcn import Vcn
    from blocks.compute import ComputeInstance, VolumeSpec, Bastion

    vcn = Vcn(name="lab", compartment_id=compartment_id, stack_name="prod")

    instance = ComputeInstance(
        name="app",
        compartment_id=compartment_id,
        vcn=vcn,
        volumes=[
            VolumeSpec(size_in_gbs=100, label="data"),
            VolumeSpec(size_in_gbs=500, label="db",
                       vpus_per_gb=VolumeSpec.PERF_HIGH),
        ],
    )
"""

from .instance import ComputeInstance
from .bastion import Bastion
from .volume import VolumeSpec

__all__ = ["ComputeInstance", "Bastion", "VolumeSpec"]
