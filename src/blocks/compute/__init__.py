"""Compute building blocks for OCIBlocks.

Provides two components for deploying OCI compute resources into a
:class:`~blocks.vcn.network.Vcn`:

:class:`~blocks.compute.instance.ComputeInstance`
    A single VM with an attached block volume and optional SSH key
    auto-generation.  Deployed to the VCN's private subnet with a minimal
    SSH security rule added automatically.

:class:`~blocks.compute.bastion.Bastion`
    An OCI Bastion Service endpoint attached to the VCN's private subnet,
    enabling time-limited SSH sessions without exposing instances directly to
    the internet.

Typical usage::

    from blocks.vcn import Vcn
    from blocks.compute import ComputeInstance, Bastion

    vcn = Vcn(name="lab", compartment_id=compartment_id, stack_name="prod")

    instance = ComputeInstance(
        name="web",
        compartment_id=compartment_id,
        vcn=vcn,
    )

    bastion = Bastion(
        name="mgmt",
        compartment_id=compartment_id,
        vcn=vcn,
        client_cidr_block_allow_list=["203.0.113.0/24"],
    )
"""

from .instance import ComputeInstance
from .bastion import Bastion

__all__ = ["ComputeInstance", "Bastion"]
