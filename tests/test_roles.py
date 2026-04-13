"""Unit tests for the Role system and Nsg.serves() relationship API."""

import unittest

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

    @pulumi.runtime.test
    def test_internet_edge_registers_sl_rules(self):
        """INTERNET_EDGE role registers port ingress rules on the public security list."""
        vcn = self._make_vcn("ie-sl")
        Nsg("lb", role=INTERNET_EDGE, ports=[80, 443, 22], vcn=vcn, compartment_id=COMP_ID)

        # The VCN accumulator should have received the three port rules.
        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("public-ingress-tcp-80", fingerprints)
        self.assertIn("public-ingress-tcp-443", fingerprints)
        self.assertIn("public-ingress-tcp-22", fingerprints)

    @pulumi.runtime.test
    def test_app_server_registers_sl_rules(self):
        """APP_SERVER role registers egress rules on the private security list."""
        vcn = self._make_vcn("as-sl")
        Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("private-egress-all-services", fingerprints)
        self.assertIn("private-egress-all-internet", fingerprints)

    @pulumi.runtime.test
    def test_database_registers_sl_rules(self):
        """DATABASE role registers services-egress rule on the secure security list."""
        vcn = self._make_vcn("db-sl")
        Nsg("db", role=DATABASE, vcn=vcn, compartment_id=COMP_ID)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("secure-egress-all-services", fingerprints)
        self.assertNotIn("secure-egress-all-internet", fingerprints)

    @pulumi.runtime.test
    def test_duplicate_app_server_nsgs_deduplicates_sl_rules(self):
        """Multiple NSGs of the same role add security list rules only once."""
        vcn = self._make_vcn("dedup")
        Nsg("web-1", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        Nsg("web-2", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        Nsg("web-3", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        # All three NSGs share the same fingerprints: private_egress_rules must
        # have exactly 2 entries (services + internet) — not 6 (2 × 3 NSGs).
        self.assertEqual(len(vcn._private_egress_rules), 2)


class TestNsgServes(unittest.TestCase):
    """Tests for the Nsg.serves() bilateral relationship method."""

    def _make_trio(self, vcn_name: str = "trio") -> tuple[Vcn, Nsg, Nsg, Nsg]:
        vcn = Vcn(name=vcn_name, compartment_id=COMP_ID)
        lb = Nsg("lb", role=INTERNET_EDGE, ports=[80], vcn=vcn, compartment_id=COMP_ID)
        web = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        db = Nsg("db", role=DATABASE, vcn=vcn, compartment_id=COMP_ID)
        return vcn, lb, web, db

    @pulumi.runtime.test
    def test_serves_registers_cross_subnet_app_port(self):
        """serves() registers cross-subnet Security List rules for the app port."""
        vcn, lb, web, _db = self._make_trio("serves-app")
        lb.serves(web, port=8080)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("public-egress-tcp-8080-to-private", fingerprints)
        self.assertIn("private-ingress-tcp-8080-from-public", fingerprints)

    @pulumi.runtime.test
    def test_serves_registers_ssh_management_by_default(self):
        """serves() adds SSH (22) cross-subnet rules when with_ssh=True (default)."""
        vcn, lb, web, _db = self._make_trio("serves-ssh")
        lb.serves(web, port=8080)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("public-egress-tcp-22-to-private", fingerprints)
        self.assertIn("private-ingress-tcp-22-from-public", fingerprints)

    @pulumi.runtime.test
    def test_serves_suppresses_ssh_when_with_ssh_false(self):
        """serves(with_ssh=False) omits the SSH management channel."""
        vcn, lb, web, _db = self._make_trio("serves-no-ssh")
        lb.serves(web, port=8080, with_ssh=False)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertNotIn("public-egress-tcp-22-to-private", fingerprints)
        self.assertNotIn("private-ingress-tcp-22-from-public", fingerprints)

    @pulumi.runtime.test
    def test_serves_web_to_db(self):
        """web→db serves() registers private↔secure cross-subnet rules."""
        vcn, _lb, web, db = self._make_trio("serves-web-db")
        web.serves(db, port=5432)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("private-egress-tcp-5432-to-secure", fingerprints)
        self.assertIn("secure-ingress-tcp-5432-from-private", fingerprints)
        self.assertIn("private-egress-tcp-22-to-secure", fingerprints)
        self.assertIn("secure-ingress-tcp-22-from-private", fingerprints)

    @pulumi.runtime.test
    def test_serves_without_roles_skips_sl_rules(self):
        """serves() between role-less NSGs creates NSG rules but no SL rules."""
        vcn = Vcn(name="no-role-serves", compartment_id=COMP_ID)
        a = Nsg("a", vcn=vcn, compartment_id=COMP_ID)
        b = Nsg("b", vcn=vcn, compartment_id=COMP_ID)
        a.serves(b, port=9000)

        # No SL fingerprints should have been registered
        self.assertEqual(len(vcn._applied_ambient_rule_fingerprints), 0)

    @pulumi.runtime.test
    def test_serves_same_tier_skips_sl_rules(self):
        """serves() between NSGs in the same subnet tier adds no SL cross-subnet rules."""
        vcn = Vcn(name="same-tier", compartment_id=COMP_ID)
        web1 = Nsg("web-1", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        web2 = Nsg("web-2", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        before = frozenset(vcn._applied_ambient_rule_fingerprints)
        web1.serves(web2, port=8080)

        # No new cross-subnet fingerprints (both are private tier)
        after = frozenset(vcn._applied_ambient_rule_fingerprints)
        cross_subnet = {fp for fp in (after - before) if "to-" in fp or "from-" in fp}
        self.assertEqual(len(cross_subnet), 0)


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
