"""Bastion Service building block for OCIBlocks.

Provides :class:`Bastion`, which creates an OCI Bastion Service endpoint
attached to the VCN's private subnet.  The Bastion enables time-limited SSH
sessions to private-subnet resources without requiring a public-facing jump
host.

Key behaviours
--------------
* Creates one ``oci.bastion.Bastion`` of type ``STANDARD``.
* Adds a TCP port-22 ingress rule to the VCN private security list when the
  network has not yet been finalised.
* If the network is already finalised (e.g. because a
  :class:`~blocks.compute.instance.ComputeInstance` or
  :class:`~blocks.autoscale.workload.ScalableWorkload` was constructed first),
  the existing SSH rule is reused and no duplicate rule is added.
* Session access is controlled at the Bastion level via
  ``client_cidr_block_allow_list``; the security-list rule allows all sources
  because OCI Bastion uses dynamically-assigned managed IPs.

Sessions are ephemeral (max 3 h TTL) and are not managed by this block.
Create them on demand via the OCI CLI::

    oci bastion session create-managed-ssh \\
        --bastion-id <bastion_id> \\
        --target-resource-id <instance_id> \\
        --target-os-username opc \\
        --ssh-public-key-file ~/.ssh/id_rsa.pub
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from core.abstractions.bastion import AbstractBastion
from providers.oci.network import Vcn


class Bastion(BaseResource, AbstractBastion):
    """OCI Bastion Service for secure SSH access to private-subnet resources.

    Creates an OCI managed Bastion attached to the VCN's private subnet,
    enabling time-limited SSH sessions without exposing instances directly to
    the internet.

    Resources created:

    * One ``oci.bastion.Bastion`` of type ``STANDARD``.

    Security rules added to the VCN (only when the network is not yet
    finalised):

    * Private subnet ingress: TCP port 22 from ``0.0.0.0/0``.  OCI Bastion
      uses managed, randomly-assigned source IPs; restrict client access via
      *client_cidr_block_allow_list* instead.

    Attributes:
        vcn: The :class:`~blocks.vcn.network.Vcn` this Bastion is attached to.
        bastion: The underlying ``oci.bastion.Bastion`` resource.
        bastion_id: ``pulumi.Output[str]`` of the Bastion OCID.
        bastion_endpoint: ``pulumi.Output[str]`` of the Bastion's private
            endpoint IP address (used as a ProxyJump target in SSH config).

    Usage::

        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")

        instance = ComputeInstance(
            name="web",
            compartment_id=comp_id,
            vcn=vcn,
        )

        bastion = Bastion(
            name="mgmt",
            compartment_id=comp_id,
            vcn=vcn,
            client_cidr_block_allow_list=["203.0.113.0/24"],
        )

        pulumi.export("bastion_endpoint", bastion.get_bastion_endpoint())
    """

    vcn: Vcn
    bastion: oci.bastion.Bastion
    bastion_id: pulumi.Output[str]
    bastion_endpoint: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn,
        stack_name: str | None = None,
        max_session_ttl_in_seconds: int = 10800,
        client_cidr_block_allow_list: list[str] | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create an OCI Bastion Service endpoint.

        Args:
            name: Logical name for the Bastion (e.g. ``"mgmt"``).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: :class:`~blocks.vcn.network.Vcn` instance whose private
                subnet the Bastion will be attached to.
            stack_name: Pulumi stack name.  Defaults to
                ``pulumi.get_stack()`` when ``None``.
            max_session_ttl_in_seconds: Maximum lifetime of a single Bastion
                session in seconds.  Minimum ``1800`` (30 min), maximum
                ``10800`` (3 h).  Default: ``10800``.
            client_cidr_block_allow_list: List of IPv4 CIDR blocks from which
                Bastion session creation is permitted.  Defaults to
                ``["0.0.0.0/0"]`` (unrestricted – restrict in production).
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:compute:Bastion", name, compartment_id, stack_name, opts)

        self.vcn = vcn

        if client_cidr_block_allow_list is None:
            client_cidr_block_allow_list = ["0.0.0.0/0"]

        # Add SSH ingress rule and finalise only when the network has not yet
        # been finalised.  When used alongside ComputeInstance or
        # ScalableWorkload (which already add an SSH rule and finalise), skip
        # rule-addition and use the existing finalised network directly.
        if not self.vcn._security_lists_finalized:
            self._add_bastion_security_rules()
            self.vcn.finalize_network()

        assert self.vcn.private_subnet is not None, (
            "VCN private subnet must exist. Construct ComputeInstance or "
            "ScalableWorkload before Bastion, or call vcn.finalize_network() first."
        )

        bastion_name = self.create_resource_name("bastion")
        self.bastion = oci.bastion.Bastion(
            bastion_name,
            bastion_type="STANDARD",
            compartment_id=self.compartment_id,
            target_subnet_id=self.vcn.private_subnet.id,
            name=bastion_name,
            max_session_ttl_in_seconds=max_session_ttl_in_seconds,
            client_cidr_block_allow_lists=client_cidr_block_allow_list,
            freeform_tags=self.create_freeform_tags(bastion_name, "bastion"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.bastion_id = self.bastion.id

        self.register_outputs({
            "bastion_id": self.bastion.id,
            "bastion_endpoint": self.bastion.private_endpoint_ip_address,
        })

    def _add_bastion_security_rules(self) -> None:
        """Add SSH ingress rule to the VCN private security list.

        OCI Bastion sessions originate from managed, randomly-assigned source
        IPs, so the rule must allow ``0.0.0.0/0`` on port 22.  Client access
        is restricted at the Bastion level via ``client_cidr_block_allow_list``.

        Must be called *before* :meth:`~blocks.vcn.network.Vcn.finalize_network`.
        Constructing :class:`Bastion` before any block that triggers finalisation
        (e.g. :class:`~blocks.compute.instance.ComputeInstance`) ensures the
        correct ordering.
        """
        self.vcn.add_security_list_rules(
            private_ingress=[
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="SSH access from OCI Bastion service to private subnet instances",
                    protocol="6",  # TCP
                    source="0.0.0.0/0",
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        min=22,
                        max=22,
                    ),
                ),
            ]
        )

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export standard Bastion stack outputs.

        Publishes the Bastion OCID and private endpoint IP under keys
        derived from the block's logical name.

        Example::

            bastion = Bastion(name="mgmt", ...)
            bastion.export()
            # Exports: mgmt_bastion_id, mgmt_bastion_endpoint
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_bastion_id", self.get_bastion_id())
        pulumi.export(f"{prefix}_bastion_endpoint", self.get_bastion_endpoint())

    def get_bastion_id(self) -> pulumi.Output[str]:
        """Return the OCID of the Bastion resource.

        Returns:
            ``pulumi.Output[str]`` resolving to the Bastion OCID.
        """
        return self.bastion.id

    def get_bastion_endpoint(self) -> pulumi.Output[str]:
        """Return the private endpoint IP of the Bastion.

        Use this address as a ``ProxyJump`` target in your SSH client
        configuration to tunnel SSH connections to private-subnet instances.

        Returns:
            ``pulumi.Output[str]`` resolving to the Bastion private endpoint
            IP address.
        """
        return self.bastion.private_endpoint_ip_address

    def get_access_endpoint(self) -> pulumi.Output[str]:
        """Return the access endpoint for SSH proxy sessions.

        Satisfies :meth:`~core.abstractions.bastion.AbstractBastion.get_access_endpoint`.
        Delegates to :meth:`get_bastion_endpoint`.

        Returns:
            ``pulumi.Output[str]`` resolving to the Bastion private endpoint
            IP address.
        """
        return self.get_bastion_endpoint()


__all__ = ["Bastion"]
