r"""Bastion Service spell for CloudSpells.

Provides `Bastion`, which creates an OCI Bastion Service endpoint attached to
the VCN's private subnet.  The Bastion enables time-limited SSH sessions to
private-subnet resources without requiring a public-facing jump host.

Key behaviours:

- Creates one `oci.bastion.Bastion` of type `STANDARD`.
- Adds a TCP port-22 ingress rule to the VCN private security list when the
  network has not yet been finalised.
- If the network is already finalised (e.g. because a `ComputeInstance` or
  `ScalableWorkload` was constructed first), the existing SSH rule is reused
  and no duplicate rule is added.
- Session access is controlled at the Bastion level via
  `allowed_client_cidrs`; the security-list rule allows all sources
  because OCI Bastion uses dynamically-assigned managed IPs.

Sessions are ephemeral (max 3 h TTL) and are not managed by this spell.
Create them on demand via the OCI CLI:

```text
oci bastion session create-managed-ssh \\
    --bastion-id <bastion_id> \\
    --target-resource-id <instance_id> \\
    --target-os-username opc \\
    --ssh-public-key-file ~/.ssh/id_rsa.pub
```
"""

from __future__ import annotations

from collections.abc import Sequence

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.bastion import AbstractBastion
from cloudspells.core.base import BaseResource

from ._network_profiles import NETWORK_PROFILE_BASTION
from .network import Vcn, VcnRef

# OCI Bastion sessions always expire at 3 hours — the maximum the service
# allows.  Exposing a shorter TTL as a parameter would only create operational
# friction with no security benefit, since the session can always be terminated
# early.
_MAX_SESSION_TTL_SECONDS = 10800


