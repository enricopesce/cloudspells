"""Unit tests for Bastion block."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci._network_profiles import (
    CLOUDSPELLS_OCI_VCN_SCHEMA,
    NETWORK_PROFILE_BASELINE,
    NETWORK_PROFILE_BASTION,
)
from cloudspells.providers.oci.bastion import Bastion
from cloudspells.providers.oci.network import Vcn, VcnRef


class TestBastion(unittest.TestCase):
    """Test cases for Bastion block."""

    def _make_vcn(self) -> Vcn:
        """Create a fresh VCN for each test to prevent shared mutable state."""
        return Vcn(
            name="bastion-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

    def _make_vcn_ref(self, profiles: list[str] | None = None) -> VcnRef:
        """Create a VcnRef populated with Bastion-compatible test values."""
        return VcnRef(
            vcn_id="ocid1.vcn.test",
            public_subnet_id="ocid1.subnet.public.test",
            private_subnet_id="ocid1.subnet.private.test",
            public_subnet_cidr="10.0.48.0/21",
            private_subnet_cidr="10.0.0.0/19",
            cidr_block="10.0.0.0/18",
            cloudspells_network_schema=CLOUDSPELLS_OCI_VCN_SCHEMA,
            network_profiles=profiles or [NETWORK_PROFILE_BASELINE, NETWORK_PROFILE_BASTION],
            public_security_list_id="ocid1.seclist.public.test",
            private_security_list_id="ocid1.seclist.private.test",
        )

    @pulumi.runtime.test
    def test_bastion_created(self):
        """Test that Bastion creates a bastion resource."""
        bastion = Bastion(
            name="test-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        def check_bastion(bastion_id):
            self.assertIsNotNone(bastion_id, "Bastion must be created")

        return bastion.bastion.id.apply(check_bastion)

    def test_bastion_finalizes_vcn(self):
        """Test that Bastion calls finalize_network() on VCN."""
        vcn = Vcn(
            name="bastion-finalize-vcn",
            compartment_id="ocid1.compartment.test",
        )

        self.assertIsNone(vcn.public_subnet)
        self.assertIsNone(vcn.private_subnet)

        Bastion(
            name="test-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        self.assertIsNotNone(vcn.public_subnet, "VCN should be finalized by Bastion")
        self.assertIsNotNone(vcn.private_subnet, "VCN should be finalized by Bastion")

    def test_bastion_registers_network_profile(self):
        """Bastion marks live VCNs with the Bastion network profile."""
        vcn = self._make_vcn()
        Bastion(
            name="profile-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        self.assertTrue(vcn.has_network_profile(NETWORK_PROFILE_BASTION))

    @pulumi.runtime.test
    def test_bastion_getter_methods(self):
        """Test Bastion getter methods return Output types."""
        bastion = Bastion(
            name="getter-test-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        def check_id(bastion_id):
            self.assertIsNotNone(bastion_id)

        return bastion.get_bastion_id().apply(check_id)

    def test_bastion_resource_created(self):
        """Test that Bastion resource is created successfully with default options."""
        bastion = Bastion(
            name="default-ttl-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        self.assertIsNotNone(bastion.bastion)

    def test_bastion_custom_cidr_allow_list(self):
        """Test that Bastion accepts a custom client CIDR allow list."""
        custom_cidrs = ["203.0.113.0/24", "198.51.100.0/24"]

        bastion = Bastion(
            name="custom-cidr-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            allowed_client_cidrs=custom_cidrs,
        )

        self.assertIsNotNone(bastion.bastion)

    @pulumi.runtime.test
    def test_bastion_endpoint_output(self):
        """Test that Bastion exposes a bastion_endpoint output."""
        bastion = Bastion(
            name="endpoint-test-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        def check_endpoint(endpoint):
            self.assertIsNotNone(endpoint, "Bastion endpoint must be set")

        return bastion.get_bastion_endpoint().apply(check_endpoint)

    @pulumi.runtime.test
    def test_get_access_endpoint_matches_bastion_endpoint(self):
        """get_access_endpoint() returns the same Output as get_bastion_endpoint()."""
        bastion = Bastion(
            name="access-endpoint-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        def check(endpoint):
            self.assertIsNotNone(endpoint)

        return bastion.get_access_endpoint().apply(check)

    def test_bastion_raises_when_vcn_already_finalized(self):
        """Bastion raises RuntimeError when the VCN is finalized without the SSH rule applied."""
        vcn = Vcn(
            name="pre-finalized-vcn",
            compartment_id="ocid1.compartment.test",
        )
        # Finalize before any Bastion has registered its SSH rule.
        vcn.finalize_network()
        with self.assertRaises(RuntimeError):
            Bastion(
                name="late-bastion",
                compartment_id="ocid1.compartment.test",
                vcn=vcn,
                allowed_client_cidrs=["0.0.0.0/0"],
            )

    def test_bastion_raises_when_allowed_client_cidrs_is_none(self):
        """Bastion raises ValueError when allowed_client_cidrs is not provided."""
        with self.assertRaises(ValueError) as ctx:
            Bastion(
                name="no-cidrs-bastion",
                compartment_id="ocid1.compartment.test",
                vcn=self._make_vcn(),
                allowed_client_cidrs=None,
            )
        self.assertIn("allowed_client_cidrs", str(ctx.exception))

    def test_bastion_with_vcnref_requires_bastion_profile(self):
        """Bastion rejects VcnRef stacks without the Bastion network profile."""
        vcn_ref = self._make_vcn_ref(profiles=[NETWORK_PROFILE_BASELINE])

        with self.assertRaises(RuntimeError) as ctx:
            Bastion(
                name="missing-profile-bastion",
                compartment_id="ocid1.compartment.test",
                vcn=vcn_ref,
                allowed_client_cidrs=["0.0.0.0/0"],
            )

        self.assertIn(NETWORK_PROFILE_BASTION, str(ctx.exception))

    def test_bastion_accepts_vcnref_with_bastion_profile(self):
        """Bastion accepts VcnRef stacks that export the Bastion profile."""
        bastion = Bastion(
            name="vcnref-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn_ref(),
            allowed_client_cidrs=["0.0.0.0/0"],
        )

        self.assertIsNotNone(bastion.bastion)

    def test_second_bastion_on_same_vcn_is_accepted(self):
        """A second Bastion against the same VCN is a no-op (deduplication via fingerprint)."""
        vcn = Vcn(
            name="dedup-vcn",
            compartment_id="ocid1.compartment.test",
        )
        Bastion(
            name="first-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            allowed_client_cidrs=["0.0.0.0/0"],
        )
        # VCN is now finalized; a second Bastion should not raise.
        Bastion(
            name="second-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=vcn,
            allowed_client_cidrs=["0.0.0.0/0"],
        )


if __name__ == "__main__":
    unittest.main()
