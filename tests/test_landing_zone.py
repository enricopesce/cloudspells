"""Unit tests for the LandingZone foundation spell."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci._network_profiles import (
    NETWORK_PROFILE_BASELINE,
    NETWORK_PROFILE_BASTION,
)
from cloudspells.providers.oci.compute import ComputeInstance
from cloudspells.providers.oci.landing_zone import LandingZone
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import APP_SERVER

_COMPARTMENT = "ocid1.compartment.test"
_TENANCY = "ocid1.tenancy.test"


def _make_landing_zone(name: str) -> LandingZone:
    """Create a fresh LandingZone for each test to prevent shared state."""
    return LandingZone(
        name=name,
        compartment_id=_COMPARTMENT,
        tenancy_id=_TENANCY,
        allowed_client_cidrs=["203.0.113.0/24"],
    )


class TestLandingZone(unittest.TestCase):
    """Test cases for the LandingZone spell."""

    def test_landing_zone_creates_foundation_components(self):
        """LandingZone creates the VCN and IAM baseline at construction."""
        lz = _make_landing_zone("lz-foundation")

        self.assertIsNotNone(lz.vcn)
        self.assertIsNotNone(lz.admin_group)

    def test_network_not_finalized_before_finalize(self):
        """Construction accumulates rules without materialising subnets."""
        lz = _make_landing_zone("lz-lazy")

        self.assertIsNone(lz.bastion)
        self.assertIsNone(lz.vcn.public_subnet)
        self.assertIsNone(lz.vcn.private_subnet)

    def test_bastion_profile_registered_at_construction(self):
        """The Bastion SSH rule is registered before any finalisation."""
        lz = _make_landing_zone("lz-profile")

        self.assertTrue(lz.vcn.has_network_profile(NETWORK_PROFILE_BASTION))
        self.assertTrue(lz.vcn.has_network_profile(NETWORK_PROFILE_BASELINE))

    def test_finalize_materialises_network_and_bastion(self):
        """finalize() creates subnets, flow logs, and the Bastion."""
        lz = _make_landing_zone("lz-finalize")

        lz.finalize()

        self.assertIsNotNone(lz.bastion)
        self.assertIsNotNone(lz.vcn.public_subnet)
        self.assertIsNotNone(lz.vcn.private_subnet)
        self.assertIsNotNone(lz.vcn.secure_subnet)
        self.assertIsNotNone(lz.vcn.management_subnet)
        self.assertIsNotNone(lz.vcn.flow_logs, "flow logs must always be enabled")

    def test_finalize_is_idempotent(self):
        """A second finalize() call reuses the existing Bastion."""
        lz = _make_landing_zone("lz-idempotent")

        lz.finalize()
        first_bastion = lz.bastion
        lz.finalize()

        self.assertIs(lz.bastion, first_bastion)

    def test_raises_when_allowed_client_cidrs_is_none(self):
        """LandingZone fails fast when the Bastion CIDR allow list is missing."""
        with self.assertRaises(ValueError) as ctx:
            LandingZone(
                name="lz-no-cidrs",
                compartment_id=_COMPARTMENT,
                tenancy_id=_TENANCY,
                allowed_client_cidrs=None,
            )
        self.assertIn("allowed_client_cidrs", str(ctx.exception))

    def test_workload_between_construction_and_finalize(self):
        """Workload spells declared before finalize() register their rules."""
        lz = _make_landing_zone("lz-workload")

        app_nsg = Nsg(
            "app",
            role=APP_SERVER,
            vcn=lz.vcn,
            compartment_id=_COMPARTMENT,
        )
        # ComputeInstance finalises the network itself; the landing zone's
        # Bastion rule was pre-registered so this must not raise.
        ComputeInstance(
            name="app-1",
            compartment_id=_COMPARTMENT,
            image_id="ocid1.image.test",
            nsg=app_nsg,
        )
        lz.finalize()

        self.assertIsNotNone(lz.bastion)

    @pulumi.runtime.test
    def test_bastion_id_output(self):
        """get_bastion_id() returns a resolvable Output after finalize()."""
        lz = _make_landing_zone("lz-bastion-id")
        lz.finalize()

        def check(bastion_id):
            self.assertIsNotNone(bastion_id, "Bastion must be created")

        return lz.get_bastion_id().apply(check)

    @pulumi.runtime.test
    def test_bastion_endpoint_output(self):
        """get_bastion_endpoint() returns a resolvable Output after finalize()."""
        lz = _make_landing_zone("lz-bastion-ep")
        lz.finalize()

        def check(endpoint):
            self.assertIsNotNone(endpoint, "Bastion endpoint must be set")

        return lz.get_bastion_endpoint().apply(check)

    @pulumi.runtime.test
    def test_admin_group_output(self):
        """get_admin_group_id() returns a resolvable Output."""
        lz = _make_landing_zone("lz-admin")

        def check(group_id):
            self.assertIsNotNone(group_id, "Admin group must be created")

        return lz.get_admin_group_id().apply(check)

    def test_bastion_accessors_raise_before_finalize(self):
        """Bastion accessors fail with guidance before finalize()."""
        lz = _make_landing_zone("lz-early-access")

        with self.assertRaises(RuntimeError) as ctx:
            lz.get_bastion_id()
        self.assertIn("finalize()", str(ctx.exception))

        with self.assertRaises(RuntimeError):
            lz.get_bastion_endpoint()

    @pulumi.runtime.test
    def test_export_finalizes_and_publishes(self):
        """export() finalises the landing zone and publishes outputs."""
        lz = _make_landing_zone("lz-export")

        lz.export()

        self.assertIsNotNone(lz.bastion)
        self.assertIsNotNone(lz.vcn.public_subnet)


if __name__ == "__main__":
    unittest.main()
