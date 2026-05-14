"""Unit tests for Nsg rule-generation helpers."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.nsg import (
    ALL,
    HTTP,
    HTTPS,
    ICMP,
    INTERNET,
    SSH,
    TCP,
    Nsg,
)
from cloudspells.providers.oci.roles import APP_SERVER, INTERNET_EDGE

COMP_ID = "ocid1.compartment.oc1..test"


class TestNsgCreation(unittest.TestCase):
    """Tests for Nsg construction and role validation."""

    def _make_vcn(self) -> Vcn:
        return Vcn(name="nsg-vcn", compartment_id=COMP_ID)

    @pulumi.runtime.test
    def test_nsg_created_without_role(self):
        """Nsg constructed without a role creates the underlying NSG resource."""
        vcn = self._make_vcn()
        nsg = Nsg("bare", vcn=vcn, compartment_id=COMP_ID)

        def check(nsg_id):
            self.assertIsNotNone(nsg_id)

        return nsg.id.apply(check)

    @pulumi.runtime.test
    def test_nsg_created_with_role(self):
        """Nsg constructed with APP_SERVER role creates the NSG resource."""
        vcn = self._make_vcn()
        nsg = Nsg("app", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        def check(nsg_id):
            self.assertIsNotNone(nsg_id)

        return nsg.id.apply(check)

    def test_internet_edge_without_ports_raises(self):
        """Nsg(role=INTERNET_EDGE) without ports raises ValueError."""
        vcn = self._make_vcn()
        with self.assertRaises(ValueError):
            Nsg("edge", role=INTERNET_EDGE, vcn=vcn, compartment_id=COMP_ID)

    def test_internet_edge_with_ports_ok(self):
        """Nsg(role=INTERNET_EDGE, ports=[HTTP, HTTPS]) does not raise."""
        vcn = self._make_vcn()
        nsg = Nsg("edge", role=INTERNET_EDGE, ports=[HTTP, HTTPS], vcn=vcn, compartment_id=COMP_ID)
        self.assertIsNotNone(nsg)

    def test_vcn_property_returns_host_network(self):
        """vcn returns the network that hosts the NSG."""
        vcn = self._make_vcn()
        nsg = Nsg("app-vcn-ref", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        self.assertIs(nsg.vcn, vcn)


class TestNsgRuleHelpers(unittest.TestCase):
    """Tests for Nsg convenience rule-generation helpers."""

    def _make_pair(self) -> tuple[Vcn, Nsg, Nsg]:
        vcn = Vcn(name="rule-vcn", compartment_id=COMP_ID)
        src = Nsg("src", vcn=vcn, compartment_id=COMP_ID)
        tgt = Nsg("tgt", vcn=vcn, compartment_id=COMP_ID)
        return vcn, src, tgt

    @pulumi.runtime.test
    def test_allow_from_cidr_creates_ingress_rule(self):
        """allow_from_cidr creates an INGRESS TCP rule with the correct direction."""
        _, src, _ = self._make_pair()
        rule = src.allow_from_cidr("https-in", HTTPS, INTERNET)

        def check(direction):
            self.assertEqual(direction, "INGRESS")

        return rule.direction.apply(check)

    @pulumi.runtime.test
    def test_nsg_rule_resource_name_uses_ordinal_slot_not_label(self):
        """NSG rule resource names use internal ordinal slots."""
        vcn = Vcn(name="rule-name-vcn", compartment_id=COMP_ID, stack_name="unit")
        nsg = Nsg("rule-name", vcn=vcn, compartment_id=COMP_ID, stack_name="unit")
        rule = nsg.allow_from_cidr("https-in", HTTPS, INTERNET)

        def check(rule_id):
            self.assertEqual(rule_id, "unit-rule-name-nsg-rule-1-id")

        return rule.id.apply(check)

    def test_duplicate_nsg_rule_label_raises(self):
        """NSG rule labels remain unique even though they no longer name resources."""
        vcn = Vcn(name="rule-dupe-vcn", compartment_id=COMP_ID, stack_name="unit")
        nsg = Nsg("rule-dupe", vcn=vcn, compartment_id=COMP_ID, stack_name="unit")

        nsg.allow_to_cidr("inet-out", INTERNET)
        with self.assertRaises(ValueError):
            nsg.allow_to_cidr("inet-out", INTERNET)

    @pulumi.runtime.test
    def test_allow_from_cidr_protocol_is_tcp(self):
        """allow_from_cidr uses TCP protocol."""
        _, src, _ = self._make_pair()
        rule = src.allow_from_cidr("ssh-in", SSH, "203.0.113.0/24")

        def check(protocol):
            self.assertEqual(protocol, TCP)

        return rule.protocol.apply(check)

    @pulumi.runtime.test
    def test_allow_to_cidr_creates_egress_rule(self):
        """allow_to_cidr creates an EGRESS all-protocol rule."""
        _, src, _ = self._make_pair()
        rule = src.allow_to_cidr("inet-out", INTERNET)

        def check(args):
            direction, protocol = args
            self.assertEqual(direction, "EGRESS")
            self.assertEqual(protocol, ALL)

        return pulumi.Output.all(rule.direction, rule.protocol).apply(check)

    @pulumi.runtime.test
    def test_allow_from_nsg_uses_network_security_group_source_type(self):
        """allow_from_nsg sets source_type=NETWORK_SECURITY_GROUP."""
        _, src, tgt = self._make_pair()
        rule = tgt.allow_from_nsg("app-in", src, HTTP)

        def check(source_type):
            self.assertEqual(source_type, "NETWORK_SECURITY_GROUP")

        return rule.source_type.apply(check)

    @pulumi.runtime.test
    def test_allow_to_nsg_uses_network_security_group_destination_type(self):
        """allow_to_nsg sets destination_type=NETWORK_SECURITY_GROUP."""
        _, src, tgt = self._make_pair()
        rule = src.allow_to_nsg("app-out", tgt, HTTP)

        def check(destination_type):
            self.assertEqual(destination_type, "NETWORK_SECURITY_GROUP")

        return rule.destination_type.apply(check)

    @pulumi.runtime.test
    def test_allow_to_services_uses_service_cidr_block(self):
        """allow_to_services sets destination_type=SERVICE_CIDR_BLOCK and protocol=ALL."""
        _, src, _ = self._make_pair()
        rule = src.allow_to_services("svc-out")

        def check(args):
            destination_type, protocol = args
            self.assertEqual(destination_type, "SERVICE_CIDR_BLOCK")
            self.assertEqual(protocol, ALL)

        return pulumi.Output.all(rule.destination_type, rule.protocol).apply(check)

    @pulumi.runtime.test
    def test_allow_icmp_from_cidr_uses_icmp_protocol(self):
        """allow_icmp_from_cidr creates an INGRESS ICMP rule."""
        _, src, _ = self._make_pair()
        rule = src.allow_icmp_from_cidr("icmp-in", INTERNET, icmp_type=3, code=4)

        def check(args):
            direction, protocol = args
            self.assertEqual(direction, "INGRESS")
            self.assertEqual(protocol, ICMP)

        return pulumi.Output.all(rule.direction, rule.protocol).apply(check)

    @pulumi.runtime.test
    def test_allow_udp_from_cidr_uses_udp_protocol(self):
        """allow_udp_from_cidr creates an INGRESS UDP rule."""
        _, src, _ = self._make_pair()
        rule = src.allow_udp_from_cidr("dns-in", 53, "10.0.0.0/16")

        def check(args):
            direction, protocol, source_type = args
            self.assertEqual(direction, "INGRESS")
            self.assertEqual(protocol, "17")
            self.assertEqual(source_type, "CIDR_BLOCK")

        return pulumi.Output.all(rule.direction, rule.protocol, rule.source_type).apply(check)

    @pulumi.runtime.test
    def test_allow_udp_to_cidr_uses_udp_protocol(self):
        """allow_udp_to_cidr creates an EGRESS UDP rule."""
        _, src, _ = self._make_pair()
        rule = src.allow_udp_to_cidr("dns-out", 53, "10.0.0.0/16")

        def check(args):
            direction, protocol, destination_type = args
            self.assertEqual(direction, "EGRESS")
            self.assertEqual(protocol, "17")
            self.assertEqual(destination_type, "CIDR_BLOCK")

        return pulumi.Output.all(rule.direction, rule.protocol, rule.destination_type).apply(check)

    @pulumi.runtime.test
    def test_raw_add_rule_is_not_public_api(self):
        """Nsg does not expose raw OCI security rule creation publicly."""
        self.assertFalse(hasattr(Nsg, "add_rule"))

    @pulumi.runtime.test
    def test_allow_from_cidr_stateless_is_false(self):
        """allow_from_cidr produces a stateful (stateless=False) rule."""
        _, src, _ = self._make_pair()
        rule = src.allow_from_cidr("custom", 8080, INTERNET)

        def check(stateless):
            self.assertFalse(stateless)

        return rule.stateless.apply(check)


class TestNsgServes(unittest.TestCase):
    """Tests for Nsg.serves() bilateral rule generation."""

    def _make_vcn(self) -> Vcn:
        return Vcn(name="serves-vcn", compartment_id=COMP_ID)

    def test_serves_registers_cross_subnet_sl_rules_for_different_tiers(self):
        """serves() between different-tier roles registers security list fingerprints."""
        vcn = self._make_vcn()
        lb = Nsg("lb", role=INTERNET_EDGE, ports=[HTTP, HTTPS], vcn=vcn, compartment_id=COMP_ID)
        app = Nsg("app", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        before = frozenset(vcn._applied_ambient_rule_fingerprints)
        lb.serves(app, port=HTTP)
        after = frozenset(vcn._applied_ambient_rule_fingerprints)

        new_fps = after - before
        cross_subnet = {fp for fp in new_fps if "to-" in fp or "from-" in fp}
        self.assertGreater(len(cross_subnet), 0, "Expected cross-subnet SL fingerprints")

    def test_serves_same_tier_skips_sl_rules(self):
        """serves() between same-tier NSGs adds no cross-subnet security list rules."""
        vcn = self._make_vcn()
        app1 = Nsg("app1", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)
        app2 = Nsg("app2", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        before = frozenset(vcn._applied_ambient_rule_fingerprints)
        app1.serves(app2, port=8080)
        after = frozenset(vcn._applied_ambient_rule_fingerprints)

        cross_subnet = {fp for fp in (after - before) if "to-" in fp or "from-" in fp}
        self.assertEqual(len(cross_subnet), 0)

    def test_serves_with_ssh_false_omits_ssh_channel(self):
        """serves(with_ssh=False) does not add SSH management rules."""
        vcn = self._make_vcn()
        lb = Nsg("lb2", role=INTERNET_EDGE, ports=[HTTPS], vcn=vcn, compartment_id=COMP_ID)
        app = Nsg("app3", role=APP_SERVER, vcn=vcn, compartment_id=COMP_ID)

        before = frozenset(vcn._applied_ambient_rule_fingerprints)
        lb.serves(app, port=HTTPS, with_ssh=False)
        after = frozenset(vcn._applied_ambient_rule_fingerprints)

        new_fps = after - before
        ssh_fps = {fp for fp in new_fps if "-22-" in fp or "tcp-22" in fp}
        self.assertEqual(len(ssh_fps), 0, "No SSH SL fingerprints expected when with_ssh=False")

    def test_serves_no_role_skips_sl_rules(self):
        """serves() without roles on either NSG adds no security list rules."""
        vcn = self._make_vcn()
        a = Nsg("bare-a", vcn=vcn, compartment_id=COMP_ID)
        b = Nsg("bare-b", vcn=vcn, compartment_id=COMP_ID)

        before = frozenset(vcn._applied_ambient_rule_fingerprints)
        a.serves(b, port=8080)
        after = frozenset(vcn._applied_ambient_rule_fingerprints)

        self.assertEqual(before, after, "No SL fingerprints expected when NSGs have no role")
