"""Compute Instance building block for OCIBlocks.

Provides :class:`ComputeInstance`, which deploys a single OCI VM into the
private subnet of a :class:`~blocks.vcn.network.Vcn` and attaches a block
volume for persistent data storage.

Key behaviours
--------------
* Defaults to Oracle Linux 8 (latest image for the chosen shape).
* Deploys to the VCN's **private** subnet (not directly internet-facing).
* Adds a minimal SSH ingress rule to the private security list (port 22 from
  the public subnet CIDR, for bastion-host access).
* Auto-generates an RSA 4096-bit SSH key pair when no key is supplied; the
  keys are exported as Pulumi secrets.
* Calls :meth:`~blocks.vcn.network.Vcn.finalize_network` automatically, so
  no explicit finalisation step is needed.
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from blocks.vcn.network import Vcn, VcnRef, SUBNET_PUBLIC, SUBNET_PRIVATE, SUBNET_SECURE, SUBNET_MANAGEMENT, SubnetTier
from core.helper import Helper


class ComputeInstance(BaseResource):
    """OCI Compute Instance with attached block volume.

    Creates a single VM in the VCN's private subnet together with a separate
    block volume for data storage (easier backup and migration).

    Attributes:
        vcn: The :class:`~blocks.vcn.network.Vcn` this instance is deployed
            into.
        shape: Compute shape (e.g. ``"VM.Standard.E4.Flex"``).
        ocpus: Number of OCPUs allocated to the instance.
        memory_in_gbs: RAM in GiB allocated to the instance.
        ssh_public_key: OpenSSH public key installed in
            ``authorized_keys``.
        ssh_private_key: Corresponding private key string, or ``None`` when
            the caller supplied their own public key.
        image_id: OCID of the boot image used by the instance.
        boot_volume_size_in_gbs: Size of the boot volume in GiB.
        block_volume_size_in_gbs: Size of the attached data volume in GiB.
        instance: The underlying ``oci.core.Instance`` resource.
        block_volume: The ``oci.core.Volume`` attached to the instance.
        volume_attachment: The ``oci.core.VolumeAttachment`` resource.
        id: ``pulumi.Output[str]`` of the instance OCID.
        auto_generated_keys: ``True`` when SSH keys were auto-generated.

    Usage patterns:

    1. **Minimal – auto-generated SSH keys**::

            vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
            instance = ComputeInstance(
                name="web",
                vcn=vcn,
                compartment_id=comp_id,
            )
            # Access the generated key pair:
            private_key = instance.get_ssh_private_key()

    2. **Custom shape and storage**::

            instance = ComputeInstance(
                name="app",
                vcn=vcn,
                compartment_id=comp_id,
                shape="VM.Standard.E4.Flex",
                ocpus=4,
                memory_in_gbs=64,
                boot_volume_size_in_gbs=100,
                block_volume_size_in_gbs=500,
                ssh_public_key="ssh-rsa AAAA...",
            )

    3. **Custom image**::

            instance = ComputeInstance(
                name="custom",
                vcn=vcn,
                compartment_id=comp_id,
                image_id="ocid1.image.oc1....",
            )
    """

    vcn: Vcn | VcnRef
    shape: pulumi.Input[str]
    ocpus: pulumi.Input[float]
    memory_in_gbs: pulumi.Input[float]
    ssh_public_key: str
    ssh_private_key: str | None
    image_id: pulumi.Input[str] | None
    boot_volume_size_in_gbs: pulumi.Input[int]
    block_volume_size_in_gbs: pulumi.Input[int]
    instance: oci.core.Instance
    block_volume: oci.core.Volume
    volume_attachment: oci.core.VolumeAttachment
    id: pulumi.Output[str]
    auto_generated_keys: bool

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        stack_name: str | None = None,
        ssh_public_key: pulumi.Input[str] | None = None,
        shape: pulumi.Input[str] = "VM.Standard.E4.Flex",
        ocpus: pulumi.Input[float] = 1,
        memory_in_gbs: pulumi.Input[float] = 16,
        image_id: pulumi.Input[str] | None = None,
        os_name: str = "oracle",
        subnet: SubnetTier = SUBNET_PRIVATE,
        boot_volume_size_in_gbs: pulumi.Input[int] = 50,
        block_volume_size_in_gbs: pulumi.Input[int] = 100,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a compute instance with an attached block volume.

        Args:
            name: Logical name for the instance (e.g. ``"web-server"``).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: :class:`~blocks.vcn.network.Vcn` instance that provides the
                private subnet and security list for this instance.
            stack_name: Pulumi stack name.  Defaults to
                ``pulumi.get_stack()`` when ``None``.
            ssh_public_key: OpenSSH public key string to install on the
                instance.  When ``None`` or empty, a new RSA 4096-bit key
                pair is auto-generated and exported as Pulumi secrets.
            shape: OCI compute shape (default: ``"VM.Standard.E4.Flex"``).
            ocpus: Number of OCPUs (default: ``1``).
            memory_in_gbs: Memory in GiB (default: ``16``).
            image_id: Explicit boot image OCID.  When provided, *os_name* is
                ignored and this OCID is used directly.
            os_name: Friendly OS name used to auto-discover the latest image
                when *image_id* is ``None``.  Supported values:
                ``"oracle"`` (Oracle Linux 8, default), ``"ubuntu"``
                (Canonical Ubuntu 22.04), ``"windows"``
                (Windows Server 2022 Standard).
            subnet: Which VCN tier to place the instance in.  Use the
                constants ``SUBNET_PRIVATE`` (default), ``SUBNET_PUBLIC``,
                or ``SUBNET_SECURE`` imported from
                :mod:`blocks.vcn.network`.
            boot_volume_size_in_gbs: Boot volume size in GiB (default:
                ``50``).
            block_volume_size_in_gbs: Attached data volume size in GiB
                (default: ``100``).
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:compute:Instance", name, compartment_id, stack_name, opts)

        self.name = name
        self.vcn = vcn
        self.compartment_id = compartment_id
        self.shape = shape
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs
        if subnet not in (SUBNET_PUBLIC, SUBNET_PRIVATE, SUBNET_SECURE, SUBNET_MANAGEMENT):
            raise ValueError(f"subnet must be one of {SUBNET_PUBLIC!r}, {SUBNET_PRIVATE!r}, {SUBNET_SECURE!r}, {SUBNET_MANAGEMENT!r}; got {subnet!r}")
        self.subnet = subnet
        self.image_id = image_id
        self.boot_volume_size_in_gbs = boot_volume_size_in_gbs
        self.block_volume_size_in_gbs = block_volume_size_in_gbs

        # Handle SSH key - either use provided or auto-generate
        self._setup_ssh_keys(ssh_public_key)

        # Add security rules to VCN for SSH access
        self._add_compute_security_rules()

        # Finalise the VCN network (creates security lists and subnets)
        self.vcn.finalize_network()

        assert self.vcn.private_subnet is not None, "VCN private subnet must exist after finalization"
        assert self.vcn.public_subnet is not None, "VCN public subnet must exist after finalization"
        assert self.vcn.secure_subnet is not None, "VCN secure subnet must exist after finalization"
        assert self.vcn.management_subnet is not None, "VCN management subnet must exist after finalization"

        # Resolve image - use provided OCID or discover latest by os_name
        resolved_image_id = str(image_id) if image_id is not None else None
        self.image_id = Helper().resolve_image_id(str(compartment_id), str(shape), resolved_image_id, os_name)

        # Use the first availability domain
        ads = oci.identity.get_availability_domains(compartment_id=str(compartment_id))
        availability_domain = ads.availability_domains[0].name

        # Create the compute instance
        instance_name = self.create_resource_name("instance")
        self.instance = oci.core.Instance(
            instance_name,
            availability_domain=availability_domain,
            compartment_id=self.compartment_id,
            shape=self.shape,
            display_name=instance_name,
            source_details=oci.core.InstanceSourceDetailsArgs(
                source_type="image",
                source_id=self.image_id,
                boot_volume_size_in_gbs=str(self.boot_volume_size_in_gbs),
            ),
            create_vnic_details=oci.core.InstanceCreateVnicDetailsArgs(
                subnet_id=(
                    self.vcn.public_subnet.id if self.subnet == SUBNET_PUBLIC
                    else self.vcn.secure_subnet.id if self.subnet == SUBNET_SECURE
                    else self.vcn.management_subnet.id if self.subnet == SUBNET_MANAGEMENT
                    else self.vcn.private_subnet.id
                ),
                assign_public_ip="true" if self.subnet == SUBNET_PUBLIC else "false",
                display_name=f"{instance_name}-vnic",
            ),
            metadata={
                "ssh_authorized_keys": self.ssh_public_key,
            },
            shape_config=oci.core.InstanceShapeConfigArgs(
                ocpus=self.ocpus,
                memory_in_gbs=self.memory_in_gbs,
            ),
            freeform_tags=self.create_freeform_tags(
                instance_name,
                "compute-instance",
                {
                    "Shape": str(shape),
                    "OCPUs": str(ocpus),
                    "MemoryGB": str(memory_in_gbs),
                },
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.id = self.instance.id

        # Create block volume for data storage
        volume_name = self.create_resource_name("data-volume")
        self.block_volume = oci.core.Volume(
            volume_name,
            availability_domain=availability_domain,
            compartment_id=self.compartment_id,
            display_name=volume_name,
            size_in_gbs=str(self.block_volume_size_in_gbs),
            freeform_tags=self.create_freeform_tags(
                volume_name,
                "block-volume",
                {
                    "SizeGB": str(block_volume_size_in_gbs),
                    "AttachedTo": instance_name,
                },
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Attach block volume to instance (paravirtualised for best performance)
        attachment_name = self.create_resource_name("volume-attachment")
        self.volume_attachment = oci.core.VolumeAttachment(
            attachment_name,
            instance_id=self.instance.id,
            volume_id=self.block_volume.id,
            attachment_type="paravirtualized",
            display_name=attachment_name,
            is_read_only=False,
            opts=pulumi.ResourceOptions(parent=self),
        )

        outputs = {
            "instance_id": self.instance.id,
            "private_ip": self.instance.private_ip,
            "block_volume_id": self.block_volume.id,
        }
        if self.subnet == SUBNET_PUBLIC:
            outputs["public_ip"] = self.instance.public_ip
        outputs.update(self._get_ssh_outputs())
        self.register_outputs(outputs)

    def _add_compute_security_rules(self) -> None:
        """Add SSH access rule to the appropriate VCN security list.

        For **private** subnet instances: allows TCP port 22 from the public
        subnet CIDR (bastion-host access).

        For **public** subnet instances: allows TCP port 22 from anywhere
        (``0.0.0.0/0``), since the instance is directly internet-facing.
        """
        ssh_rule = oci.core.SecurityListIngressSecurityRuleArgs(
            protocol="6",  # TCP
            source_type="CIDR_BLOCK",
            tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(min=22, max=22),
            description=(
                "SSH access from private subnet" if self.subnet in (SUBNET_SECURE, SUBNET_MANAGEMENT)
                else "SSH access from public subnet (bastion host)" if self.subnet == SUBNET_PRIVATE
                else "SSH access from the internet"
            ),
            source=(
                self.vcn.get_private_subnet_cidr() if self.subnet in (SUBNET_SECURE, SUBNET_MANAGEMENT)
                else self.vcn.get_public_subnet_cidr() if self.subnet == SUBNET_PRIVATE
                else "0.0.0.0/0"
            ),
        )

        if self.subnet == SUBNET_PRIVATE:
            self.vcn.add_security_list_rules(private_ingress=[ssh_rule])
        elif self.subnet == SUBNET_SECURE:
            self.vcn.add_security_list_rules(secure_ingress=[ssh_rule])
        elif self.subnet == SUBNET_MANAGEMENT:
            self.vcn.add_security_list_rules(management_ingress=[ssh_rule])
        else:
            self.vcn.add_security_list_rules(public_ingress=[ssh_rule])

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export standard compute instance stack outputs.

        Publishes instance OCID, private IP, block volume OCID, and SSH
        public key under keys derived from the block's logical name.  The
        SSH private key is exported as a Pulumi secret only when it was
        auto-generated.

        Example::

            instance = ComputeInstance(name="web-server", ...)
            instance.export()
            # Exports: web_server_id, web_server_private_ip,
            #          web_server_data_volume_id, web_server_ssh_public_key,
            #          and conditionally web_server_ssh_private_key (secret)
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_id", self.get_instance_id())
        pulumi.export(f"{prefix}_private_ip", self.get_private_ip())
        if self.subnet == SUBNET_PUBLIC:
            pulumi.export(f"{prefix}_public_ip", self.instance.public_ip)
        pulumi.export(f"{prefix}_data_volume_id", self.get_block_volume_id())
        pulumi.export(f"{prefix}_ssh_public_key", self.get_ssh_public_key())
        if self.auto_generated_keys and self.ssh_private_key:
            pulumi.export(f"{prefix}_ssh_private_key", pulumi.Output.secret(self.ssh_private_key))

    def get_private_ip(self) -> pulumi.Output[str]:
        """Return the private IP address of the instance.

        Returns:
            ``pulumi.Output[str]`` resolving to the instance's private IP.
        """
        return self.instance.private_ip

    def get_instance_id(self) -> pulumi.Output[str]:
        """Return the OCID of the compute instance.

        Returns:
            ``pulumi.Output[str]`` resolving to the instance OCID.
        """
        return self.instance.id

    def get_block_volume_id(self) -> pulumi.Output[str]:
        """Return the OCID of the attached block volume.

        Returns:
            ``pulumi.Output[str]`` resolving to the block volume OCID.
        """
        return self.block_volume.id

    def get_ssh_public_key(self) -> str:
        """Return the SSH public key installed on the instance.

        Returns:
            OpenSSH public key string (auto-generated or caller-supplied).
        """
        return self.ssh_public_key

    def get_ssh_private_key(self) -> str | None:
        """Return the SSH private key if it was auto-generated.

        Returns:
            PEM-encoded private key string when keys were auto-generated,
            or ``None`` when the caller supplied their own public key.
        """
        return self.ssh_private_key
