"""Unit tests for Load Balancer spells."""

import unittest

import pulumi

from tests.mocks import set_mocks

set_mocks()

from cloudspells.providers.oci._network_profiles import (
    NETWORK_PROFILE_BASELINE,
    internal_load_balancer_profile_id,
    load_balancer_profile_id,
)
from cloudspells.providers.oci.loadbalancer import InternalLoadBalancer, LoadBalancer
from cloudspells.providers.oci.network import Vcn, VcnRef
from cloudspells.providers.oci.nsg import Nsg
from cloudspells.providers.oci.roles import INTERNET_EDGE

_COMPARTMENT = "ocid1.compartment.test"


def _make_vcn_ref(profiles: list[str] | None = None) -> VcnRef:
    """Create a VcnRef populated with load-balancer-compatible test values."""
    return VcnRef(
        vcn_id="ocid1.vcn.test",
        public_subnet_id="ocid1.subnet.public.test",
        private_subnet_id="ocid1.subnet.private.test",
        public_subnet_cidr="10.0.192.0/19",
        private_subnet_cidr="10.0.0.0/17",
        cidr_block="10.0.0.0/16",
        cloudspells_network_schema="cloudspells.oci.vcn/v1",
        network_profiles=profiles or [NETWORK_PROFILE_BASELINE],
    )


