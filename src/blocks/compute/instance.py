from __future__ import annotations

import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from blocks.vcn.network import Vcn
from typing import Optional
import subprocess
import os
import tempfile


class ComputeInstance(BaseResource):
    """OCI Compute Instance with attached block volume for data storage.

    This block creates a compute instance with:
    - Standard Oracle Linux 8 image (customizable)
    - Deployment to VCN's private subnet (secure by default)
    - Attached block volume for persistent data storage
    - SSH access security rules (from public subnet for bastion access)
    - Automated SSH key generation (optional - provide your own or auto-generate)

    The instance follows OCI best practices by:
    - Deploying to private subnet (not directly exposed to internet)
    - Using separate data volume (easier backup/migration)
    - Adding minimal security rules (SSH only)
    - Auto-generating SSH keys if not provided (exported as Pulumi secrets)

    Usage Patterns:

    1. Simple instance with defaults (auto-generated SSH keys):
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")

        # No SSH key provided - will auto-generate and export keys
        instance = ComputeInstance(
            name="web-server",
            vcn=vcn,
            compartment_id=comp_id,
            stack_name="prod"
            # ssh_public_key not provided - auto-generates
        )

        # Access generated keys
        private_key = instance.get_ssh_private_key()  # Returns the private key
        public_key = instance.get_ssh_public_key()    # Returns the public key
        ```

    2. Custom shape and storage:
        ```python
        instance = ComputeInstance(
            name="app-server",
            vcn=vcn,
            compartment_id=comp_id,
            stack_name="prod",
            shape="VM.Standard.E4.Flex",
            ocpus=4,
            memory_in_gbs=64,
            ssh_public_key="ssh-rsa AAAA...",
            boot_volume_size_in_gbs=100,
            block_volume_size_in_gbs=500
        )
        ```

    3. Using your own SSH key:
        ```python
        instance = ComputeInstance(
            name="web-server",
            vcn=vcn,
            compartment_id=comp_id,
            stack_name="prod",
            ssh_public_key="ssh-rsa AAAA... your-key-comment"  # Your public key
        )
        ```

    4. Custom image:
        ```python
        instance = ComputeInstance(
            name="custom-server",
            vcn=vcn,
            compartment_id=comp_id,
            stack_name="prod",
            image_id="ocid1.image.oc1...."  # Your custom image
            # ssh_public_key omitted - will auto-generate
        )
        ```
    """

    vcn: Vcn
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
        vcn: Vcn,
        stack_name: str,
        ssh_public_key: pulumi.Input[str] | None = None,
        # Optional parameters with sensible defaults
        shape: pulumi.Input[str] = "VM.Standard.E4.Flex",
        ocpus: pulumi.Input[float] = 1,
        memory_in_gbs: pulumi.Input[float] = 16,
        image_id: pulumi.Input[str] | None = None,
        boot_volume_size_in_gbs: pulumi.Input[int] = 50,
        block_volume_size_in_gbs: pulumi.Input[int] = 100,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """
        Create a compute instance with attached block volume.

        :param str name: The name of the instance
        :param pulumi.Input[str] compartment_id: The OCID of the compartment
        :param Vcn vcn: The VCN instance to deploy into
        :param str stack_name: Stack identifier for naming and tagging
        :param pulumi.Input[str] ssh_public_key: SSH public key for instance access (optional - auto-generates if not provided)
        :param pulumi.Input[str] shape: Compute shape (default: VM.Standard.E4.Flex)
        :param pulumi.Input[float] ocpus: Number of OCPUs (default: 1)
        :param pulumi.Input[float] memory_in_gbs: Memory in GB (default: 16)
        :param pulumi.Input[str] image_id: Optional custom image OCID (defaults to Oracle Linux 8)
        :param pulumi.Input[int] boot_volume_size_in_gbs: Boot volume size (default: 50GB)
        :param pulumi.Input[int] block_volume_size_in_gbs: Data volume size (default: 100GB)
        :param pulumi.ResourceOptions opts: Options for the resource
        """
        super().__init__("custom:compute:Instance", name, compartment_id, stack_name, opts)

        self.name = name
        self.vcn = vcn
        self.compartment_id = compartment_id
        self.shape = shape
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs
        self.image_id = image_id
        self.boot_volume_size_in_gbs = boot_volume_size_in_gbs
        self.block_volume_size_in_gbs = block_volume_size_in_gbs

        # Handle SSH key - either use provided or auto-generate
        # Treat empty string as None
        if ssh_public_key is None or (isinstance(ssh_public_key, str) and ssh_public_key.strip() == ""):
            # Auto-generate SSH key pair
            public_key, private_key = self._generate_ssh_key_pair()
            self.ssh_public_key = public_key
            self.ssh_private_key = private_key
            self.auto_generated_keys = True
        else:
            # Use provided public key
            self.ssh_public_key = str(ssh_public_key)
            self.ssh_private_key = None
            self.auto_generated_keys = False

        # Add security rules to VCN for SSH access
        self._add_compute_security_rules()

        # Finalize the VCN network (create security lists and subnets with all collected rules)
        self.vcn.finalize_network()

        # At this point, finalize_network() has been called, so subnets exist
        assert self.vcn.private_subnet is not None, "VCN private subnet must exist after finalization"

        # Get the latest Oracle Linux 8 image if no custom image specified
        if image_id is None:
            # Get the latest Oracle Linux 8 image for the compartment
            # Filter for Oracle-Linux-8.x images
            images = oci.core.get_images(
                compartment_id=str(compartment_id),
                operating_system="Oracle Linux",
                operating_system_version="8",
                shape=str(shape),
                sort_by="TIMECREATED",
                sort_order="DESC",
            )
            # Get the most recent image (first in the sorted list)
            self.image_id = images.images[0].id

        # Get availability domain (use first AD)
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
                subnet_id=self.vcn.private_subnet.id,
                assign_public_ip="false",  # Private subnet - no public IP
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

        # Attach block volume to instance
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

        # Register outputs
        outputs = {
            "instance_id": self.instance.id,
            "private_ip": self.instance.private_ip,
            "block_volume_id": self.block_volume.id,
        }

        # Add SSH keys to outputs if auto-generated
        if self.auto_generated_keys:
            outputs["ssh_public_key"] = pulumi.Output.secret(self.ssh_public_key)
            outputs["ssh_private_key"] = pulumi.Output.secret(self.ssh_private_key) if self.ssh_private_key else pulumi.Output.from_input("")

        self.register_outputs(outputs)

    def _add_compute_security_rules(self) -> None:
        """Add compute instance security rules to VCN.

        This adds SSH access rules to the private subnet, allowing SSH connections
        from the public subnet (where bastion hosts would typically be deployed).

        Security Rules Added:
        ---------------------
        Private Subnet Ingress:
        - SSH (port 22) from public subnet for bastion host access

        This minimal ruleset follows the principle of least privilege. Additional
        rules for application traffic (HTTP, HTTPS, custom ports) should be added
        based on the specific workload requirements.
        """
        # Get subnet CIDRs
        public_subnet_cidr = self.vcn.get_public_subnet_cidr()

        # SSH access from public subnet (for bastion host access)
        compute_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="SSH access to compute instance from public subnet (bastion host access)",
                protocol="6",  # TCP
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=22,
                    max=22,
                ),
            ),
        ]

        # Add rules to VCN private security list
        self.vcn.add_security_list_rules(
            private_ingress=compute_ingress_rules,
        )

    def get_private_ip(self) -> pulumi.Output[str]:
        """Get the private IP address of the instance.

        Returns:
            The private IP address as a Pulumi Output.
        """
        return self.instance.private_ip

    def get_instance_id(self) -> pulumi.Output[str]:
        """Get the OCID of the compute instance.

        Returns:
            The instance OCID as a Pulumi Output.
        """
        return self.instance.id

    def get_block_volume_id(self) -> pulumi.Output[str]:
        """Get the OCID of the attached block volume.

        Returns:
            The block volume OCID as a Pulumi Output.
        """
        return self.block_volume.id

    def _generate_ssh_key_pair(self) -> tuple[str, str]:
        """Generate an SSH key pair for the instance.

        Returns:
            Tuple of (public_key, private_key) as strings.
        """
        # Create a temporary directory for key generation
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "id_rsa")

            # Generate SSH key pair using ssh-keygen
            subprocess.run(
                [
                    "ssh-keygen",
                    "-t",
                    "rsa",
                    "-b",
                    "4096",
                    "-f",
                    key_path,
                    "-N",
                    "",  # No passphrase
                    "-C",
                    f"ociblocks-{self.stack_name}-{self.name}",
                ],
                check=True,
                capture_output=True,
            )

            # Read public key
            with open(f"{key_path}.pub", "r") as f:
                public_key = f.read().strip()

            # Read private key
            with open(key_path, "r") as f:
                private_key = f.read()

        return public_key, private_key

    def get_ssh_public_key(self) -> str:
        """Get the SSH public key used for the instance.

        Returns:
            The SSH public key as a string.
        """
        return self.ssh_public_key

    def get_ssh_private_key(self) -> str | None:
        """Get the SSH private key if auto-generated.

        Returns:
            The SSH private key as a string if auto-generated, None otherwise.
        """
        return self.ssh_private_key
