"""Unit tests for the Role system and Nsg.serves() relationship API."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pulumi

from tests.mocks import set_mocks

set_mocks()

from providers.oci.network import (
    SUBNET_MANAGEMENT,
    SUBNET_PRIVATE,
    SUBNET_PUBLIC,
    SUBNET_SECURE,
    Vcn,
)
from providers.oci.nsg import Nsg
from providers.oci.roles import (
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
            subnet_tier=SUBNET_PRIVATE,
            egress_internet=True,
            egress_services=False,
            accept_management_ssh=False,
        )
        self.assertEqual(custom.subnet_tier, SUBNET_PRIVATE)
        self.assertTrue(custom.egress_internet)
        self.assertFalse(custom.egress_services)
        self.assertFalse(custom.accept_management_ssh)


class TestNsgWithRole(unittest.TestCase):
    """Tests for Nsg constructed with role= and ports=."""

    def _make_vcn(self, name: str = "lab") -> Vcn:
        return Vcn(name=name, compartment_id=COMP_ID)

    @pulumi.runtime.test
    def test_nsg_stores_role(self) -> None:
        """Nsg stores the role attribute when one is supplied."""
        vcn = self._make_vcn()
        nsg = Nsg("lb", role=INTERNET_EDGE, ports=[80, 443], vcn=vcn, compartment_id=COMP_ID)
        self.assertEqual(nsg.role, INTERNET_EDGE)

    @pulumi.runtime.test
    def test_nsg_role_none_by_default(self) -> None:
        """Nsg.role is None when no role is supplied (existing API unchanged)."""
        vcn = self._make_vcn("no-role")
        nsg = Nsg("plain", vcn=vcn, compartment_id=COMP_ID)
        self.assertIsNone(nsg.role)

    @pulumi.runtime.test
    def test_nsg_id_is_output(self) -> None:
        """Nsg.id is a pulumi.Output regardless of role."""
        vcn = self._make_vcn("id-test")
        nsg = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        self.assertIsInstance(nsg.id, pulumi.Output)

    @pulumi.runtime.test
    def test_internet_edge_registers_sl_rules(self) -> None:
        """INTERNET_EDGE role registers port ingress rules on the public security list."""
        vcn = self._make_vcn("ie-sl")
        _nsg = Nsg("lb", role=INTERNET_EDGE, ports=[80, 443, 22], vcn=vcn, compartment_id=COMP_ID)

        # The VCN accumulator should have received at least the three port rules
        # + ICMP in + ICMP out fingerprints.
        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("public-ingress-tcp-80", fingerprints)
        self.assertIn("public-ingress-tcp-443", fingerprints)
        self.assertIn("public-ingress-tcp-22", fingerprints)
        self.assertIn("public-ingress-icmp-mtu", fingerprints)
        self.assertIn("public-egress-icmp-mtu", fingerprints)

    @pulumi.runtime.test
    def test_app_server_registers_sl_rules(self) -> None:
        """APP_SERVER role registers egress rules on the private security list."""
        vcn = self._make_vcn("as-sl")
        _nsg = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("private-egress-all-services", fingerprints)
        self.assertIn("private-egress-all-internet", fingerprints)

    @pulumi.runtime.test
    def test_database_registers_sl_rules(self) -> None:
        """DATABASE role registers services-egress rule on the secure security list."""
        vcn = self._make_vcn("db-sl")
        _nsg = Nsg("db", role=DATABASE, vcn=vcn, compartment_id=COMP_ID)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("secure-egress-all-services", fingerprints)
        self.assertNotIn("secure-egress-all-internet", fingerprints)

    @pulumi.runtime.test
    def test_duplicate_app_server_nsgs_deduplicates_sl_rules(self) -> None:
        """Multiple NSGs of the same role add security list rules only once."""
        vcn = self._make_vcn("dedup")
        _web1 = Nsg("web-1", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        _web2 = Nsg("web-2", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        _web3 = Nsg("web-3", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

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
    def test_serves_registers_cross_subnet_app_port(self) -> None:
        """serves() registers cross-subnet Security List rules for the app port."""
        vcn, lb, web, _db = self._make_trio("serves-app")
        lb.serves(web, port=8080)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("public-egress-tcp-8080-to-private", fingerprints)
        self.assertIn("private-ingress-tcp-8080-from-public", fingerprints)

    @pulumi.runtime.test
    def test_serves_registers_ssh_management_by_default(self) -> None:
        """serves() adds SSH (22) cross-subnet rules when with_ssh=True (default)."""
        vcn, lb, web, _db = self._make_trio("serves-ssh")
        lb.serves(web, port=8080)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("public-egress-tcp-22-to-private", fingerprints)
        self.assertIn("private-ingress-tcp-22-from-public", fingerprints)

    @pulumi.runtime.test
    def test_serves_suppresses_ssh_when_with_ssh_false(self) -> None:
        """serves(with_ssh=False) omits the SSH management channel."""
        vcn, lb, web, _db = self._make_trio("serves-no-ssh")
        lb.serves(web, port=8080, with_ssh=False)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertNotIn("public-egress-tcp-22-to-private", fingerprints)
        self.assertNotIn("private-ingress-tcp-22-from-public", fingerprints)

    @pulumi.runtime.test
    def test_serves_web_to_db(self) -> None:
        """web→db serves() registers private↔secure cross-subnet rules."""
        vcn, _lb, web, db = self._make_trio("serves-web-db")
        web.serves(db, port=5432)

        fingerprints = vcn._applied_ambient_rule_fingerprints
        self.assertIn("private-egress-tcp-5432-to-secure", fingerprints)
        self.assertIn("secure-ingress-tcp-5432-from-private", fingerprints)
        self.assertIn("private-egress-tcp-22-to-secure", fingerprints)
        self.assertIn("secure-ingress-tcp-22-from-private", fingerprints)

    @pulumi.runtime.test
    def test_serves_without_roles_skips_sl_rules(self) -> None:
        """serves() between role-less NSGs creates NSG rules but no SL rules."""
        vcn = Vcn(name="no-role-serves", compartment_id=COMP_ID)
        a = Nsg("a", vcn=vcn, compartment_id=COMP_ID)
        b = Nsg("b", vcn=vcn, compartment_id=COMP_ID)
        a.serves(b, port=9000)

        # No SL fingerprints should have been registered
        self.assertEqual(len(vcn._applied_ambient_rule_fingerprints), 0)

    @pulumi.runtime.test
    def test_serves_same_tier_skips_sl_rules(self) -> None:
        """serves() between NSGs in the same subnet tier adds no SL cross-subnet rules."""
        vcn = Vcn(name="same-tier", compartment_id=COMP_ID)
        web1 = Nsg("web-1", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        web2 = Nsg("web-2", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        initial_fp_count = len(vcn._applied_ambient_rule_fingerprints)
        web1.serves(web2, port=8080)

        # No new cross-subnet fingerprints (both are private tier)
        new_fps = vcn._applied_ambient_rule_fingerprints - set(
            list(vcn._applied_ambient_rule_fingerprints)[:initial_fp_count]
        )
        cross_subnet = {fp for fp in new_fps if "to-" in fp or "from-" in fp}
        self.assertEqual(len(cross_subnet), 0)


class TestComputeInstanceNsgShorthand(unittest.TestCase):
    """Tests for ComputeInstance nsg= parameter and subnet inference."""

    @pulumi.runtime.test
    def test_nsg_shorthand_infers_private_subnet(self) -> None:
        """ComputeInstance with nsg=APP_SERVER NSG is placed in private subnet."""
        from providers.oci.compute import ComputeInstance

        vcn = Vcn(name="ci-priv", compartment_id=COMP_ID)
        web_nsg = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        web_nsg.serves(Nsg("db", role=DATABASE, vcn=vcn, compartment_id=COMP_ID), port=5432)

        instance = ComputeInstance(
            name="web-1",
            compartment_id=COMP_ID,
            vcn=vcn,
            nsg=web_nsg,
        )
        self.assertEqual(instance.subnet, "private")

    @pulumi.runtime.test
    def test_nsg_shorthand_infers_public_subnet(self) -> None:
        """ComputeInstance with nsg=INTERNET_EDGE NSG is placed in public subnet."""
        from providers.oci.compute import ComputeInstance

        vcn = Vcn(name="ci-pub", compartment_id=COMP_ID)
        lb_nsg = Nsg("lb", role=INTERNET_EDGE, ports=[80], vcn=vcn, compartment_id=COMP_ID)

        instance = ComputeInstance(
            name="lb-1",
            compartment_id=COMP_ID,
            vcn=vcn,
            nsg=lb_nsg,
        )
        self.assertEqual(instance.subnet, "public")

    @pulumi.runtime.test
    def test_nsg_shorthand_infers_secure_subnet(self) -> None:
        """ComputeInstance with nsg=DATABASE NSG is placed in secure subnet."""
        from providers.oci.compute import ComputeInstance

        vcn = Vcn(name="ci-sec", compartment_id=COMP_ID)
        db_nsg = Nsg("db", role=DATABASE, vcn=vcn, compartment_id=COMP_ID)

        instance = ComputeInstance(
            name="db-1",
            compartment_id=COMP_ID,
            vcn=vcn,
            nsg=db_nsg,
        )
        self.assertEqual(instance.subnet, "secure")

    @pulumi.runtime.test
    def test_nsg_shorthand_sets_nsg_ids(self) -> None:
        """ComputeInstance with nsg= sets nsg_ids to [nsg.id]."""
        from providers.oci.compute import ComputeInstance

        vcn = Vcn(name="ci-ids", compartment_id=COMP_ID)
        web_nsg = Nsg("web", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        instance = ComputeInstance(
            name="web-x",
            compartment_id=COMP_ID,
            vcn=vcn,
            nsg=web_nsg,
        )
        self.assertEqual(len(instance.nsg_ids), 1)

    @pulumi.runtime.test
    def test_old_api_unchanged(self) -> None:
        """ComputeInstance with explicit subnet= and nsg_ids= still works."""
        from providers.oci.compute import ComputeInstance
        from providers.oci.network import SUBNET_PRIVATE

        vcn = Vcn(name="ci-old", compartment_id=COMP_ID)
        web_nsg = Nsg("web-old", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        instance = ComputeInstance(
            name="web-old",
            compartment_id=COMP_ID,
            vcn=vcn,
            subnet=SUBNET_PRIVATE,
            nsg_ids=[web_nsg.id],
        )
        self.assertEqual(instance.subnet, "private")
        self.assertEqual(len(instance.nsg_ids), 1)


if __name__ == "__main__":
    unittest.main()
