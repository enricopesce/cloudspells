"""Unit tests for OKE Cluster block."""

import unittest
import warnings
from unittest.mock import patch

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci._network_profiles import (
    CLOUDSPELLS_OCI_VCN_SCHEMA,
    NETWORK_PROFILE_BASELINE,
    oke_profile_id,
)
from cloudspells.providers.oci.kubernetes import (
    NodePoolConfig,
    OkeCluster,
    OkeClusterEnhanced,
)
from cloudspells.providers.oci.network import Vcn, VcnRef

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
        node_pools=node_pools or [_DEFAULT_POOL],
        kubectl_allowed_cidrs=["10.0.0.0/8"],
    )


def _make_vcn_ref(**kwargs) -> VcnRef:
    """Build a VcnRef populated with plain values suitable for tests."""
    defaults = dict(
        vcn_id="ocid1.vcn.test",
        public_subnet_id="ocid1.subnet.public.test",
        private_subnet_id="ocid1.subnet.private.test",
        public_subnet_cidr="10.0.48.0/21",
        private_subnet_cidr="10.0.0.0/19",
        cidr_block="10.0.0.0/18",
        cloudspells_network_schema=CLOUDSPELLS_OCI_VCN_SCHEMA,
        network_profiles=[NETWORK_PROFILE_BASELINE],
        public_security_list_id="ocid1.seclist.public.test",
        private_security_list_id="ocid1.seclist.private.test",
    )
    defaults.update(kwargs)
    return VcnRef(**defaults)


