"""Unit tests for ComputeInstance block and VolumeSpec dataclass."""

import unittest

import pulumi

from tests.mocks import set_mocks

set_mocks()

from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.volume import VolumeSpec


class TestVolumeSpec(unittest.TestCase):
    """Tests for VolumeSpec validation and defaults."""

    def test_default_fields(self):
        """VolumeSpec defaults are correct."""
        spec = VolumeSpec(size_in_gbs=100)
        self.assertEqual(spec.label, "data")
        self.assertEqual(spec.vpus_per_gb, VolumeSpec.PERF_BALANCED)
        self.assertFalse(spec.is_read_only)

    def test_performance_constants(self):
        """Class-level performance constants have expected values."""
        self.assertEqual(VolumeSpec.PERF_LOW, 0)
        self.assertEqual(VolumeSpec.PERF_BALANCED, 10)
        self.assertEqual(VolumeSpec.PERF_HIGH, 20)
        self.assertEqual(VolumeSpec.PERF_ULTRA, 120)

    def test_valid_custom_spec(self):
        """A fully-specified VolumeSpec is accepted."""
        spec = VolumeSpec(
            size_in_gbs=500,
            label="db",
            vpus_per_gb=VolumeSpec.PERF_HIGH,
            is_read_only=True,
        )
        self.assertEqual(spec.size_in_gbs, 500)
        self.assertEqual(spec.label, "db")
        self.assertEqual(spec.vpus_per_gb, 20)
        self.assertTrue(spec.is_read_only)

    def test_rejects_size_below_minimum(self):
        """size_in_gbs < 50 raises ValueError."""
        with self.assertRaises(ValueError, msg="size_in_gbs < 50 should raise"):
            VolumeSpec(size_in_gbs=49)

    def test_rejects_invalid_vpus(self):
        """vpus_per_gb not in {0,10,20,120} raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, vpus_per_gb=5)

    def test_rejects_invalid_label_uppercase(self):
        """Label with uppercase letters raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, label="Data")

    def test_rejects_invalid_label_starts_digit(self):
        """Label starting with a digit raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, label="1data")

    def test_rejects_empty_label(self):
        """Empty label raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, label="")

    def test_accepts_label_with_hyphen(self):
        """Label with hyphens is accepted."""
        spec = VolumeSpec(size_in_gbs=100, label="my-data")
        self.assertEqual(spec.label, "my-data")

    def test_accepts_exact_minimum_size(self):
        """size_in_gbs == 50 is accepted."""
        spec = VolumeSpec(size_in_gbs=50)
        self.assertEqual(spec.size_in_gbs, 50)

    def test_rejects_size_above_maximum(self) -> None:
        """Test that size_in_gbs above OCI maximum raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=32769)


class TestComputeInstance(unittest.TestCase):
    """Tests for ComputeInstance block."""

    def _make_vcn(self) -> Vcn:
        """Create a fresh VCN for each test to prevent shared mutable state."""
        return Vcn(name="compute-test-vcn", compartment_id="ocid1.compartment.test")

    # ------ resource creation -----------------------------------------

    @pulumi.runtime.test
    def test_creates_instance(self):
        """ComputeInstance creates an oci.core.Instance."""
        instance = ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        return instance.instance.id.apply(lambda iid: self.assertIsNotNone(iid))

    @pulumi.runtime.test
    def test_auto_discovers_availability_domain(self):
        """ComputeInstance without availability_domain selects first mock AD."""
        instance = ComputeInstance(
            name="auto-ad-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
        )
        return instance.availability_domain.apply(lambda ad: self.assertEqual(ad, "AD-1"))

    @pulumi.runtime.test
    def test_default_creates_one_volume(self):
        """Default ComputeInstance creates exactly one block volume."""
        instance = ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertEqual(len(instance.block_volumes), 1)
        self.assertEqual(len(instance.volume_attachments), 1)
        return instance.block_volumes[0].id.apply(lambda vid: self.assertIsNotNone(vid))

    @pulumi.runtime.test
    def test_multiple_volumes_created(self):
        """ComputeInstance creates all volumes in the list."""
        instance = ComputeInstance(
            name="multi-vol-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            volumes=[
                VolumeSpec(size_in_gbs=100, label="data"),
                VolumeSpec(size_in_gbs=200, label="logs"),
                VolumeSpec(size_in_gbs=500, label="db", vpus_per_gb=VolumeSpec.PERF_HIGH),
            ],
        )
        self.assertEqual(len(instance.block_volumes), 3)
        self.assertEqual(len(instance.volume_attachments), 3)
        self.assertEqual(len(instance.volumes_spec), 3)

    @pulumi.runtime.test
    def test_creates_volume_attachment(self):
        """ComputeInstance creates a volume attachment."""
        instance = ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        return instance.volume_attachments[0].id.apply(lambda aid: self.assertIsNotNone(aid))

    @pulumi.runtime.test
    def test_finalizes_vcn(self):
        """ComputeInstance calls finalize_network() on the VCN."""
        vcn = Vcn(name="finalize-test-vcn", compartment_id="ocid1.compartment.test")
        self.assertIsNone(vcn.public_subnet)
        self.assertIsNone(vcn.private_subnet)
        ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertIsNotNone(vcn.public_subnet)
        self.assertIsNotNone(vcn.private_subnet)
        public_subnet = vcn.public_subnet
        assert public_subnet is not None
        return public_subnet.id.apply(lambda _: None)

    # ------ backward-compat properties --------------------------------

    @pulumi.runtime.test
    def test_block_volume_property_returns_first_volume(self):
        """block_volume property returns block_volumes[0]."""
        instance = ComputeInstance(
            name="compat-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertIs(instance.block_volume, instance.block_volumes[0])
        return instance.block_volume.id.apply(lambda vid: self.assertIsNotNone(vid))

    @pulumi.runtime.test
    def test_volume_attachment_property_returns_first_attachment(self):
        """volume_attachment property returns volume_attachments[0]."""
        instance = ComputeInstance(
            name="compat-attach-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertIs(instance.volume_attachment, instance.volume_attachments[0])
        return instance.volume_attachment.id.apply(lambda aid: self.assertIsNotNone(aid))

    # ------ accessor methods ------------------------------------------

    @pulumi.runtime.test
    def test_get_volume_id_by_label(self):
        """get_volume_id returns the OCID for the named volume."""
        instance = ComputeInstance(
            name="label-lookup-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            volumes=[
                VolumeSpec(size_in_gbs=100, label="data"),
                VolumeSpec(size_in_gbs=200, label="logs"),
            ],
        )
        return instance.get_volume_id("logs").apply(lambda vid: self.assertIsNotNone(vid))

    def test_get_volume_id_unknown_label_raises(self):
        """get_volume_id raises KeyError for an unknown label."""
        instance = ComputeInstance(
            name="keyerror-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        with self.assertRaises(KeyError):
            instance.get_volume_id("nonexistent")

    def test_get_all_volume_ids_length(self):
        """get_all_volume_ids returns one Output per volume."""
        instance = ComputeInstance(
            name="all-ids-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            volumes=[
                VolumeSpec(size_in_gbs=100, label="a"),
                VolumeSpec(size_in_gbs=100, label="b"),
                VolumeSpec(size_in_gbs=100, label="c"),
            ],
        )
        self.assertEqual(len(instance.get_all_volume_ids()), 3)

    # ------ validation ------------------------------------------------

    def test_duplicate_labels_raises(self):
        """Duplicate VolumeSpec labels raise ValueError."""
        with self.assertRaises(ValueError, msg="Duplicate labels must raise"):
            ComputeInstance(
                name="dup-label-instance",
                compartment_id="ocid1.compartment.test",
                vcn=self._make_vcn(),
                image_id="ocid1.image.oc1.phx.test",
                availability_domain="AD-1",
                ssh_public_key="ssh-rsa AAAAB3... test-key",
                volumes=[
                    VolumeSpec(size_in_gbs=100, label="data"),
                    VolumeSpec(size_in_gbs=200, label="data"),
                ],
            )

    def test_empty_volumes_list_raises(self):
        """Empty volumes list raises ValueError."""
        with self.assertRaises(ValueError):
            ComputeInstance(
                name="empty-vols-instance",
                compartment_id="ocid1.compartment.test",
                vcn=self._make_vcn(),
                image_id="ocid1.image.oc1.phx.test",
                availability_domain="AD-1",
                ssh_public_key="ssh-rsa AAAAB3... test-key",
                volumes=[],
            )

    # ------ SSH keys --------------------------------------------------

    def test_auto_generates_ssh_key(self):
        """ComputeInstance auto-generates SSH keys when not provided."""
        instance = ComputeInstance(
            name="auto-key-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
        )
        self.assertTrue(instance.auto_generated_keys)
        self.assertIsNotNone(instance.ssh_public_key)
        self.assertIsNotNone(instance.ssh_private_key)
        self.assertTrue(instance.ssh_public_key.startswith("ssh-rsa"))

    def test_uses_provided_ssh_key(self):
        """ComputeInstance uses a caller-supplied SSH key."""
        provided_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAA... user@host"
        instance = ComputeInstance(
            name="provided-key-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key=provided_key,
        )
        self.assertFalse(instance.auto_generated_keys)
        self.assertEqual(instance.ssh_public_key, provided_key)
        self.assertIsNone(instance.ssh_private_key)

    def test_empty_key_triggers_auto_generation(self):
        """Empty SSH key string triggers auto-generation."""
        instance = ComputeInstance(
            name="empty-key-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="",
        )
        self.assertTrue(instance.auto_generated_keys)

    # ------ shape / config --------------------------------------------

    def test_default_shape(self):
        """Default shape is VM.Standard.E4.Flex."""
        instance = ComputeInstance(
            name="default-shape-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertEqual(instance.shape, "VM.Standard.E4.Flex")

    def test_custom_shape(self):
        """Custom shape, ocpus, and memory_in_gbs are stored."""
        instance = ComputeInstance(
            name="custom-shape-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            shape="VM.Standard.A1.Flex",
            ocpus=4,
            memory_in_gbs=24,
        )
        self.assertEqual(instance.shape, "VM.Standard.A1.Flex")
        self.assertEqual(instance.ocpus, 4)
        self.assertEqual(instance.memory_in_gbs, 24)

    def test_volumes_spec_stored(self):
        """volumes_spec attribute reflects the provided list."""
        specs = [
            VolumeSpec(size_in_gbs=100, label="data"),
            VolumeSpec(size_in_gbs=500, label="db", vpus_per_gb=VolumeSpec.PERF_HIGH),
        ]
        instance = ComputeInstance(
            name="spec-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            volumes=specs,
        )
        self.assertEqual(instance.volumes_spec, specs)

    # ------ getter methods --------------------------------------------

    def test_getter_methods_return_outputs(self):
        """Standard getter methods return non-None values."""
        instance = ComputeInstance(
            name="getter-test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertIsNotNone(instance.get_private_ip())
        self.assertIsNotNone(instance.get_instance_id())
        self.assertIsNotNone(instance.get_block_volume_id())
        self.assertIsNotNone(instance.get_ssh_public_key())
        self.assertEqual(len(instance.get_all_volume_ids()), 1)

    # ------ new optional parameters ------------------------------------

    def test_user_data_string_accepted(self):
        """user_data as a plain string is stored and base64-encoded by the spell."""
        instance = ComputeInstance(
            name="userdata-str-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            user_data="#!/bin/bash\necho hello\n",
        )
        self.assertIsNotNone(instance.instance)

    def test_user_data_bytes_accepted(self):
        """user_data as bytes is accepted."""
        instance = ComputeInstance(
            name="userdata-bytes-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            user_data=b"#!/bin/bash\necho hello\n",
        )
        self.assertIsNotNone(instance.instance)

    def test_fault_domain_optional(self):
        """fault_domain defaults to None (OCI auto-assigns)."""
        instance = ComputeInstance(
            name="fd-default-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertIsNone(instance.fault_domain)

    def test_fault_domain_explicit(self):
        """Explicit fault_domain is stored on the instance."""
        instance = ComputeInstance(
            name="fd-explicit-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            fault_domain="FAULT-DOMAIN-2",
        )
        self.assertEqual(instance.fault_domain, "FAULT-DOMAIN-2")

    def test_hostname_label_optional(self):
        """hostname_label defaults to None."""
        instance = ComputeInstance(
            name="hl-default-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertIsNone(instance.hostname_label)

    def test_hostname_label_set(self):
        """Explicit hostname_label is stored."""
        instance = ComputeInstance(
            name="hl-set-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            hostname_label="app-server",
        )
        self.assertEqual(instance.hostname_label, "app-server")

    def test_volume_spec_device_field(self):
        """VolumeSpec.device stores the explicit device path."""
        spec = VolumeSpec(
            size_in_gbs=100,
            label="data",
            device="/dev/oracleoci/oraclevdb",
        )
        self.assertEqual(spec.device, "/dev/oracleoci/oraclevdb")

    def test_volume_spec_device_default_none(self):
        """VolumeSpec.device defaults to None."""
        spec = VolumeSpec(size_in_gbs=100, label="data")
        self.assertIsNone(spec.device)

    @pulumi.runtime.test
    def test_all_new_params_accepted(self):
        """ComputeInstance accepts all new optional parameters without error."""
        instance = ComputeInstance(
            name="full-params-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            user_data="#!/bin/bash\necho hello\n",
            fault_domain="FAULT-DOMAIN-1",
            hostname_label="full-params",
            volumes=[
                VolumeSpec(
                    size_in_gbs=200,
                    label="data",
                    device="/dev/oracleoci/oraclevdb",
                ),
            ],
        )
        return instance.instance.id.apply(lambda iid: self.assertIsNotNone(iid))

    # ------ subnet placement ------------------------------------------

    def test_management_subnet_placement(self):
        """ComputeInstance with subnet=SUBNET_MANAGEMENT is accepted."""
        from cloudspells.providers.oci.network import SUBNET_MANAGEMENT

        instance = ComputeInstance(
            name="mgmt-subnet-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            subnet=SUBNET_MANAGEMENT,
        )
        self.assertIsNotNone(instance.instance)

    def test_public_subnet_placement(self):
        """ComputeInstance with subnet=SUBNET_PUBLIC is accepted."""
        from cloudspells.providers.oci.network import SUBNET_PUBLIC

        instance = ComputeInstance(
            name="public-subnet-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            subnet=SUBNET_PUBLIC,
        )
        self.assertIsNotNone(instance.instance)

    # ------ additional accessor methods --------------------------------

    def test_get_disk_id_delegates_to_get_volume_id(self):
        """get_disk_id returns the same Output as get_volume_id for the same label."""
        instance = ComputeInstance(
            name="disk-id-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            volumes=[VolumeSpec(size_in_gbs=100, label="data")],
        )
        self.assertIsNotNone(instance.get_disk_id("data"))

    def test_get_disk_id_unknown_label_raises(self):
        """get_disk_id raises KeyError for an unknown label."""
        instance = ComputeInstance(
            name="disk-keyerror-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        with self.assertRaises(KeyError):
            instance.get_disk_id("nonexistent")

    def test_get_volume_returns_oci_resource(self):
        """get_volume returns a non-None resource object for a valid label."""
        instance = ComputeInstance(
            name="get-vol-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            volumes=[VolumeSpec(size_in_gbs=100, label="data")],
        )
        self.assertIsNotNone(instance.get_volume("data"))

    def test_get_volume_unknown_label_raises(self):
        """get_volume raises KeyError for an unknown label."""
        instance = ComputeInstance(
            name="get-vol-keyerror-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        with self.assertRaises(KeyError):
            instance.get_volume("nonexistent")

    def test_get_volume_attachment_returns_resource(self):
        """get_volume_attachment returns a non-None resource for a valid label."""
        instance = ComputeInstance(
            name="get-att-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            volumes=[VolumeSpec(size_in_gbs=100, label="data")],
        )
        self.assertIsNotNone(instance.get_volume_attachment("data"))

    def test_get_volume_attachment_unknown_label_raises(self):
        """get_volume_attachment raises KeyError for an unknown label."""
        instance = ComputeInstance(
            name="get-att-keyerror-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        with self.assertRaises(KeyError):
            instance.get_volume_attachment("nonexistent")

    def test_get_ssh_private_key_returns_none_when_key_provided(self):
        """get_ssh_private_key returns None when the caller supplied their own public key."""
        instance = ComputeInstance(
            name="privkey-none-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )
        self.assertIsNone(instance.get_ssh_private_key())

    def test_get_ssh_private_key_returns_key_when_auto_generated(self):
        """get_ssh_private_key returns the PEM string when keys were auto-generated."""
        instance = ComputeInstance(
            name="privkey-auto-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
        )
        self.assertIsNotNone(instance.get_ssh_private_key())


class TestComputeInstanceNsgShorthand(unittest.TestCase):
    """Tests for ComputeInstance nsg= parameter and subnet inference."""

    @pulumi.runtime.test
    def test_nsg_shorthand_infers_private_subnet(self):
        """ComputeInstance with nsg=APP_SERVER NSG is placed in private subnet."""
        from cloudspells.providers.oci.nsg import Nsg
        from cloudspells.providers.oci.roles import APP_SERVER, DATABASE

        vcn = Vcn(name="ci-priv", compartment_id="ocid1.compartment.oc1..test")
        web_nsg = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id="ocid1.compartment.oc1..test")
        web_nsg.serves(Nsg("db", role=DATABASE, vcn=vcn, compartment_id="ocid1.compartment.oc1..test"), port=5432)

        instance = ComputeInstance(
            name="web-1",
            compartment_id="ocid1.compartment.oc1..test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            nsg=web_nsg,
        )
        self.assertEqual(instance.subnet, "private")

    @pulumi.runtime.test
    def test_nsg_shorthand_infers_public_subnet(self):
        """ComputeInstance with nsg=INTERNET_EDGE NSG is placed in public subnet."""
        from cloudspells.providers.oci.nsg import Nsg
        from cloudspells.providers.oci.roles import INTERNET_EDGE

        vcn = Vcn(name="ci-pub", compartment_id="ocid1.compartment.oc1..test")
        lb_nsg = Nsg("lb", role=INTERNET_EDGE, ports=[80], vcn=vcn, compartment_id="ocid1.compartment.oc1..test")

        instance = ComputeInstance(
            name="lb-1",
            compartment_id="ocid1.compartment.oc1..test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            nsg=lb_nsg,
        )
        self.assertEqual(instance.subnet, "public")

    @pulumi.runtime.test
    def test_nsg_shorthand_infers_secure_subnet(self):
        """ComputeInstance with nsg=DATABASE NSG is placed in secure subnet."""
        from cloudspells.providers.oci.nsg import Nsg
        from cloudspells.providers.oci.roles import DATABASE

        vcn = Vcn(name="ci-sec", compartment_id="ocid1.compartment.oc1..test")
        db_nsg = Nsg("db", role=DATABASE, vcn=vcn, compartment_id="ocid1.compartment.oc1..test")

        instance = ComputeInstance(
            name="db-1",
            compartment_id="ocid1.compartment.oc1..test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            nsg=db_nsg,
        )
        self.assertEqual(instance.subnet, "secure")

    @pulumi.runtime.test
    def test_nsg_shorthand_sets_nsg_ids(self):
        """ComputeInstance with nsg= sets nsg_ids to [nsg.id]."""
        from cloudspells.providers.oci.nsg import Nsg
        from cloudspells.providers.oci.roles import APP_SERVER

        vcn = Vcn(name="ci-ids", compartment_id="ocid1.compartment.oc1..test")
        web_nsg = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id="ocid1.compartment.oc1..test")

        instance = ComputeInstance(
            name="web-x",
            compartment_id="ocid1.compartment.oc1..test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            nsg=web_nsg,
        )
        self.assertEqual(len(instance.nsg_ids), 1)

    @pulumi.runtime.test
    def test_old_api_unchanged(self):
        """ComputeInstance with explicit subnet= and nsg= still works."""
        from cloudspells.providers.oci.network import SUBNET_PRIVATE
        from cloudspells.providers.oci.nsg import Nsg
        from cloudspells.providers.oci.roles import APP_SERVER

        vcn = Vcn(name="ci-old", compartment_id="ocid1.compartment.oc1..test")
        web_nsg = Nsg("web-old", role=APP_SERVER, vcn=vcn, compartment_id="ocid1.compartment.oc1..test")

        instance = ComputeInstance(
            name="web-old",
            compartment_id="ocid1.compartment.oc1..test",
            vcn=vcn,
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            subnet=SUBNET_PRIVATE,
            nsg=web_nsg,
        )
        # APP_SERVER role is placed in private subnet — matches explicit subnet=.
        self.assertEqual(instance.subnet, "private")
        self.assertEqual(len(instance.nsg_ids), 1)


if __name__ == "__main__":
    unittest.main()
