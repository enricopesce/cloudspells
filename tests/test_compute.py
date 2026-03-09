"""Unit tests for ComputeInstance block."""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks
set_mocks()

# Import AFTER mocks are set
from blocks.vcn.network import Vcn
from blocks.compute.instance import ComputeInstance


class TestComputeInstance(unittest.TestCase):
    """Test cases for ComputeInstance block."""

    def setUp(self):
        """Set up VCN for compute tests."""
        self.vcn = Vcn(
            name="compute-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

    @pulumi.runtime.test
    def test_compute_creates_instance(self):
        """Test that ComputeInstance creates an instance."""
        instance = ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        def check_instance(instance_id):
            self.assertIsNotNone(instance_id, "Instance must be created")

        return instance.instance.id.apply(check_instance)

    @pulumi.runtime.test
    def test_compute_creates_block_volume(self):
        """Test that ComputeInstance creates a block volume."""
        instance = ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        def check_volume(volume_id):
            self.assertIsNotNone(volume_id, "Block volume must be created")

        return instance.block_volume.id.apply(check_volume)

    @pulumi.runtime.test
    def test_compute_creates_volume_attachment(self):
        """Test that ComputeInstance creates a volume attachment."""
        instance = ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        def check_attachment(attachment_id):
            self.assertIsNotNone(attachment_id, "Volume attachment must be created")

        return instance.volume_attachment.id.apply(check_attachment)

    @pulumi.runtime.test
    def test_compute_finalizes_vcn(self):
        """Test that ComputeInstance calls finalize_network() on VCN."""
        vcn = Vcn(
            name="finalize-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        # Subnets should be None before ComputeInstance
        self.assertIsNone(vcn.public_subnet)
        self.assertIsNone(vcn.private_subnet)

        instance = ComputeInstance(
            name="test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        # After ComputeInstance, subnets should exist
        self.assertIsNotNone(vcn.public_subnet, "VCN should be finalized by ComputeInstance")
        self.assertIsNotNone(vcn.private_subnet, "VCN should be finalized by ComputeInstance")

    def test_compute_auto_generates_ssh_key(self):
        """Test that ComputeInstance auto-generates SSH keys when not provided."""
        instance = ComputeInstance(
            name="auto-key-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            # No ssh_public_key provided
        )

        self.assertTrue(instance.auto_generated_keys, "Keys should be auto-generated")
        self.assertIsNotNone(instance.ssh_public_key, "Public key should be generated")
        self.assertIsNotNone(instance.ssh_private_key, "Private key should be generated")
        self.assertTrue(
            instance.ssh_public_key.startswith("ssh-rsa"),
            "Public key should be RSA format"
        )

    def test_compute_uses_provided_ssh_key(self):
        """Test that ComputeInstance uses provided SSH key."""
        provided_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAA... user@host"

        instance = ComputeInstance(
            name="provided-key-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key=provided_key,
        )

        self.assertFalse(instance.auto_generated_keys, "Keys should not be auto-generated")
        self.assertEqual(instance.ssh_public_key, provided_key, "Should use provided key")
        self.assertIsNone(instance.ssh_private_key, "Private key should be None when provided")

    def test_compute_treats_empty_key_as_none(self):
        """Test that empty SSH key string triggers auto-generation."""
        instance = ComputeInstance(
            name="empty-key-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="",  # Empty string
        )

        self.assertTrue(instance.auto_generated_keys, "Empty key should trigger auto-generation")
        self.assertIsNotNone(instance.ssh_public_key)

    def test_compute_default_shape(self):
        """Test that ComputeInstance uses default shape."""
        instance = ComputeInstance(
            name="default-shape-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        self.assertEqual(instance.shape, "VM.Standard.E4.Flex", "Default shape should be E4.Flex")

    def test_compute_custom_shape(self):
        """Test that ComputeInstance accepts custom shape."""
        instance = ComputeInstance(
            name="custom-shape-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            shape="VM.Standard.A1.Flex",
            ocpus=4,
            memory_in_gbs=24,
        )

        self.assertEqual(instance.shape, "VM.Standard.A1.Flex")
        self.assertEqual(instance.ocpus, 4)
        self.assertEqual(instance.memory_in_gbs, 24)

    def test_compute_custom_volume_sizes(self):
        """Test that ComputeInstance accepts custom volume sizes."""
        instance = ComputeInstance(
            name="custom-volumes-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            boot_volume_size_in_gbs=100,
            block_volume_size_in_gbs=500,
        )

        self.assertEqual(instance.boot_volume_size_in_gbs, 100)
        self.assertEqual(instance.block_volume_size_in_gbs, 500)

    def test_compute_getter_methods(self):
        """Test ComputeInstance getter methods."""
        instance = ComputeInstance(
            name="getter-test-instance",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            ssh_public_key="ssh-rsa AAAAB3... test-key",
        )

        # Verify getter methods return Output types
        self.assertIsNotNone(instance.get_private_ip())
        self.assertIsNotNone(instance.get_instance_id())
        self.assertIsNotNone(instance.get_block_volume_id())
        self.assertIsNotNone(instance.get_ssh_public_key())


if __name__ == "__main__":
    unittest.main()
