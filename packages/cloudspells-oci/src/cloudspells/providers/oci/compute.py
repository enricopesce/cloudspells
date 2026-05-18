"""Compute Instance spell for CloudSpells.

Provides `ComputeInstance`, which deploys a single OCI VM into the subnet tier
declared by its required role-bearing NSG and attaches one or more block
volumes for persistent storage.

Key behaviours:

- Requires an `Nsg` with a `Role`; the role decides subnet placement.
- Derives the VCN from the NSG so callers cannot pass inconsistent networks.
- Auto-generates an RSA 4096-bit SSH key pair when no key is supplied;
  the keys are exported as Pulumi secrets.
- Accepts a list of `VolumeSpec` objects to attach any number of block
  volumes; labels are used for lookups and tags, not Pulumi resource names.
- Calls `Vcn.finalize_network` automatically.

Exports:
    ComputeInstance: Single-VM component resource with multi-volume support.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.compute import AbstractCompute
from cloudspells.core.base import BaseResource

from ._naming import ordinal_suffix
from .network import (
    SUBNET_MANAGEMENT,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    SubnetTier,
    Vcn,
    VcnRef,
)
from .nsg import Nsg
from .volume import VolumeSpec


class ComputeInstance(BaseResource, AbstractCompute):
    """OCI Compute Instance with one or more attached block volumes.

    Creates a single VM in the subnet tier declared by `nsg.role`, together
    with the block volumes described by the `volumes` parameter.  Each
    `VolumeSpec` in the list produces one `oci.core.Volume` and one
    `oci.core.VolumeAttachment`; all are created at the same time as the
    instance.

    Attributes:
        vcn: The `Vcn` or `VcnRef` derived from the required NSG.
        shape: Compute shape (e.g. `"VM.Standard.E4.Flex"`).
        ocpus: Number of OCPUs allocated to the instance.
        memory_in_gbs: RAM in GiB allocated to the instance.
        ssh_public_key: OpenSSH public key installed in `authorized_keys`.
        ssh_private_key: Corresponding private key string, or `None` when
            the caller supplied their own public key.
        image_id: OCID of the boot image used by the instance.
        availability_domain: Resolved OCI Availability Domain name
            (`pulumi.Output[str]`) for the instance and all attached block
            volumes.  Auto-discovered from the compartment's first AD when
            not explicitly supplied.
        boot_volume_size_in_gbs: Size of the boot volume in GiB.
        volumes_spec: Resolved list of `VolumeSpec` objects used to create
            the attached block volumes.
        nsg: Role-bearing `Nsg` attached to the instance VNIC.
        instance: The underlying `oci.core.Instance` resource.
        block_volumes: Ordered list of `oci.core.Volume` resources, one per
            entry in `volumes_spec`.
        volume_attachments: Ordered list of `oci.core.VolumeAttachment`
            resources, parallel to `block_volumes`.
        id: `pulumi.Output[str]` of the instance OCID.
        subnet: Subnet tier the instance is placed in (`SUBNET_PRIVATE`,
            `SUBNET_PUBLIC`, `SUBNET_SECURE`, or `SUBNET_MANAGEMENT`).
            Resolved from `nsg.role.subnet_tier`.
        nsg_ids: List containing the NSG OCID attached to the primary VNIC.
        auto_generated_keys: `True` when SSH keys were auto-generated.
        fault_domain: Fault domain the instance is placed in, or `None`
            when OCI auto-assigns (default spread behaviour).
        hostname_label: DNS hostname for the primary VNIC, or `None`.

    Usage patterns:

    1. **Minimal private instance — single default data volume**:
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")
        app_nsg = Nsg("app", role=APP_SERVER, vcn=vcn, compartment_id=comp_id)
        instance = ComputeInstance(
            name="web",
            compartment_id=comp_id,
            image_id=image_id,
            nsg=app_nsg,
        )
        private_key = instance.get_ssh_private_key()
        ```

    2. **Multiple volumes with explicit performance tiers**:
        ```python
        instance = ComputeInstance(
            name="app",
            compartment_id=comp_id,
            image_id=image_id,
            nsg=app_nsg,
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
            compartment_id=comp_id,
            image_id=image_id,
            nsg=app_nsg,
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
    image_id: pulumi.Input[str]
    availability_domain: pulumi.Output[str]
    boot_volume_size_in_gbs: pulumi.Input[int]
    volumes_spec: list[VolumeSpec]
    subnet: SubnetTier
    nsg: Nsg
    nsg_ids: list[pulumi.Input[str]]
    instance: oci.core.Instance
    block_volumes: list[oci.core.Volume]
    volume_attachments: list[oci.core.VolumeAttachment]
    id: pulumi.Output[str]
    auto_generated_keys: bool
    fault_domain: str | None
    hostname_label: str | None

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        image_id: pulumi.Input[str],
        nsg: Nsg,
        availability_domain: pulumi.Input[str] | None = None,
        stack_name: str | None = None,
        ssh_public_key: pulumi.Input[str] | None = None,
        shape: pulumi.Input[str] = "VM.Standard.E4.Flex",
        ocpus: pulumi.Input[float] = 1,
        memory_in_gbs: pulumi.Input[float] = 16,
        boot_volume_size_in_gbs: pulumi.Input[int] = 50,
        volumes: Sequence[VolumeSpec] | None = None,
        user_data: str | bytes | None = None,
        fault_domain: str | None = None,
        hostname_label: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a compute instance with one or more attached block volumes.

        Args:
            name: Logical name for the instance (e.g. `"web-server"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            image_id: Boot image OCID for the instance
                (e.g. `"ocid1.image.oc1.phx.aaaaaa..."`).  Must be an
                explicit OCID — CloudSpells does not perform
                auto-discovery.  Obtain the OCID from the OCI Console or
                CLI and commit it to your Pulumi stack config.

                No default is provided because platform image OCIDs are
                region-specific.  Callers should source this from
                `oci.core.get_images_output()` outside the spell or from
                a stack config value.  Embedding a hardcoded OCID is an
                anti-pattern.
            nsg: Role-bearing Network Security Group to attach to the
                instance VNIC.  The NSG's VCN provides network context, and
                `nsg.role.subnet_tier` decides subnet placement.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            ssh_public_key: OpenSSH public key string to install on the
                instance.  When `None` or empty, a new RSA 4096-bit key
                pair is auto-generated and exported as Pulumi secrets.
            shape: OCI compute shape (default: `"VM.Standard.E4.Flex"`).
            ocpus: Number of OCPUs (default: `1`).
            memory_in_gbs: Memory in GiB (default: `16`).
            availability_domain: OCI Availability Domain name for the
                instance and its block volumes
                (e.g. `"IqDk:US-ASHBURN-AD-1"`).  When `None` (default),
                CloudSpells auto-discovers the first AD in the compartment
                via `oci.identity.get_availability_domains_output()`.
                Provide an explicit value to pin placement to a specific AD.
            boot_volume_size_in_gbs: Boot volume size in GiB (default:
                `50`).
            volumes: Ordered list of `VolumeSpec` objects describing the
                block volumes to attach.  Each entry must have a unique
                `label`; the label is used for lookup helpers, outputs, and
                tags, while Pulumi resource names use CloudSpells-owned
                ordinal slots.  Defaults to `None`, which creates a single
                100 GiB balanced-performance data volume
                (`VolumeSpec(size_in_gbs=100)`).  Pass an explicit list to
                override; an empty list raises `ValueError`.
            user_data: Cloud-init script as a plain `str` or `bytes`.
                CloudSpells base64-encodes it before passing to OCI.  When
                `None`, no user data is injected.
            fault_domain: Explicit fault domain for placement
                (e.g. `"FAULT-DOMAIN-1"`).  When `None`, OCI auto-assigns
                and spreads instances across fault domains.
            hostname_label: DNS hostname registered for the primary VNIC.
                Must be unique within the subnet.  When `None`, OCI does
                not assign a hostname.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `nsg` has no role, if `volumes` is an explicitly
                empty list, or if any two `VolumeSpec` entries share the same
                `label`.
            RuntimeError: If any of the four VCN subnets is absent after
                `finalize_network()` completes.

        Example:
            ```python
            # Role-based placement — VCN and subnet are inferred from the NSG
            web = ComputeInstance("web-1", compartment_id=comp_id,
                                  image_id=image_id, nsg=web_nsg)
            db  = ComputeInstance("db-1",  compartment_id=comp_id,
                                  image_id=image_id, nsg=db_nsg,
                                  volumes=[VolumeSpec(size_in_gbs=200, label="data")])
            ```
        """
        super().__init__("custom:compute:Instance", name, compartment_id, stack_name, opts)

        role = nsg.role
        if role is None:
            raise ValueError(
                f"ComputeInstance '{name}' requires nsg.role to determine VCN placement. "
                "Construct the NSG with a role such as APP_SERVER, DATABASE, MANAGEMENT, or INTERNET_EDGE."
            )

        self.nsg = nsg
        self.vcn = nsg.vcn
        self.shape = shape
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs

        self.subnet = role.subnet_tier
        self.image_id = image_id
        if availability_domain is not None:
            self.availability_domain = pulumi.Output.from_input(availability_domain)
        else:
            ads_output = oci.identity.get_availability_domains_output(compartment_id=self.compartment_id)
            self.availability_domain = ads_output.availability_domains.apply(lambda ads: ads[0].name)
        self.boot_volume_size_in_gbs = boot_volume_size_in_gbs
        self.fault_domain = fault_domain
        self.hostname_label = hostname_label

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

        self.nsg_ids = [nsg.id]

        # SSH key setup
        self._setup_ssh_keys(ssh_public_key)

        # Materialise the network after role-bearing NSGs and other rule-owning
        # spells have registered their security list requirements.
        self.vcn.finalize_network()

        self._assert_subnets_ready()
        assert self.vcn.public_subnet is not None
        assert self.vcn.private_subnet is not None
        assert self.vcn.secure_subnet is not None
        assert self.vcn.management_subnet is not None

        # ---- Encode cloud-init user data --------------------------------
        encoded_user_data: str | None = None
        if user_data is not None:
            raw = user_data.encode() if isinstance(user_data, str) else user_data
            encoded_user_data = base64.b64encode(raw).decode()

        # ---- Compute instance ------------------------------------------
        instance_name = self.create_resource_name("instance")

        instance_metadata: dict[str, str] = {"ssh_authorized_keys": self.ssh_public_key}
        if encoded_user_data is not None:
            instance_metadata["user_data"] = encoded_user_data

        self.instance = oci.core.Instance(
            instance_name,
            availability_domain=self.availability_domain,
            compartment_id=self.compartment_id,
            shape=self.shape,
            display_name=instance_name,
            fault_domain=self.fault_domain,
            source_details=oci.core.InstanceSourceDetailsArgs(
                source_type="image",
                source_id=self.image_id,
                boot_volume_size_in_gbs=str(self.boot_volume_size_in_gbs),
                boot_volume_vpus_per_gb="10",
            ),
            create_vnic_details=oci.core.InstanceCreateVnicDetailsArgs(
                subnet_id=self._resolve_subnet_id(),
                assign_public_ip="true" if self.subnet == SUBNET_PUBLIC else "false",
                display_name=self.create_resource_name("vnic"),
                nsg_ids=self.nsg_ids if self.nsg_ids else None,
                hostname_label=self.hostname_label,
                skip_source_dest_check=False,
            ),
            metadata=instance_metadata,
            shape_config=oci.core.InstanceShapeConfigArgs(
                ocpus=self.ocpus,
                memory_in_gbs=self.memory_in_gbs,
            ),
            is_pv_encryption_in_transit_enabled=True,
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
        self._attach_block_volumes(self.availability_domain, instance_name)

        # ---- Stack outputs ---------------------------------------------
        outputs: dict[str, pulumi.Output[str]] = {
            "instance_id": self.instance.id,
            "private_ip": self.instance.private_ip,
        }
        for spec, vol in zip(self.volumes_spec, self.block_volumes, strict=False):
            outputs[f"{spec.label}_volume_id"] = vol.id
        if self.subnet == SUBNET_PUBLIC:
            outputs["public_ip"] = self.instance.public_ip
        outputs.update(self._get_ssh_outputs())
        self.register_outputs(outputs)

    def _resolve_subnet_id(self) -> pulumi.Input[str]:
        """Return the subnet OCID for the VNIC based on `self.subnet`."""
        assert self.vcn.public_subnet is not None
        assert self.vcn.private_subnet is not None
        assert self.vcn.secure_subnet is not None
        assert self.vcn.management_subnet is not None
        if self.subnet == SUBNET_PUBLIC:
            return self.vcn.public_subnet.id
        if self.subnet == SUBNET_SECURE:
            return self.vcn.secure_subnet.id
        if self.subnet == SUBNET_MANAGEMENT:
            return self.vcn.management_subnet.id
        return self.vcn.private_subnet.id

    def _attach_block_volumes(
        self,
        availability_domain: pulumi.Input[str],
        instance_name: str,
    ) -> None:
        """Create and attach one block volume per `VolumeSpec` in `self.volumes_spec`.

        Appends each created `oci.core.Volume` to `self.block_volumes` and each
        `oci.core.VolumeAttachment` to `self.volume_attachments`.

        Args:
            availability_domain: AD name used for volume placement.
            instance_name: Resource name of the parent instance, used in volume tags.
        """
        for index, spec in enumerate(self.volumes_spec):
            legacy_name_prefix = f"{self.stack_name}-{self.name}-{spec.label}"
            vol_name = self.create_resource_name(ordinal_suffix("vol", index))
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
                opts=pulumi.ResourceOptions(
                    parent=self,
                    aliases=[pulumi.Alias(name=f"{legacy_name_prefix}-vol")],
                ),
            )
            att_name = self.create_resource_name(ordinal_suffix("vol-attach", index))
            att = oci.core.VolumeAttachment(
                att_name,
                instance_id=self.instance.id,
                volume_id=vol.id,
                attachment_type="paravirtualized",
                display_name=att_name,
                is_read_only=spec.is_read_only,
                device=spec.device,
                opts=pulumi.ResourceOptions(
                    parent=self,
                    delete_before_replace=True,
                    depends_on=[self.instance, vol],
                    aliases=[pulumi.Alias(name=f"{legacy_name_prefix}-vol-attach")],
                ),
            )
            self.block_volumes.append(vol)
            self.volume_attachments.append(att)

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

    def _assert_subnets_ready(self) -> None:
        """Raise `RuntimeError` if any VCN subnet is absent after `finalize_network()`.

        All four subnets must be non-`None` before resources that reference
        them can be created.  This should never fire for a properly constructed
        `Vcn`; it can fire for a `VcnRef` whose source stack did not export
        all expected subnet outputs.

        Raises:
            RuntimeError: If any of the four subnets is `None`.
        """
        for attr, label in (
            ("private_subnet", "private"),
            ("public_subnet", "public"),
            ("secure_subnet", "secure"),
            ("management_subnet", "management"),
        ):
            if getattr(self.vcn, attr) is None:
                raise RuntimeError(f"VCN {label} subnet must exist after finalize_network().")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export standard compute instance stack outputs.

        Publishes instance OCID, private IP, availability domain, shape,
        fault domain, all block volume OCIDs, and SSH public key under keys
        derived from the spell's logical name.  The SSH private key is
        exported as a Pulumi secret only when it was auto-generated.  Each
        volume is exported under `{name}_{label}_volume_id`.

        Example:
            ```python
            instance = ComputeInstance(
                name="app",
                compartment_id=comp_id,
                image_id=image_id,
                nsg=app_nsg,
                volumes=[
                    VolumeSpec(size_in_gbs=100, label="data"),
                    VolumeSpec(size_in_gbs=500, label="db"),
                ],
            )
            instance.export()
            # Exports: app_id, app_private_ip,
            #          app_availability_domain, app_shape, app_fault_domain,
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
        pulumi.export(f"{prefix}_availability_domain", self.availability_domain)
        pulumi.export(f"{prefix}_shape", self.instance.shape)
        pulumi.export(f"{prefix}_fault_domain", self.instance.fault_domain)
        for spec, vol in zip(self.volumes_spec, self.block_volumes, strict=False):
            pulumi.export(f"{prefix}_{spec.label}_volume_id", vol.id)
        ssh_key_val = pulumi.Output.secret(self.ssh_public_key) if self.auto_generated_keys else self.ssh_public_key
        pulumi.export(f"{prefix}_ssh_public_key", ssh_key_val)
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
        for spec, vol in zip(self.volumes_spec, self.block_volumes, strict=False):
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
        for spec, vol in zip(self.volumes_spec, self.block_volumes, strict=False):
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
        for spec, att in zip(self.volumes_spec, self.volume_attachments, strict=False):
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


__all__ = ["ComputeInstance"]
