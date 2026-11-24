r"""Bastion Service spell for CloudSpells.

Provides `Bastion`, which creates an OCI Bastion Service endpoint attached to
the VCN's private subnet.  The Bastion enables time-limited SSH sessions to
private-subnet resources without requiring a public-facing jump host.

Key behaviours:

- Creates one `oci.bastion.Bastion` of type `STANDARD`.
- Restricts session clients to `allowed_client_cidrs`.
- Grants SSH to an explicitly selected target NSG with `allow_ssh_to`.

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

from .network import Vcn, VcnRef
from .nsg import SSH, Nsg

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

    Use `allow_ssh_to` to authorize the Bastion private endpoint on a target NSG.

    Attributes:
        vcn: The `Vcn` or `VcnRef` this Bastion is attached to.
        bastion: The underlying `oci.bastion.Bastion` resource.
        bastion_id: `pulumi.Output[str]` OCID of the Bastion resource.
        bastion_endpoint: `pulumi.Output[str]` private endpoint IP address
            of the Bastion.  Use this as a `ProxyJump` target in SSH config.

    Example:
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")

        target_nsg = Nsg("web-target", vcn=vcn, compartment_id=comp_id)
        instance = ComputeInstance(
            name="web", compartment_id=comp_id, vcn=vcn, image_id=image_id, nsg=target_nsg,
        )

        bastion = Bastion(
            name="mgmt",
            compartment_id=comp_id,
            vcn=vcn,
            allowed_client_cidrs=["203.0.113.0/24"],  # always required
        )

        bastion.allow_ssh_to(target_nsg)
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
        """
        super().__init__("custom:bastion:Bastion", name, compartment_id, stack_name, opts)

        self.vcn = vcn

        if allowed_client_cidrs is None:
            raise ValueError(
                f"Bastion '{name}': allowed_client_cidrs must be provided explicitly. "
                "To permit all source IPs (not recommended for production), pass "
                "allowed_client_cidrs=['0.0.0.0/0']."
            )

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

        self.register_outputs({
            "bastion_id": self.bastion_id,
            "bastion_endpoint": self.bastion_endpoint,
        })

    def allow_ssh_to(self, target: Nsg) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Allow SSH from this Bastion private endpoint to members of `target`.

        Args:
            target: NSG attached to the target VNICs in this VCN.

        Returns:
            The NSG ingress rule permitting TCP port 22 from the endpoint IP.
        """
        return target.allow_from_cidr(
            f"bastion-{self.name}-ssh",
            SSH,
            pulumi.Output.concat(self.bastion_endpoint, "/32"),
            "SSH from OCI Bastion private endpoint",
        )

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
