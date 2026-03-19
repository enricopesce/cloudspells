"""Unit tests for OKE Cluster block."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci.kubernetes import NodePoolConfig, OkeCluster
from cloudspells.providers.oci.network import Vcn

_DEFAULT_POOL = NodePoolConfig(
    name="default",
    shape="VM.Standard.A1.Flex",
    image="ocid1.image.test",
    node_count=2,
    ocpus=2,
    memory_in_gbs=16,
)


def _make_cluster(vcn: Vcn, node_pools: list[NodePoolConfig] | None = None) -> OkeCluster:
    return OkeCluster(
        name="test-cluster",
        compartment_id="ocid1.compartment.test",
        vcn=vcn,
        kubernetes_version="v1.28.2",
        display_name="test-cluster",
        node_pools=node_pools or [_DEFAULT_POOL],
    )


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
        oke = _make_cluster(self.vcn)

        def check_cluster(cluster_id):
            self.assertIsNotNone(cluster_id, "OKE cluster must be created")

        return oke.cluster.id.apply(check_cluster)

    @pulumi.runtime.test
    def test_oke_creates_node_pools(self):
        """Test that OkeCluster creates node pools for every NodePoolConfig."""
        oke = _make_cluster(self.vcn)

        def check_node_pool(node_pool_id):
            self.assertIsNotNone(node_pool_id, "Node pool must be created")

        return oke.node_pools[0].id.apply(check_node_pool)

    @pulumi.runtime.test
    def test_oke_creates_multiple_node_pools(self):
        """Test that OkeCluster creates one pool per NodePoolConfig entry."""
        pools = [
            NodePoolConfig(
                name="system",
                shape="VM.Standard.A1.Flex",
                image="ocid1.image.test",
                node_count=2,
                ocpus=2,
                memory_in_gbs=16,
            ),
            NodePoolConfig(
                name="app",
                shape="VM.Standard.E4.Flex",
                image="ocid1.image.test",
                node_count=5,
                ocpus=8,
                memory_in_gbs=64,
            ),
        ]
        oke = _make_cluster(self.vcn, node_pools=pools)

        self.assertEqual(len(oke.node_pools), 2, "Two node pools must be created")

        def check_pool(pool_id):
            self.assertIsNotNone(pool_id)

        return pulumi.Output.all(
            oke.node_pools[0].id,
            oke.node_pools[1].id,
        ).apply(lambda ids: [check_pool(i) for i in ids])

    @pulumi.runtime.test
    def test_oke_finalizes_vcn(self):
        """Test that OkeCluster calls finalize_network() on VCN."""
        vcn = Vcn(
            name="oke-finalize-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        self.assertIsNone(vcn.public_subnet)
        self.assertIsNone(vcn.private_subnet)

        _make_cluster(vcn)

        self.assertIsNotNone(vcn.public_subnet, "VCN should be finalized by OkeCluster")
        self.assertIsNotNone(vcn.private_subnet, "VCN should be finalized by OkeCluster")

    def test_oke_node_pool_config_values(self):
        """Test that NodePoolConfig stores values correctly."""
        cfg = NodePoolConfig(
            name="app",
            shape="VM.Standard.E4.Flex",
            image="ocid1.image.test",
            node_count=3,
            ocpus=4,
            memory_in_gbs=32,
        )

        self.assertEqual(cfg.node_count, 3)
        self.assertEqual(cfg.ocpus, 4)
        self.assertEqual(cfg.memory_in_gbs, 32)

    def test_oke_ssh_key_optional(self):
        """Test that NodePoolConfig ssh_public_key defaults to None."""
        cfg = NodePoolConfig(
            name="default",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            node_count=2,
            ocpus=2,
            memory_in_gbs=16,
        )

        self.assertIsNone(cfg.ssh_public_key, "SSH key should be None when not provided")

    def test_oke_uses_provided_ssh_key(self):
        """Test that NodePoolConfig accepts an SSH public key."""
        provided_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAA... user@host"

        cfg = NodePoolConfig(
            name="default",
            shape="VM.Standard.A1.Flex",
            image="ocid1.image.test",
            node_count=2,
            ocpus=2,
            memory_in_gbs=16,
            ssh_public_key=provided_key,
        )

        self.assertEqual(cfg.ssh_public_key, provided_key)

    def test_oke_security_list_aliases(self):
        """Test that OkeCluster creates security list aliases."""
        oke = _make_cluster(self.vcn)

        self.assertIsNotNone(oke.oke_public_security_list)
        self.assertIsNotNone(oke.oke_private_security_list)

    @pulumi.runtime.test
    def test_oke_security_lists_match_vcn(self):
        """Test that OKE security list aliases point to VCN security lists."""
        oke = _make_cluster(self.vcn)

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

    def test_oke_nsgs_created(self):
        """Test that OkeCluster creates all four NSGs."""
        oke = _make_cluster(self.vcn)

        self.assertIsNotNone(oke.api_nsg, "api_nsg must be created")
        self.assertIsNotNone(oke.lb_nsg, "lb_nsg must be created")
        self.assertIsNotNone(oke.worker_nsg, "worker_nsg must be created")
        self.assertIsNotNone(oke.pod_nsg, "pod_nsg must be created")

    @pulumi.runtime.test
    def test_oke_nsgs_have_ids(self):
        """Test that all four NSGs expose Output IDs."""
        oke = _make_cluster(self.vcn)

        def check_nsg_ids(args):
            api_id, lb_id, worker_id, pod_id = args
            self.assertIsNotNone(api_id, "api_nsg must have an ID")
            self.assertIsNotNone(lb_id, "lb_nsg must have an ID")
            self.assertIsNotNone(worker_id, "worker_nsg must have an ID")
            self.assertIsNotNone(pod_id, "pod_nsg must have an ID")

        return pulumi.Output.all(
            oke.api_nsg.id,
            oke.lb_nsg.id,
            oke.worker_nsg.id,
            oke.pod_nsg.id,
        ).apply(check_nsg_ids)


if __name__ == "__main__":
    unittest.main()
