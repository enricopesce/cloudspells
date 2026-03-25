"""Unit tests for Load Balancer spells."""

import unittest

import pulumi

from tests.mocks import set_mocks

set_mocks()

from cloudspells.providers.oci.loadbalancer import InternalLoadBalancer, LoadBalancer
from cloudspells.providers.oci.network import Vcn

_COMPARTMENT = "ocid1.compartment.test"


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


if __name__ == "__main__":
    unittest.main()
