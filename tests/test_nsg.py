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
    icmp_opts,
    tcp_port,
    udp_port,
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
    def test_add_rule_stateless_is_false(self):
        """add_rule always produces a stateful (stateless=False) rule."""
        _, src, _ = self._make_pair()
        rule = src.add_rule(
            "custom",
            direction="INGRESS",
            protocol=TCP,
            source=INTERNET,
            source_type="CIDR_BLOCK",
            tcp_options=tcp_port(8080),
        )

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


class TestPortHelpers(unittest.TestCase):
    """Tests for tcp_port, udp_port, icmp_opts factory functions."""

    def test_tcp_port_sets_min_max(self):
        """tcp_port(n) returns args with min=max=n."""
        opts = tcp_port(443)
        self.assertEqual(opts.destination_port_range.min, 443)  # type: ignore[union-attr]  # Args object at construction time
        self.assertEqual(opts.destination_port_range.max, 443)  # type: ignore[union-attr]

    def test_udp_port_sets_min_max(self):
        """udp_port(n) returns args with min=max=n."""
        opts = udp_port(53)
        self.assertEqual(opts.destination_port_range.min, 53)  # type: ignore[union-attr]  # Args object at construction time — not a pulumi.Output
        self.assertEqual(opts.destination_port_range.max, 53)  # type: ignore[union-attr]  # Args object at construction time — not a pulumi.Output

    def test_icmp_opts_type_only(self):
        """icmp_opts(type) returns args with type set and code=-1."""
        opts = icmp_opts(3)
        self.assertEqual(opts.type, 3)
        self.assertEqual(opts.code, -1)

    def test_icmp_opts_type_and_code(self):
        """icmp_opts(type, code) returns args with both set."""
        opts = icmp_opts(3, 4)
        self.assertEqual(opts.type, 3)
        self.assertEqual(opts.code, 4)
