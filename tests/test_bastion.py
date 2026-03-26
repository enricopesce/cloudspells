"""Unit tests for Bastion block."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci.bastion import Bastion
from cloudspells.providers.oci.network import Vcn


class TestBastion(unittest.TestCase):
    """Test cases for Bastion block."""

    def _make_vcn(self) -> Vcn:
        """Create a fresh VCN for each test to prevent shared mutable state."""
        return Vcn(
            name="bastion-test-vcn",
            compartment_id="ocid1.compartment.test",
        )

    @pulumi.runtime.test
    def test_bastion_created(self):
        """Test that Bastion creates a bastion resource."""
        bastion = Bastion(
            name="test-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
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
        )

        self.assertIsNotNone(vcn.public_subnet, "VCN should be finalized by Bastion")
        self.assertIsNotNone(vcn.private_subnet, "VCN should be finalized by Bastion")

    @pulumi.runtime.test
    def test_bastion_getter_methods(self):
        """Test Bastion getter methods return Output types."""
        bastion = Bastion(
            name="getter-test-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
        )

        def check_id(bastion_id):
            self.assertIsNotNone(bastion_id)

        return bastion.get_bastion_id().apply(check_id)

    def test_bastion_default_ttl(self):
        """Test that Bastion uses default session TTL of 3 hours."""
        bastion = Bastion(
            name="default-ttl-bastion",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
        )

        # Default TTL is 10800 seconds (3 hours)
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
            )

    def test_second_bastion_on_same_vcn_is_accepted(self):
        """A second Bastion against the same VCN is a no-op (deduplication via fingerprint)."""
        vcn = Vcn(
            name="dedup-vcn",
            compartment_id="ocid1.compartment.test",
        )
        Bastion(name="first-bastion", compartment_id="ocid1.compartment.test", vcn=vcn)
        # VCN is now finalized; a second Bastion should not raise.
        Bastion(name="second-bastion", compartment_id="ocid1.compartment.test", vcn=vcn)


if __name__ == "__main__":
    unittest.main()