class Bastion(BaseResource, AbstractBastion):
    """OCI Bastion Service for secure SSH access to private-subnet resources.

    Creates an OCI managed Bastion attached to the VCN's private subnet,
    enabling time-limited SSH sessions without exposing instances directly to
    the internet.

    Resources created:

    - One `oci.bastion.Bastion` of type `STANDARD`.

    Security rules added to the VCN (only when the network is not yet
    finalised):

    - Private subnet ingress: TCP port 22 from `0.0.0.0/0`.  OCI Bastion
      uses managed, randomly-assigned source IPs; restrict client access via
      `allowed_client_cidrs` instead.

    Attributes:
        vcn: The `Vcn` or `VcnRef` this Bastion is attached to.
        bastion: The underlying `oci.bastion.Bastion` resource.
        bastion_id: `pulumi.Output[str]` OCID of the Bastion resource.
        bastion_endpoint: `pulumi.Output[str]` private endpoint IP address
            of the Bastion.  Use this as a `ProxyJump` target in SSH config.

    Example:
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
        app_nsg = Nsg("app", role=APP_SERVER, vcn=vcn, compartment_id=comp_id)

        bastion = Bastion(
            name="mgmt",
            compartment_id=comp_id,
            vcn=vcn,
            allowed_client_cidrs=["203.0.113.0/24"],  # always required
        )

        instance = ComputeInstance(
            name="web",
            compartment_id=comp_id,
            image_id=image_id,
            nsg=app_nsg,
        )

        pulumi.export("bastion_endpoint", bastion.get_bastion_endpoint())
        ```
    """

    vcn: Vcn | VcnRef
    bastion: oci.bastion.Bastion
    bastion_id: pulumi.Output[str]
    bastion_endpoint: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        allowed_client_cidrs: Sequence[pulumi.Input[str]] | None = None,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create an OCI Bastion Service endpoint.

        Args:
            name: Logical name for the Bastion (e.g. `"mgmt"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` instance whose private subnet the Bastion
                will be attached to.
            allowed_client_cidrs: List of IPv4 CIDR blocks from which
                Bastion session creation is permitted.  Must be provided
                explicitly — passing `None` raises `ValueError`.  To
                permit all source IPs pass `["0.0.0.0/0"]`; in production
                environments supply a specific CIDR (e.g.
                `["203.0.113.0/24"]`).
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `allowed_client_cidrs` is `None`.  Always provide
                the list explicitly; pass `["0.0.0.0/0"]` to permit all
                source IPs when unrestricted access is intentional.
            RuntimeError: If the VCN network has already been finalised by
                another spell (e.g. `ComputeInstance`, `ScalableWorkload`,
                `OkeCluster`) and the Bastion SSH ingress rule was not
                registered before that finalisation. Construct `Bastion`
                before any spell that triggers `finalize_network()`.
        """
        super().__init__("custom:bastion:Bastion", name, compartment_id, stack_name, opts)

        self.vcn = vcn

        if allowed_client_cidrs is None:
            raise ValueError(
                f"Bastion '{name}': allowed_client_cidrs must be provided explicitly. "
                "To permit all source IPs (not recommended for production), pass "
                "allowed_client_cidrs=['0.0.0.0/0']."
            )

        # Register or require the Bastion network profile before finalising.
        # OCI Bastion sessions originate from randomly-assigned managed IPs, so
        # the source VCN must allow 0.0.0.0/0 on private-subnet TCP/22 while
        # actual session creation remains restricted by allowed_client_cidrs.
        network_profile_check: str | pulumi.Output[str] | None = None
        if isinstance(self.vcn, Vcn):
            self.vcn.enable_bastion_profile()
        else:
            network_profile_check = self.vcn.require_network_profile(NETWORK_PROFILE_BASTION)
        self.vcn.finalize_network()

        bastion_name = self.create_resource_name("bastion")
        self.bastion = oci.bastion.Bastion(
            bastion_name,
            bastion_type="STANDARD",
            compartment_id=self.compartment_id,
            target_subnet_id=self.vcn.get_private_subnet_id(),
            name=bastion_name,
            max_session_ttl_in_seconds=_MAX_SESSION_TTL_SECONDS,
            client_cidr_block_allow_lists=allowed_client_cidrs,
            freeform_tags=self.create_freeform_tags(bastion_name, "bastion"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.bastion_id = self.bastion.id
        self.bastion_endpoint = self.bastion.private_endpoint_ip_address

        outputs: dict[str, pulumi.Output[str] | str] = {
            "bastion_id": self.bastion_id,
            "bastion_endpoint": self.bastion_endpoint,
        }
        if network_profile_check is not None:
            outputs["network_profile_check"] = network_profile_check
        self.register_outputs(outputs)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export standard Bastion stack outputs.

        Publishes the Bastion OCID and private endpoint IP under keys
        derived from the spell's logical name.

        Example:
            ```python
            bastion = Bastion(name="mgmt", ...)
            bastion.export()
            # Exports: mgmt_bastion_id, mgmt_bastion_endpoint
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_bastion_id", self.get_bastion_id())
        pulumi.export(f"{prefix}_bastion_endpoint", self.get_bastion_endpoint())

    def get_bastion_id(self) -> pulumi.Output[str]:
        """Return the OCID of the Bastion resource.

        Returns:
            `pulumi.Output[str]` resolving to the Bastion OCID.
        """
        return self.bastion.id

    def get_bastion_endpoint(self) -> pulumi.Output[str]:
        """Return the private endpoint IP of the Bastion.

        Use this address as a `ProxyJump` target in your SSH client
        configuration to tunnel SSH connections to private-subnet instances.

        Returns:
            `pulumi.Output[str]` resolving to the Bastion private endpoint
            IP address.
        """
        return self.bastion_endpoint

    def get_access_endpoint(self) -> pulumi.Output[str]:
        """Return the access endpoint for SSH proxy sessions.

        Satisfies `AbstractBastion.get_access_endpoint`.
        Delegates to `get_bastion_endpoint`.

        Returns:
            `pulumi.Output[str]` resolving to the Bastion private endpoint
            IP address.
        """
        return self.get_bastion_endpoint()


__all__ = ["Bastion"]
