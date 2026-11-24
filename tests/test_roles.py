"""Unit tests for the Role system and Nsg.serves() relationship API."""

import unittest
from unittest.mock import patch

import pulumi

from tests.mocks import set_mocks

set_mocks()

from cloudspells.providers.oci.network import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    Vcn,
)
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import (
    APP_SERVER,
    CACHE,
    DATABASE,
    INTERNET_EDGE,
    MANAGEMENT,
    Role,
)

COMP_ID = "ocid1.compartment.oc1..test"


class TestRoleDataclass(unittest.TestCase):
    """Tests for the Role dataclass and predefined role constants."""

    def test_internet_edge_subnet_tier(self) -> None:
        """INTERNET_EDGE is placed in the public subnet."""
        self.assertEqual(INTERNET_EDGE.subnet_tier, SUBNET_PUBLIC)

    def test_app_server_subnet_tier(self) -> None:
        """APP_SERVER is placed in the private subnet."""
        self.assertEqual(APP_SERVER.subnet_tier, SUBNET_PRIVATE)

    def test_database_subnet_tier(self) -> None:
        """DATABASE is placed in the secure subnet."""
        self.assertEqual(DATABASE.subnet_tier, SUBNET_SECURE)

    def test_cache_subnet_tier(self) -> None:
        """CACHE is placed in the private subnet."""
        self.assertEqual(CACHE.subnet_tier, SUBNET_PRIVATE)

    def test_management_subnet_tier(self) -> None:
        """MANAGEMENT is placed in the management subnet."""
        self.assertEqual(MANAGEMENT.subnet_tier, SUBNET_MANAGEMENT)

    def test_internet_edge_no_egress(self) -> None:
        """INTERNET_EDGE has no internet or services egress (uses IGW route directly)."""
        self.assertFalse(INTERNET_EDGE.egress_internet)
        self.assertFalse(INTERNET_EDGE.egress_services)

    def test_internet_edge_no_management_ssh(self) -> None:
        """INTERNET_EDGE does not accept SSH from an upstream — it IS the upstream."""
        self.assertFalse(INTERNET_EDGE.accept_management_ssh)

    def test_app_server_egress_flags(self) -> None:
        """APP_SERVER egresses to both internet (NAT) and Oracle Services."""
        self.assertTrue(APP_SERVER.egress_internet)
        self.assertTrue(APP_SERVER.egress_services)

    def test_app_server_accepts_management_ssh(self) -> None:
        """APP_SERVER accepts SSH management channel from upstream."""
        self.assertTrue(APP_SERVER.accept_management_ssh)

    def test_database_egress_services_only(self) -> None:
        """DATABASE egresses to Oracle Services only — no internet path."""
        self.assertFalse(DATABASE.egress_internet)
        self.assertTrue(DATABASE.egress_services)

    def test_database_accepts_management_ssh(self) -> None:
        """DATABASE accepts SSH management from the app tier."""
        self.assertTrue(DATABASE.accept_management_ssh)

    def test_management_no_internet_egress(self) -> None:
        """MANAGEMENT has no internet path — Service Gateway only."""
        self.assertFalse(MANAGEMENT.egress_internet)
        self.assertTrue(MANAGEMENT.egress_services)

    def test_custom_role_composition(self) -> None:
        """A custom Role can be composed with arbitrary attribute values."""
        custom = Role(
            name="TEST_ROLE",
            subnet_tier=SUBNET_PRIVATE,
            egress_internet=True,
            egress_services=False,
            accept_management_ssh=False,
        )
        self.assertEqual(custom.subnet_tier, SUBNET_PRIVATE)
        self.assertTrue(custom.egress_internet)
        self.assertFalse(custom.egress_services)
        self.assertFalse(custom.accept_management_ssh)

    def test_cache_not_equal_to_app_server(self) -> None:
        """Test that CACHE and APP_SERVER are not equal after name field addition."""
        self.assertNotEqual(CACHE, APP_SERVER)

    def test_role_name_field_uniqueness(self) -> None:
        """Test that all predefined role constants have distinct name values."""
        names = [INTERNET_EDGE.name, APP_SERVER.name, DATABASE.name, CACHE.name, MANAGEMENT.name]
        self.assertEqual(len(names), len(set(names)))


class TestNsgWithRole(unittest.TestCase):
    """Tests for Nsg constructed with role= and ports=."""

    def _make_vcn(self, name: str = "lab") -> Vcn:
        return Vcn(name=name, compartment_id=COMP_ID)

    @pulumi.runtime.test
    def test_nsg_stores_role(self):
        """Nsg stores the role attribute when one is supplied."""
        vcn = self._make_vcn()
        nsg = Nsg("lb", role=INTERNET_EDGE, ports=[80, 443], vcn=vcn, compartment_id=COMP_ID)
        self.assertEqual(nsg.role, INTERNET_EDGE)

    @pulumi.runtime.test
    def test_nsg_role_none_by_default(self):
        """Nsg.role is None when no role is supplied (existing API unchanged)."""
        vcn = self._make_vcn("no-role")
        nsg = Nsg("plain", vcn=vcn, compartment_id=COMP_ID)
        self.assertIsNone(nsg.role)

    @pulumi.runtime.test
    def test_nsg_id_is_output(self):
        """Nsg.id is a pulumi.Output regardless of role."""
        vcn = self._make_vcn("id-test")
        nsg = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        self.assertIsInstance(nsg.id, pulumi.Output)

    def test_roles_configure_only_their_group(self) -> None:
        """Role defaults use NSGs on an already finalized network."""
        vcn = self._make_vcn("role-policy")
        vcn.finalize_network()
        with (
            patch.object(Nsg, "allow_from_cidr", autospec=True, side_effect=Nsg.allow_from_cidr) as ingress,
            patch.object(Nsg, "allow_to_cidr", autospec=True, side_effect=Nsg.allow_to_cidr) as egress,
            patch.object(Nsg, "allow_to_services", autospec=True, side_effect=Nsg.allow_to_services) as services,
        ):
            lb = Nsg("lb", role=INTERNET_EDGE, ports=[80, 443, 22, 80], vcn=vcn, compartment_id=COMP_ID)
            web = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
            db = Nsg("db", role=DATABASE, vcn=vcn, compartment_id=COMP_ID)

        self.assertEqual(
            [call.args[:4] for call in ingress.call_args_list],
            [
                (lb, "internet-in-80", 80, "0.0.0.0/0"),
                (lb, "internet-in-443", 443, "0.0.0.0/0"),
                (lb, "internet-in-22", 22, "0.0.0.0/0"),
            ],
        )
        egress.assert_called_once_with(web, "inet-out", "0.0.0.0/0")
        self.assertEqual([call.args[0] for call in services.call_args_list], [web, db])


class TestTiersModule(unittest.TestCase):
    """Tests for the tiers module and its importable symbols."""

    def test_subnet_tier_importable_from_tiers_module(self) -> None:
        """Test that SubnetTier and tier constants are importable from tiers module."""
        from cloudspells.core.abstractions.tiers import (
            SUBNET_MANAGEMENT,
            SUBNET_PRIVATE,
            SUBNET_PUBLIC,
            SUBNET_SECURE,
        )

        self.assertEqual(SUBNET_PUBLIC, "public")
        self.assertEqual(SUBNET_PRIVATE, "private")
        self.assertEqual(SUBNET_SECURE, "secure")
        self.assertEqual(SUBNET_MANAGEMENT, "management")


if __name__ == "__main__":
    unittest.main()
