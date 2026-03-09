"""VCN (Virtual Cloud Network) building block for OCIBlocks.

Provides :class:`~blocks.vcn.network.Vcn`, a high-level Pulumi component that
creates a complete OCI VCN with:

* Internet, NAT, and Service gateways.
* Public, private, and secure subnets (CIDRs auto-calculated from the VCN block).
* Route tables per tier — secure tier has no internet path (Service Gateway only).
* Security lists populated via the lazy-initialisation / builder pattern –
  other blocks (OKE, Compute, ScalableWorkload) add their rules *before*
  :meth:`~blocks.vcn.network.Vcn.finalize_network` creates the security lists
  and subnets.

Typical usage::

    from blocks.vcn import Vcn

    vcn = Vcn(name="lab", compartment_id=compartment_id, stack_name="prod")
    # ... attach other blocks that call vcn.add_security_list_rules() ...
    vcn.finalize_network()   # explicit call only needed for standalone VCNs
"""

from .network import Vcn, VcnRef, get_resources_by_tag, SUBNET_PUBLIC, SUBNET_PRIVATE, SUBNET_SECURE, SUBNET_MANAGEMENT, SubnetTier

__all__ = ["Vcn", "VcnRef", "get_resources_by_tag", "SUBNET_PUBLIC", "SUBNET_PRIVATE", "SUBNET_SECURE", "SUBNET_MANAGEMENT", "SubnetTier"]
