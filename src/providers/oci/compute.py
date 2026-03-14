"""Compute Instance building block for CloudBlocks.

Provides `ComputeInstance`, which deploys a single OCI VM into a chosen VCN
subnet and attaches one or more block volumes for persistent storage.

Key behaviours:

- Defaults to Oracle Linux 8 (latest image for the chosen shape).
- Deploys to the VCN's private subnet by default (not directly
  internet-facing).
- Adds a minimal SSH ingress rule to the appropriate security list
  (port 22 from the public subnet CIDR for bastion-host access).
- Auto-generates an RSA 4096-bit SSH key pair when no key is supplied;
  the keys are exported as Pulumi secrets.
- Accepts a list of `VolumeSpec` objects to attach any number of block
  volumes; defaults to a single 100 GiB balanced-performance data volume.
- Calls `Vcn.finalize_network` automatically.

Exports:
    ComputeInstance: Single-VM component resource with multi-volume support.
"""

from __future__ import annotations

from typing import Sequence

import pulumi
import pulumi_oci as oci

from core.abstractions.compute import AbstractCompute
from core.base import BaseResource
from providers.oci.helper import OciHelper
from providers.oci.network import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
    Vcn,
    VcnRef,
)
from providers.oci.nsg import Nsg
from providers.oci.volume import VolumeSpec