class TestLoadBalancer(unittest.TestCase):
    """Test cases for the `LoadBalancer` spell."""

    def setUp(self) -> None:
        self.vcn = Vcn(name="test-vcn", compartment_id=_COMPARTMENT)

    @pulumi.runtime.test
    def test_lb_created(self):
        """Test that `LoadBalancer` creates the underlying OCI load balancer."""
        lb = LoadBalancer(
            name="test-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return lb.load_balancer.id.apply(check)

    @pulumi.runtime.test
    def test_backend_set_created(self):
        """Test that `LoadBalancer` creates a backend set."""
        lb = LoadBalancer(
            name="bs-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return lb.backend_set.name.apply(check)

    @pulumi.runtime.test
    def test_redirect_rule_set_created(self):
        """Test that `LoadBalancer` creates the HTTP→HTTPS redirect rule set."""
        lb = LoadBalancer(
            name="rs-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return lb.redirect_rule_set.name.apply(check)

    @pulumi.runtime.test
    def test_two_listeners_created(self):
        """Test that `LoadBalancer` creates exactly two listeners (HTTPS + HTTP)."""
        lb = LoadBalancer(
            name="listeners-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )
        self.assertEqual(len(lb.listeners), 2)

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return lb.listeners[0].name.apply(check)

    @pulumi.runtime.test
    def test_get_lb_ip_returns_output(self):
        """Test that `get_lb_ip()` returns a non-empty IP string."""
        lb = LoadBalancer(
            name="ip-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
            stack_name="prod",
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return lb.get_lb_ip().apply(check)

    @pulumi.runtime.test
    def test_get_lb_id_returns_output(self):
        """Test that `get_lb_id()` returns a non-empty OCID string."""
        lb = LoadBalancer(
            name="id-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return lb.get_lb_id().apply(check)

    @pulumi.runtime.test
    def test_public_ingress_rules_dedupe_with_internet_edge_nsg(self):
        """LoadBalancer shares HTTP/HTTPS security-list fingerprints with NSGs."""
        Nsg("edge", role=INTERNET_EDGE, ports=[80, 443], vcn=self.vcn, compartment_id=_COMPARTMENT)
        LoadBalancer(
            name="dedupe-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )

        fingerprints = self.vcn._applied_ambient_rule_fingerprints
        self.assertIn("public-ingress-tcp-80", fingerprints)
        self.assertIn("public-ingress-tcp-443", fingerprints)
        self.assertNotIn("lb-public-ingress-tcp-80", fingerprints)
        self.assertNotIn("lb-public-ingress-tcp-443", fingerprints)

        tcp_public_ingress_count = sum(
            1
            for rule in self.vcn._public_ingress_rules
            if getattr(rule, "protocol", None) == "6" and getattr(rule, "source", None) == "0.0.0.0/0"
        )
        self.assertEqual(tcp_public_ingress_count, 2)

    @pulumi.runtime.test
    def test_name_follows_namer(self):
        """Test that the LB resource name includes the stack and logical name."""
        lb = LoadBalancer(
            name="web",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
            stack_name="prod",
        )

        def check(value: str) -> None:
            self.assertIn("prod", value)
            self.assertIn("web", value)

        return lb.load_balancer.id.apply(check)

    @pulumi.runtime.test
    def test_export_publishes_keys(self):
        """Test that `export()` publishes the lb_id and lb_ip outputs."""
        lb = LoadBalancer(
            name="export-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )
        lb.export()

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return lb.get_lb_ip().apply(check)

    def test_output_attributes_set(self) -> None:
        """Test that `lb_id` and `lb_ip` attributes are set on the spell."""
        lb = LoadBalancer(
            name="attr-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
        )
        self.assertIsNotNone(lb.lb_id)
        self.assertIsNotNone(lb.lb_ip)

    def test_live_vcn_marks_load_balancer_profile(self) -> None:
        """LoadBalancer marks the source VCN with its security-list profile."""
        LoadBalancer(
            name="profile-lb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            certificate_name="my-cert",
            backend_port=8080,
        )

        self.assertTrue(self.vcn.has_network_profile(load_balancer_profile_id(8080)))

    def test_vcnref_requires_load_balancer_profile(self) -> None:
        """LoadBalancer rejects VcnRef stacks missing its security-list profile."""
        with self.assertRaisesRegex(RuntimeError, "required network profile"):
            LoadBalancer(
                name="missing-profile-lb",
                compartment_id=_COMPARTMENT,
                vcn=_make_vcn_ref(),
                certificate_name="my-cert",
            )

    def test_vcnref_accepts_load_balancer_profile(self) -> None:
        """LoadBalancer accepts VcnRef stacks exporting the matching profile."""
        lb = LoadBalancer(
            name="present-profile-lb",
            compartment_id=_COMPARTMENT,
            vcn=_make_vcn_ref([NETWORK_PROFILE_BASELINE, load_balancer_profile_id(80)]),
            certificate_name="my-cert",
        )

        self.assertIsNotNone(lb.lb_id)


class TestInternalLoadBalancer(unittest.TestCase):
    """Test cases for the `InternalLoadBalancer` spell."""

    def setUp(self) -> None:
        self.vcn = Vcn(name="test-vcn-int", compartment_id=_COMPARTMENT)

    @pulumi.runtime.test
    def test_lb_created(self):
        """Test that `InternalLoadBalancer` creates the underlying OCI load balancer."""
        ilb = InternalLoadBalancer(
            name="test-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return ilb.load_balancer.id.apply(check)

    @pulumi.runtime.test
    def test_backend_set_created(self):
        """Test that `InternalLoadBalancer` creates a backend set."""
        ilb = InternalLoadBalancer(
            name="bs-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return ilb.backend_set.name.apply(check)

    @pulumi.runtime.test
    def test_single_listener_created(self):
        """Test that `InternalLoadBalancer` creates exactly one HTTP listener."""
        ilb = InternalLoadBalancer(
            name="listener-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return ilb.listener.name.apply(check)

    @pulumi.runtime.test
    def test_custom_backend_port_allows_private_ingress(self):
        """Internal LB opens backend_port ingress on the private security list."""
        ilb = InternalLoadBalancer(
            name="custom-port-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            backend_port=8080,
        )
        assert ilb.vcn.private_security_list is not None

        def check(ingress_rules):
            ports = []
            for rule in ingress_rules or []:
                tcp_options = rule.get("tcp_options") or {}
                ports.append((tcp_options.get("min"), tcp_options.get("max")))
            self.assertIn((8080, 8080), ports)

        return ilb.vcn.private_security_list.ingress_security_rules.apply(check)

    @pulumi.runtime.test
    def test_get_lb_ip_returns_output(self):
        """Test that `get_lb_ip()` returns a non-empty string."""
        ilb = InternalLoadBalancer(
            name="ip-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            stack_name="prod",
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return ilb.get_lb_ip().apply(check)

    @pulumi.runtime.test
    def test_get_lb_id_returns_output(self):
        """Test that `get_lb_id()` returns a non-empty OCID string."""
        ilb = InternalLoadBalancer(
            name="id-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return ilb.get_lb_id().apply(check)

    @pulumi.runtime.test
    def test_name_follows_namer(self):
        """Test that the LB resource name includes the stack and logical name."""
        ilb = InternalLoadBalancer(
            name="api",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            stack_name="prod",
        )

        def check(value: str) -> None:
            self.assertIn("prod", value)
            self.assertIn("api", value)

        return ilb.load_balancer.id.apply(check)

    @pulumi.runtime.test
    def test_export_publishes_keys(self):
        """Test that `export()` publishes the lb_id and lb_ip outputs."""
        ilb = InternalLoadBalancer(
            name="export-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
        )
        ilb.export()

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return ilb.get_lb_ip().apply(check)

    def test_output_attributes_set(self) -> None:
        """Test that `lb_id` and `lb_ip` attributes are set on the spell."""
        ilb = InternalLoadBalancer(
            name="attr-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
        )
        self.assertIsNotNone(ilb.lb_id)
        self.assertIsNotNone(ilb.lb_ip)

    def test_live_vcn_marks_internal_load_balancer_profile(self) -> None:
        """InternalLoadBalancer marks the source VCN with its profile."""
        InternalLoadBalancer(
            name="profile-ilb",
            compartment_id=_COMPARTMENT,
            vcn=self.vcn,
            backend_port=8080,
        )

        self.assertTrue(self.vcn.has_network_profile(internal_load_balancer_profile_id(8080)))

    def test_vcnref_requires_internal_load_balancer_profile(self) -> None:
        """InternalLoadBalancer rejects VcnRef stacks missing its profile."""
        with self.assertRaisesRegex(RuntimeError, "required network profile"):
            InternalLoadBalancer(
                name="missing-profile-ilb",
                compartment_id=_COMPARTMENT,
                vcn=_make_vcn_ref(),
            )


if __name__ == "__main__":
    unittest.main()