class TestOkeCluster(unittest.TestCase):
    """Test cases for OKE Cluster block."""

    def _make_vcn(self) -> Vcn:
        """Create a fresh VCN for each test to prevent shared mutable state."""
        return Vcn(
            name="oke-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

    @pulumi.runtime.test
    def test_oke_creates_cluster(self):
        """Test that OkeCluster creates a Kubernetes cluster."""
        oke = _make_cluster(self._make_vcn())

        def check_cluster(cluster_id):
            self.assertIsNotNone(cluster_id, "OKE cluster must be created")

        return oke.cluster.id.apply(check_cluster)

    @pulumi.runtime.test
    def test_oke_creates_node_pools(self):
        """Test that OkeCluster creates node pools for every NodePoolConfig."""
        oke = _make_cluster(self._make_vcn())

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
        oke = _make_cluster(self._make_vcn(), node_pools=pools)

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
        oke = _make_cluster(self._make_vcn())

        self.assertIsNotNone(oke.oke_public_security_list)
        self.assertIsNotNone(oke.oke_private_security_list)

    @pulumi.runtime.test
    def test_oke_security_lists_match_vcn(self):
        """Test that OKE security list aliases point to VCN security lists."""
        vcn = self._make_vcn()
        oke = _make_cluster(vcn)

        def check_security_lists(args):
            oke_public_id, vcn_public_id, oke_private_id, vcn_private_id = args
            self.assertEqual(oke_public_id, vcn_public_id, "OKE public SL should match VCN")
            self.assertEqual(oke_private_id, vcn_private_id, "OKE private SL should match VCN")

        assert oke.oke_public_security_list is not None
        assert oke.oke_private_security_list is not None
        return pulumi.Output.all(
            oke.oke_public_security_list.id,
            vcn.public_security_list.id,
            oke.oke_private_security_list.id,
            vcn.private_security_list.id,
        ).apply(check_security_lists)

    def test_oke_nsgs_created(self):
        """Test that OkeCluster creates all four NSGs."""
        oke = _make_cluster(self._make_vcn())

        self.assertIsNotNone(oke.api_nsg, "api_nsg must be created")
        self.assertIsNotNone(oke.lb_nsg, "lb_nsg must be created")
        self.assertIsNotNone(oke.worker_nsg, "worker_nsg must be created")
        self.assertIsNotNone(oke.pod_nsg, "pod_nsg must be created")

    @pulumi.runtime.test
    def test_oke_nsgs_have_ids(self):
        """Test that all four NSGs expose Output IDs."""
        oke = _make_cluster(self._make_vcn())

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

    def test_kubectl_allowed_cidrs_stored(self):
        """Test that kubectl_allowed_cidrs are stored on the cluster."""
        cidrs = ["10.0.0.0/8", "192.168.1.0/24"]
        oke = OkeCluster(
            name="test-kubectl-cidrs",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            kubernetes_version="v1.28.2",
            node_pools=[_DEFAULT_POOL],
            kubectl_allowed_cidrs=cidrs,
        )
        self.assertEqual(oke.kubectl_allowed_cidrs, cidrs)

    def test_kubectl_empty_cidrs_stored(self):
        """Test that an empty kubectl_allowed_cidrs list is stored correctly."""
        oke = OkeCluster(
            name="test-kubectl-empty",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            kubernetes_version="v1.28.2",
            node_pools=[_DEFAULT_POOL],
            kubectl_allowed_cidrs=[],
        )
        self.assertEqual(oke.kubectl_allowed_cidrs, [])

    def test_kubectl_none_defaults_to_empty(self):
        """Test that omitting kubectl_allowed_cidrs defaults to no external access."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            oke = OkeCluster(
                name="test-kubectl-none",
                compartment_id="ocid1.compartment.test",
                vcn=self._make_vcn(),
                kubernetes_version="v1.28.2",
                node_pools=[_DEFAULT_POOL],
            )
        self.assertEqual(oke.kubectl_allowed_cidrs, [])

    def test_kubectl_none_emits_warning(self):
        """Test that omitting kubectl_allowed_cidrs emits a pulumi.warn()."""
        with patch("pulumi.warn") as mock_warn:
            OkeCluster(
                name="test-kubectl-warn",
                compartment_id="ocid1.compartment.test",
                vcn=self._make_vcn(),
                kubernetes_version="v1.28.2",
                node_pools=[_DEFAULT_POOL],
            )
        mock_warn.assert_called_once()
        message = mock_warn.call_args.args[0]
        self.assertIn("kubectl_allowed_cidrs is not set", message)

    def test_oke_rejects_vcn_ref_without_oke_network_profile(self):
        """OkeCluster+VcnRef raises when the source VCN lacks the exact OKE profile."""
        vcn_ref = _make_vcn_ref()

        with self.assertRaises(RuntimeError) as ctx:
            OkeCluster(
                name="test-vcnref",
                compartment_id="ocid1.compartment.test",
                vcn=vcn_ref,
                kubernetes_version="v1.28.2",
                node_pools=[_DEFAULT_POOL],
                kubectl_allowed_cidrs=["10.0.0.0/8"],
            )

        self.assertIn("required network profile", str(ctx.exception))

    def test_oke_accepts_vcn_ref_with_oke_network_profile(self):
        """OkeCluster can deploy against a VcnRef when the source VCN exports the exact OKE profile."""
        profile_id = oke_profile_id(["10.0.0.0/8"])
        vcn_ref = _make_vcn_ref(network_profiles=[NETWORK_PROFILE_BASELINE, profile_id])

        oke = OkeCluster(
            name="test-vcnref-profile",
            compartment_id="ocid1.compartment.test",
            vcn=vcn_ref,
            kubernetes_version="v1.28.2",
            node_pools=[_DEFAULT_POOL],
            kubectl_allowed_cidrs=["10.0.0.0/8"],
        )

        self.assertIs(oke.vcn, vcn_ref)

    def test_oke_registers_oke_network_profile_on_live_vcn(self):
        """OkeCluster registers the exact OKE network profile on live Vcn."""
        vcn = self._make_vcn()
        cidrs = ["10.0.0.0/8"]

        OkeCluster(
            name="test-live-profile",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            kubernetes_version="v1.28.2",
            node_pools=[_DEFAULT_POOL],
            kubectl_allowed_cidrs=cidrs,
        )

        self.assertTrue(vcn.has_network_profile(oke_profile_id(cidrs)))

    def test_export_publishes_expected_keys(self):
        """Test that export() publishes the cluster-id and NSG-id outputs."""
        oke = _make_cluster(self._make_vcn())

        with patch("pulumi.export") as mock_export:
            oke.export()

        exported_keys = {call.args[0] for call in mock_export.call_args_list}
        # Basic keys should always be present (kubeconfig only in real runs).
        for key in (
            "test_cluster_cluster_id",
            "test_cluster_cluster_endpoint",
            "test_cluster_kubernetes_version",
            "test_cluster_lb_nsg_id",
        ):
            self.assertIn(key, exported_keys, f"export() must publish '{key}'")

    def test_get_public_security_list_ids_returns_single_id(self):
        """get_public_security_list_ids() returns a one-element list for live Vcn."""
        oke = _make_cluster(self._make_vcn())
        ids = oke.get_public_security_list_ids()
        self.assertEqual(len(ids), 1, "Expected exactly one public security list id")

    def test_get_private_security_list_ids_returns_single_id(self):
        """get_private_security_list_ids() returns a one-element list for live Vcn."""
        oke = _make_cluster(self._make_vcn())
        ids = oke.get_private_security_list_ids()
        self.assertEqual(len(ids), 1, "Expected exactly one private security list id")

    def test_get_security_list_ids_empty_when_seclists_missing(self):
        """Both accessors return [] when the underlying VCN exposes no security lists.

        Simulates the VcnRef case where the source stack did not export
        `public_security_list_id` / `private_security_list_id`: swap in a
        VcnRef stub with `public_security_list = private_security_list = None`
        on a live-constructed cluster and assert the accessors return `[]`.
        """
        # Start from a valid live-Vcn cluster so construction succeeds.
        oke = _make_cluster(self._make_vcn())

        # Replace the VCN handle with a VcnRef that reports no security-list
        # OCIDs (mirrors a source stack that did not export them).
        vcn_ref = VcnRef(
            vcn_id="ocid1.vcn.test",
            public_subnet_id="ocid1.subnet.public.test",
            private_subnet_id="ocid1.subnet.private.test",
            public_subnet_cidr="10.0.48.0/21",
            private_subnet_cidr="10.0.0.0/19",
            cidr_block="10.0.0.0/18",
            cloudspells_network_schema=CLOUDSPELLS_OCI_VCN_SCHEMA,
            network_profiles=[NETWORK_PROFILE_BASELINE],
            # No security-list OCIDs → accessors should yield [].
        )
        oke.vcn = vcn_ref

        self.assertIsNone(vcn_ref.public_security_list)
        self.assertIsNone(vcn_ref.private_security_list)
        self.assertEqual(oke.get_public_security_list_ids(), [])
        self.assertEqual(oke.get_private_security_list_ids(), [])


class TestOkeClusterEnhanced(unittest.TestCase):
    """Test cases for OkeClusterEnhanced (enhanced cluster variant)."""

    def _make_vcn(self) -> Vcn:
        """Create a fresh VCN for each test to prevent shared mutable state."""
        return Vcn(
            name="oke-enh-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

    @pulumi.runtime.test
    def test_enhanced_cluster_created(self):
        """Test that OkeClusterEnhanced constructs and exposes a cluster."""
        oke = OkeClusterEnhanced(
            name="test-enhanced",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            kubernetes_version="v1.28.2",
            node_pools=[_DEFAULT_POOL],
            kubectl_allowed_cidrs=["10.0.0.0/8"],
        )
        self.assertIsNotNone(oke.cluster)

        def check_cluster(cluster_id):
            self.assertIsNotNone(cluster_id, "Enhanced OKE cluster must be created")

        return oke.cluster.id.apply(check_cluster)

    def test_enhanced_cluster_type_is_enhanced(self):
        """OkeClusterEnhanced sets _CLUSTER_TYPE='ENHANCED_CLUSTER'."""
        self.assertEqual(OkeClusterEnhanced._CLUSTER_TYPE, "ENHANCED_CLUSTER")
        self.assertEqual(OkeCluster._CLUSTER_TYPE, "BASIC_CLUSTER")


if __name__ == "__main__":
    unittest.main()