class ComputeInstance(BaseResource, AbstractCompute):
    """OCI Compute Instance with one or more attached block volumes.

    Creates a single VM in the chosen VCN subnet together with the block
    volumes described by the `volumes` parameter.  Each `VolumeSpec` in the
    list produces one `oci.core.Volume` and one `oci.core.VolumeAttachment`;
    all are created at the same time as the instance.

    Attributes:
        vcn: The `Vcn` this instance is deployed into.
        shape: Compute shape (e.g. `"VM.Standard.E4.Flex"`).
        ocpus: Number of OCPUs allocated to the instance.
        memory_in_gbs: RAM in GiB allocated to the instance.
        ssh_public_key: OpenSSH public key installed in `authorized_keys`.
        ssh_private_key: Corresponding private key string, or `None` when
            the caller supplied their own public key.
        image_id: OCID of the boot image used by the instance.
        boot_volume_size_in_gbs: Size of the boot volume in GiB.
        volumes_spec: Resolved list of `VolumeSpec` objects used to create
            the attached block volumes.
        instance: The underlying `oci.core.Instance` resource.
        block_volumes: Ordered list of `oci.core.Volume` resources, one per
            entry in `volumes_spec`.
        volume_attachments: Ordered list of `oci.core.VolumeAttachment`
            resources, parallel to `block_volumes`.
        id: `pulumi.Output[str]` of the instance OCID.
        auto_generated_keys: `True` when SSH keys were auto-generated.

    Usage patterns:

    1. **Minimal — single default data volume, auto-generated SSH keys**:
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
        instance = ComputeInstance(
            name="web",
            vcn=vcn,
            compartment_id=comp_id,
        )
        private_key = instance.get_ssh_private_key()
        ```

    2. **Multiple volumes with explicit performance tiers**:
        ```python
        instance = ComputeInstance(
            name="app",
            vcn=vcn,
            compartment_id=comp_id,
            volumes=[
                VolumeSpec(size_in_gbs=200, label="app"),
                VolumeSpec(size_in_gbs=500, label="db",
                           vpus_per_gb=VolumeSpec.PERF_HIGH),
                VolumeSpec(size_in_gbs=100, label="logs",
                           vpus_per_gb=VolumeSpec.PERF_LOW),
            ],
        )
        db_vol_id = instance.get_volume_id("db")
        ```

    3. **Custom shape and boot volume**:
        ```python
        instance = ComputeInstance(
            name="heavy",
            vcn=vcn,
            compartment_id=comp_id,
            shape="VM.Standard.E4.Flex",
            ocpus=8,
            memory_in_gbs=128,
            boot_volume_size_in_gbs=100,
            volumes=[VolumeSpec(size_in_gbs=1000, label="data",
                                vpus_per_gb=VolumeSpec.PERF_HIGH)],
        )
        ```
    """

    vcn: Vcn | VcnRef
    shape: pulumi.Input[str]
    ocpus: pulumi.Input[float]
    memory_in_gbs: pulumi.Input[float]
    ssh_public_key: str
    ssh_private_key: str | None
    image_id: pulumi.Input[str] | None
    boot_volume_size_in_gbs: pulumi.Input[int]
    volumes_spec: list[VolumeSpec]
    instance: oci.core.Instance
    block_volumes: list[oci.core.Volume]
    volume_attachments: list[oci.core.VolumeAttachment]
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
        volumes: Sequence[VolumeSpec] | None = None,
        nsg_ids: list[pulumi.Input[str]] | None = None,
        nsg: Nsg | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a compute instance with one or more attached block volumes.

        Args:
            name: Logical name for the instance (e.g. `"web-server"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` instance that provides the subnet and security list
                for this instance.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            ssh_public_key: OpenSSH public key string to install on the
                instance.  When `None` or empty, a new RSA 4096-bit key
                pair is auto-generated and exported as Pulumi secrets.
            shape: OCI compute shape (default: `"VM.Standard.E4.Flex"`).
            ocpus: Number of OCPUs (default: `1`).
            memory_in_gbs: Memory in GiB (default: `16`).
            image_id: Explicit boot image OCID.  When provided, `os_name`
                is ignored.
            os_name: Friendly OS name used to auto-discover the latest
                image when `image_id` is `None`.  Supported values:
                `"oracle"` (Oracle Linux 8, default), `"ubuntu"`
                (Canonical Ubuntu 22.04), `"windows"`
                (Windows Server 2022 Standard).
            subnet: Which VCN tier to place the instance in.  Use the
                constants `SUBNET_PRIVATE` (default), `SUBNET_PUBLIC`,
                `SUBNET_SECURE`, or `SUBNET_MANAGEMENT` imported from
                `blocks.vcn`.  Ignored when `nsg` is supplied and the
                NSG has a `Role` — the role's `subnet_tier` takes
                precedence.
            boot_volume_size_in_gbs: Boot volume size in GiB (default:
                `50`).
            volumes: Ordered list of `VolumeSpec` objects describing the
                block volumes to attach.  Each entry must have a unique
                `label`; the label is used to derive the resource name
                suffix.  Defaults to `None`, which creates a single 100 GiB
                balanced-performance data volume (`VolumeSpec(size_in_gbs=100)`).
                Pass an explicit list to override; an empty list raises
                `ValueError`.
            nsg_ids: List of Network Security Group OCIDs to attach to the
                instance VNIC.  When `None`, no NSGs are attached and
                security is enforced by the subnet security list alone.
                Provide NSG OCIDs (e.g. from `Nsg`) to add a second,
                resource-level security layer.
            nsg: Shorthand for single-NSG deployments.  When supplied, sets
                `nsg_ids=[nsg.id]` and, if the NSG carries a `Role`, also
                infers `subnet` from `nsg.role.subnet_tier`.  Takes
                precedence over `subnet` and `nsg_ids` when both are
                provided.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `subnet` is not a recognised tier constant, or if
                any two `VolumeSpec` entries share the same `label`.

        Example:
            ```python
            # Role-based shorthand — subnet inferred from NSG role
            web = ComputeInstance("web-1", compartment_id=comp_id, vcn=vcn, nsg=web_nsg)
            db  = ComputeInstance("db-1",  compartment_id=comp_id, vcn=vcn, nsg=db_nsg,
                                  volumes=[VolumeSpec(size_in_gbs=200, label="data")])
            ```
        """
        # Resolve nsg= shorthand: infer subnet from role and expand nsg_ids.
        if nsg is not None:
            if nsg.role is not None:
                subnet = nsg.role.subnet_tier
            nsg_ids = [nsg.id]
        super().__init__("custom:compute:Instance", name, compartment_id, stack_name, opts)

        self.name = name
        self.vcn = vcn
        self.compartment_id = compartment_id
        self.shape = shape
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs

        self.subnet = subnet
        self.image_id = image_id
        self.boot_volume_size_in_gbs = boot_volume_size_in_gbs

        # Resolve volumes list.
        # None  → one default 100 GiB balanced-performance data volume.
        # []    → caller error; an explicitly empty list has no valid meaning.
        if volumes is None:
            self.volumes_spec = [VolumeSpec(size_in_gbs=100)]
        elif len(volumes) == 0:
            raise ValueError(
                "volumes must not be empty; pass volumes=None to use the default "
                "100 GiB data volume, or provide at least one VolumeSpec."
            )
        else:
            self.volumes_spec = list(volumes)
        labels = [spec.label for spec in self.volumes_spec]
        duplicates = {lbl for lbl in labels if labels.count(lbl) > 1}
        if duplicates:
            raise ValueError(
                f"VolumeSpec labels must be unique within the list; duplicates found: {sorted(duplicates)}"
            )

        self.nsg_ids = nsg_ids or []

        # SSH key setup
        self._setup_ssh_keys(ssh_public_key)

        # Accumulate security rules, then materialise the VCN.
        # Skip rule-addition when the network is already finalised (e.g. a
        # sibling ComputeInstance was constructed first); the caller is
        # responsible for adding any additional rules before the first block
        # triggers finalisation.
        if isinstance(self.vcn, Vcn) and not self.vcn._security_lists_finalized:
            self._add_compute_security_rules()
        self.vcn.finalize_network()

        assert self.vcn.private_subnet is not None
        assert self.vcn.public_subnet is not None
        assert self.vcn.secure_subnet is not None
        assert self.vcn.management_subnet is not None

        # Resolve boot image
        resolved_image_id = str(image_id) if image_id is not None else None
        self.image_id = OciHelper().resolve_image_id(str(compartment_id), str(shape), resolved_image_id, os_name)

        ads = oci.identity.get_availability_domains(compartment_id=str(compartment_id))
        availability_domain = ads.availability_domains[0].name

        # ---- Compute instance ------------------------------------------
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
                    self.vcn.public_subnet.id
                    if self.subnet == SUBNET_PUBLIC
                    else self.vcn.secure_subnet.id
                    if self.subnet == SUBNET_SECURE
                    else self.vcn.management_subnet.id
                    if self.subnet == SUBNET_MANAGEMENT
                    else self.vcn.private_subnet.id
                ),
                assign_public_ip="true" if self.subnet == SUBNET_PUBLIC else "false",
                display_name=f"{instance_name}-vnic",
                nsg_ids=self.nsg_ids if self.nsg_ids else None,
            ),
            metadata={"ssh_authorized_keys": self.ssh_public_key},
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

        # ---- Block volumes (one per VolumeSpec) ------------------------
        self.block_volumes = []
        self.volume_attachments = []

        for spec in self.volumes_spec:
            vol_name = self.create_resource_name(f"{spec.label}-vol")
            vol = oci.core.Volume(
                vol_name,
                availability_domain=availability_domain,
                compartment_id=self.compartment_id,
                display_name=vol_name,
                size_in_gbs=str(spec.size_in_gbs),
                vpus_per_gb=str(spec.vpus_per_gb),
                freeform_tags=self.create_freeform_tags(
                    vol_name,
                    "block-volume",
                    {
                        "SizeGB": str(spec.size_in_gbs),
                        "Label": spec.label,
                        "PerfTier": str(spec.vpus_per_gb),
                        "AttachedTo": instance_name,
                    },
                ),
                opts=pulumi.ResourceOptions(parent=self),
            )
            att_name = self.create_resource_name(f"{spec.label}-vol-attach")
            att = oci.core.VolumeAttachment(
                att_name,
                instance_id=self.instance.id,
                volume_id=vol.id,
                attachment_type="paravirtualized",
                display_name=att_name,
                is_read_only=spec.is_read_only,
                opts=pulumi.ResourceOptions(parent=self, delete_before_replace=True),
            )
            self.block_volumes.append(vol)
            self.volume_attachments.append(att)

        # ---- Stack outputs ---------------------------------------------
        outputs: dict[str, pulumi.Output[str]] = {
            "instance_id": self.instance.id,
            "private_ip": self.instance.private_ip,
        }
        for spec, vol in zip(self.volumes_spec, self.block_volumes):
            outputs[f"{spec.label}_volume_id"] = vol.id
        if self.subnet == SUBNET_PUBLIC:
            outputs["public_ip"] = self.instance.public_ip
        outputs.update(self._get_ssh_outputs())
        self.register_outputs(outputs)

    # ------------------------------------------------------------------
    # Backward-compatibility shims
    # ------------------------------------------------------------------

    @property
    def block_volume(self) -> oci.core.Volume:
        """Return the first (primary) block volume.

        Provides backward compatibility for code that references
        `instance.block_volume` directly.  For multi-volume setups use
        `block_volumes` or `get_volume` instead.

        Returns:
            The first `oci.core.Volume` in `block_volumes`.
        """
        return self.block_volumes[0]

    @property
    def volume_attachment(self) -> oci.core.VolumeAttachment:
        """Return the first (primary) volume attachment.

        Provides backward compatibility for code that references
        `instance.volume_attachment` directly.  For multi-volume setups use
        `volume_attachments` or `get_volume_attachment` instead.

        Returns:
            The first `oci.core.VolumeAttachment` in `volume_attachments`.
        """
        return self.volume_attachments[0]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_compute_security_rules(self) -> None:
        """Add SSH ingress rule to the appropriate VCN security list.

        For **private** subnet instances: allows TCP port 22 from the public
        subnet CIDR (bastion-host pattern).

        For **secure** / **management** subnet instances: allows TCP port 22
        from the private subnet CIDR.

        For **public** subnet instances: allows TCP port 22 from anywhere
        (`0.0.0.0/0`).
        """
        ssh_rule = oci.core.SecurityListIngressSecurityRuleArgs(
            protocol="6",
            source_type="CIDR_BLOCK",
            tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(min=22, max=22),
            description=(
                "SSH access from private subnet"
                if self.subnet in (SUBNET_SECURE, SUBNET_MANAGEMENT)
                else "SSH access from public subnet (bastion host)"
                if self.subnet == SUBNET_PRIVATE
                else "SSH access from the internet"
            ),
            source=(
                self.vcn.get_private_subnet_cidr()
                if self.subnet in (SUBNET_SECURE, SUBNET_MANAGEMENT)
                else self.vcn.get_public_subnet_cidr()
                if self.subnet == SUBNET_PRIVATE
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

        Publishes instance OCID, private IP, all block volume OCIDs, and SSH
        public key under keys derived from the block's logical name.  The SSH
        private key is exported as a Pulumi secret only when it was
        auto-generated.  Each volume is exported under
        `{name}_{label}_volume_id`.

        Example:
            ```python
            instance = ComputeInstance(
                name="app",
                vcn=vcn,
                compartment_id=comp_id,
                volumes=[
                    VolumeSpec(size_in_gbs=100, label="data"),
                    VolumeSpec(size_in_gbs=500, label="db"),
                ],
            )
            instance.export()
            # Exports: app_id, app_private_ip,
            #          app_data_volume_id, app_db_volume_id,
            #          app_ssh_public_key,
            #          app_ssh_private_key (secret, only if auto-generated)
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_id", self.get_instance_id())
        pulumi.export(f"{prefix}_private_ip", self.get_private_ip())
        if self.subnet == SUBNET_PUBLIC:
            pulumi.export(f"{prefix}_public_ip", self.instance.public_ip)
        for spec, vol in zip(self.volumes_spec, self.block_volumes):
            pulumi.export(f"{prefix}_{spec.label}_volume_id", vol.id)
        pulumi.export(f"{prefix}_ssh_public_key", self.get_ssh_public_key())
        if self.auto_generated_keys and self.ssh_private_key:
            pulumi.export(
                f"{prefix}_ssh_private_key",
                pulumi.Output.secret(self.ssh_private_key),
            )

    def get_private_ip(self) -> pulumi.Output[str]:
        """Return the private IP address of the instance.

        Returns:
            `pulumi.Output[str]` resolving to the instance's private IP.
        """
        return self.instance.private_ip

    def get_instance_id(self) -> pulumi.Output[str]:
        """Return the OCID of the compute instance.

        Returns:
            `pulumi.Output[str]` resolving to the instance OCID.
        """
        return self.instance.id

    def get_block_volume_id(self) -> pulumi.Output[str]:
        """Return the OCID of the first (primary) block volume.

        Provided for backward compatibility.  For multi-volume setups use
        `get_volume_id` or `get_all_volume_ids`.

        Returns:
            `pulumi.Output[str]` resolving to the first block volume OCID.
        """
        return self.block_volumes[0].id

    def get_volume_id(self, label: str) -> pulumi.Output[str]:
        """Return the OCID of the block volume with the given label.

        Args:
            label: The `label` value of the target `VolumeSpec`.

        Returns:
            `pulumi.Output[str]` resolving to the volume OCID.

        Raises:
            KeyError: If no volume with the given label exists.

        Example:
            ```python
            db_vol_id = instance.get_volume_id("db")
            ```
        """
        for spec, vol in zip(self.volumes_spec, self.block_volumes):
            if spec.label == label:
                return vol.id
        raise KeyError(f"No volume with label {label!r}. Available labels: {[s.label for s in self.volumes_spec]}")

    def get_disk_id(self, label: str) -> pulumi.Output[str]:
        """Return the OCID of the block volume with the given label.

        Satisfies `AbstractCompute.get_disk_id`.  Delegates to
        `get_volume_id`.

        Args:
            label: The `label` value of the target `VolumeSpec`.

        Returns:
            `pulumi.Output[str]` resolving to the volume OCID.

        Raises:
            KeyError: If no volume with the given label exists.
        """
        return self.get_volume_id(label)

    def get_volume(self, label: str) -> oci.core.Volume:
        """Return the `oci.core.Volume` resource with the given label.

        Args:
            label: The `label` value of the target `VolumeSpec`.

        Returns:
            The `oci.core.Volume` resource.

        Raises:
            KeyError: If no volume with the given label exists.
        """
        for spec, vol in zip(self.volumes_spec, self.block_volumes):
            if spec.label == label:
                return vol
        raise KeyError(f"No volume with label {label!r}. Available labels: {[s.label for s in self.volumes_spec]}")

    def get_volume_attachment(self, label: str) -> oci.core.VolumeAttachment:
        """Return the `oci.core.VolumeAttachment` resource with the given label.

        Args:
            label: The `label` value of the target `VolumeSpec`.

        Returns:
            The `oci.core.VolumeAttachment` resource.

        Raises:
            KeyError: If no volume with the given label exists.
        """
        for spec, att in zip(self.volumes_spec, self.volume_attachments):
            if spec.label == label:
                return att
        raise KeyError(
            f"No volume attachment with label {label!r}. Available labels: {[s.label for s in self.volumes_spec]}"
        )

    def get_all_volume_ids(self) -> list[pulumi.Output[str]]:
        """Return a list of OCIDs for all attached block volumes.

        The list order matches the order of the `volumes` parameter passed
        at construction time.

        Returns:
            List of `pulumi.Output[str]` resolving to each volume OCID.
        """
        return [vol.id for vol in self.block_volumes]

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
            or `None` when the caller supplied their own public key.
        """
        return self.ssh_private_key


__all__ = ["ComputeInstance"]
