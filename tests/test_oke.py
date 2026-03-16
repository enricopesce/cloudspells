"""Unit tests for OKE Cluster block."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.blocks.oke.cluster import OkeCluster
from cloudspells.blocks.vcn.network import Vcn


class TestOkeCluster(unittest.TestCase):
    """Test cases for OKE Cluster block."""

    def setUp(self):
        """Set up VCN for OKE tests."""
        self.vcn = Vcn(
            name="oke-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

    @pulumi.runtime.test
    def test_oke_creates_cluster(self):
        """Test that OkeCluster creates a Kubernetes cluster."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
        )

        def check_cluster(cluster_id):
            self.assertIsNotNone(cluster_id, "OKE cluster must be created")

        return oke.cluster.id.apply(check_cluster)

    @pulumi.runtime.test
    def test_oke_creates_node_pool(self):
        """Test that OkeCluster creates a node pool."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
        )

        def check_node_pool(node_pool_id):
            self.assertIsNotNone(node_pool_id, "Node pool must be created")

        return oke.node_pool.id.apply(check_node_pool)

    @pulumi.runtime.test
    def test_oke_finalizes_vcn(self):
        """Test that OkeCluster calls finalize_network() on VCN."""
        vcn = Vcn(
            name="oke-finalize-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        # Subnets should be None before OkeCluster
        self.assertIsNone(vcn.public_subnet)
        self.assertIsNone(vcn.private_subnet)

        OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
        )

        # After OkeCluster, subnets should exist
        self.assertIsNotNone(vcn.public_subnet, "VCN should be finalized by OkeCluster")
        self.assertIsNotNone(vcn.private_subnet, "VCN should be finalized by OkeCluster")

    def test_oke_node_count(self):
        """Test that OkeCluster stores node count correctly."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=3,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
        )

        self.assertEqual(oke.min_nodes, 3, "min_nodes should be 3")

    def test_oke_custom_node_count(self):
        """Test that OkeCluster accepts custom node count."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=5,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
        )

        self.assertEqual(oke.min_nodes, 5)

    def test_oke_custom_resources(self):
        """Test that OkeCluster accepts custom OCPU and memory."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=4,
            memory_in_gbs=32,
            display_name="test-cluster",
        )

        self.assertEqual(oke.ocpus, 4)
        self.assertEqual(oke.memory_in_gbs, 32)

    def test_oke_security_list_aliases(self):
        """Test that OkeCluster creates security list aliases."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
        )

        # OKE should have references to VCN security lists
        self.assertIsNotNone(oke.oke_public_security_list)
        self.assertIsNotNone(oke.oke_private_security_list)

    @pulumi.runtime.test
    def test_oke_security_lists_match_vcn(self):
        """Test that OKE security list aliases point to VCN security lists."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
        )

        def check_security_lists(args):
            oke_public_id, vcn_public_id, oke_private_id, vcn_private_id = args
            self.assertEqual(oke_public_id, vcn_public_id, "OKE public SL should match VCN")
            self.assertEqual(oke_private_id, vcn_private_id, "OKE private SL should match VCN")

        return pulumi.Output.all(
            oke.oke_public_security_list.id,
            self.vcn.public_security_list.id,
            oke.oke_private_security_list.id,
            self.vcn.private_security_list.id,
        ).apply(check_security_lists)

    def test_oke_ssh_key_optional(self):
        """Test that OkeCluster SSH key is optional (None when not provided)."""
        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
            # No ssh_public_key provided
        )

        # OKE allows None for ssh_public_key (no SSH access to nodes)
        self.assertIsNone(oke.ssh_public_key, "SSH key should be None when not provided")

    def test_oke_uses_provided_ssh_key(self):
        """Test that OkeCluster uses provided SSH key."""
        provided_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAA... user@host"

        oke = OkeCluster(
            name="test-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self.vcn,
            kubernetes_version="v1.28.2",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            min_nodes=2,
            ocpus=2,
            memory_in_gbs=16,
            display_name="test-cluster",
            ssh_public_key=provided_key,
        )

        self.assertEqual(oke.ssh_public_key, provided_key)


if __name__ == "__main__":
    unittest.main()
