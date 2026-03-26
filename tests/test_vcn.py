"""Unit tests for VCN block."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.core.abstractions.network import EgressRule, IngressRule, SecurityRules
from cloudspells.providers.oci.network import Vcn, VcnRef


class TestVcn(unittest.TestCase):
    """Test cases for VCN block."""

    @pulumi.runtime.test
    def test_vcn_creates_base_resources(self):
        """Test that VCN creates core networking resources."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        def check_vcn(args):
            vcn_id, igw_id, natgw_id, svcgw_id = args
            self.assertIsNotNone(vcn_id, "VCN must be created")
            self.assertIsNotNone(igw_id, "Internet Gateway must be created")
            self.assertIsNotNone(natgw_id, "NAT Gateway must be created")
            self.assertIsNotNone(svcgw_id, "Service Gateway must be created")

        return pulumi.Output.all(
            vcn.vcn.id,
            vcn.internet_gateway.id,
            vcn.nat_gateway.id,
            vcn.service_gateway.id,
        ).apply(check_vcn)

    @pulumi.runtime.test
    def test_vcn_creates_route_tables(self):
        """Test that VCN creates public, private, secure, and management route tables."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        def check_route_tables(args):
            public_rt_id, private_rt_id, secure_rt_id, management_rt_id = args
            self.assertIsNotNone(public_rt_id, "Public route table must be created")
            self.assertIsNotNone(private_rt_id, "Private route table must be created")
            self.assertIsNotNone(secure_rt_id, "Secure route table must be created")
            self.assertIsNotNone(management_rt_id, "Management route table must be created")

        return pulumi.Output.all(
            vcn.public_route_table.id,
            vcn.private_route_table.id,
            vcn.secure_route_table.id,
            vcn.management_route_table.id,
        ).apply(check_route_tables)

    @pulumi.runtime.test
    def test_vcn_subnets_not_created_before_finalize(self):
        """Test that subnets are None before finalize_network() is called."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        # Before finalization, subnets should be None
        self.assertIsNone(vcn.public_subnet, "Public subnet should be None before finalization")
        self.assertIsNone(vcn.private_subnet, "Private subnet should be None before finalization")
        self.assertIsNone(vcn.secure_subnet, "Secure subnet should be None before finalization")
        self.assertIsNone(vcn.management_subnet, "Management subnet should be None before finalization")

    @pulumi.runtime.test
    def test_vcn_subnets_created_after_finalize(self):
        """Test that subnets are created after finalize_network() is called."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )
        vcn.finalize_network()

        # Assert subnets exist before accessing
        assert vcn.public_subnet is not None
        assert vcn.private_subnet is not None
        assert vcn.secure_subnet is not None
        assert vcn.management_subnet is not None

        def check_subnets(args):
            public_id, private_id, secure_id, management_id = args
            self.assertIsNotNone(public_id, "Public subnet must be created after finalization")
            self.assertIsNotNone(private_id, "Private subnet must be created after finalization")
            self.assertIsNotNone(secure_id, "Secure subnet must be created after finalization")
            self.assertIsNotNone(management_id, "Management subnet must be created after finalization")

        return pulumi.Output.all(
            vcn.public_subnet.id,
            vcn.private_subnet.id,
            vcn.secure_subnet.id,
            vcn.management_subnet.id,
        ).apply(check_subnets)

    @pulumi.runtime.test
    def test_vcn_security_lists_created_after_finalize(self):
        """Test that security lists are created after finalize_network()."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )
        vcn.finalize_network()

        # Assert security lists exist before accessing
        assert vcn.public_security_list is not None
        assert vcn.private_security_list is not None
        assert vcn.secure_security_list is not None
        assert vcn.management_security_list is not None

        def check_security_lists(args):
            public_sl_id, private_sl_id, secure_sl_id, management_sl_id = args
            self.assertIsNotNone(public_sl_id, "Public security list must be created")
            self.assertIsNotNone(private_sl_id, "Private security list must be created")
            self.assertIsNotNone(secure_sl_id, "Secure security list must be created")
            self.assertIsNotNone(management_sl_id, "Management security list must be created")

        return pulumi.Output.all(
            vcn.public_security_list.id,
            vcn.private_security_list.id,
            vcn.secure_security_list.id,
            vcn.management_security_list.id,
        ).apply(check_security_lists)

    def test_vcn_cidr_calculation(self):
        """Test that subnet CIDRs are correctly calculated."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            cidr_block="10.0.0.0/16",
        )

        public_cidr = vcn.get_public_subnet_cidr()
        private_cidr = vcn.get_private_subnet_cidr()
        secure_cidr = vcn.get_secure_subnet_cidr()
        management_cidr = vcn.get_management_subnet_cidr()

        # /16 proportional split: private=50% /17, secure=25% /18, public=12.5% /19
        self.assertEqual(private_cidr, "10.0.0.0/17", "Private subnet should be /17 (50% of VCN)")
        self.assertEqual(secure_cidr, "10.0.128.0/18", "Secure subnet should be /18 (25% of VCN)")
        self.assertEqual(public_cidr, "10.0.192.0/19", "Public subnet should be /19 (12.5% of VCN)")
        self.assertEqual(management_cidr, "10.0.224.0/19", "Management subnet should be /19 (12.5% of VCN)")

    def test_vcn_custom_cidr(self):
        """Test VCN with custom CIDR block."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            cidr_block="192.168.0.0/16",
        )

        public_cidr = vcn.get_public_subnet_cidr()
        private_cidr = vcn.get_private_subnet_cidr()
        secure_cidr = vcn.get_secure_subnet_cidr()
        management_cidr = vcn.get_management_subnet_cidr()

        self.assertEqual(private_cidr, "192.168.0.0/17")
        self.assertEqual(secure_cidr, "192.168.128.0/18")
        self.assertEqual(public_cidr, "192.168.192.0/19")
        self.assertEqual(management_cidr, "192.168.224.0/19")

    def test_vcn_finalize_idempotent(self):
        """Test that finalize_network() can be called multiple times safely."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )

        # Call finalize twice - should not raise
        vcn.finalize_network()
        vcn.finalize_network()

        # Should still have valid subnets
        self.assertIsNotNone(vcn.public_subnet)
        self.assertIsNotNone(vcn.private_subnet)
        self.assertIsNotNone(vcn.secure_subnet)
        self.assertIsNotNone(vcn.management_subnet)

    def test_flow_logs_none_by_default(self):
        """Test that flow_logs is None when flow_logs=False (default)."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )
        vcn.finalize_network()
        self.assertIsNone(vcn.flow_logs)

    @pulumi.runtime.test
    def test_flow_logs_created_when_enabled(self):
        """Test that VcnFlowLogs is created automatically when flow_logs=True."""
        from cloudspells.providers.oci.network_logging import VcnFlowLogs

        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            flow_logs=True,
        )
        vcn.finalize_network()

        self.assertIsNotNone(vcn.flow_logs, "flow_logs attribute must be set after finalize_network")
        self.assertIsInstance(vcn.flow_logs, VcnFlowLogs)

        def check_log_group(log_group_id):
            self.assertIsNotNone(log_group_id, "Log group must be created")

        assert vcn.flow_logs is not None
        return vcn.flow_logs.log_group_id.apply(check_log_group)

    def test_flow_logs_not_created_before_finalize(self):
        """Test that flow_logs remains None before finalize_network() is called."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            flow_logs=True,
        )
        self.assertIsNone(vcn.flow_logs, "flow_logs must be None before finalize_network")

    # ------------------------------------------------------------------
    # Baseline gateway egress tests
    # ------------------------------------------------------------------

    @pulumi.runtime.test
    def test_baseline_private_egress_enables_nat(self):
        """Private security list must have an all-protocol egress rule to 0.0.0.0/0.

        Without this rule the security list drops packets before they reach
        the NAT Gateway, even though the route table is correctly wired.
        """
        vcn = Vcn(name="test-vcn", compartment_id="ocid1.compartment.test")
        vcn.finalize_network()

        def check(rules):
            has_nat = any(r.get("destination") == "0.0.0.0/0" and r.get("protocol") == "all" for r in (rules or []))
            self.assertTrue(has_nat, "Private egress must have all-protocol rule to 0.0.0.0/0 for NAT gateway")

        return vcn.private_security_list.egress_security_rules.apply(check)

    @pulumi.runtime.test
    def test_baseline_service_gw_egress_on_internal_tiers(self):
        """Private, secure, and management egress must have a SERVICE_CIDR_BLOCK rule.

        Required so instances on internal tiers can reach OCI services
        (Object Storage, Monitoring, Logging, etc.) via the Service Gateway.
        """
        vcn = Vcn(name="test-vcn", compartment_id="ocid1.compartment.test")
        vcn.finalize_network()

        def check(args):
            priv, sec, mgmt = args
            for tier, rules in (("private", priv), ("secure", sec), ("management", mgmt)):
                has_svc = any(r.get("destination_type") == "SERVICE_CIDR_BLOCK" for r in (rules or []))
                self.assertTrue(has_svc, f"{tier} egress must have SERVICE_CIDR_BLOCK rule for Service Gateway")

        return pulumi.Output.all(
            vcn.private_security_list.egress_security_rules,
            vcn.secure_security_list.egress_security_rules,
            vcn.management_security_list.egress_security_rules,
        ).apply(check)

    @pulumi.runtime.test
    def test_baseline_public_has_no_nat_or_svc_egress(self):
        """Public security list must NOT have NAT or SERVICE_CIDR_BLOCK egress rules.

        Public subnet routes via the Internet Gateway only; adding these
        rules would be misleading since the route table does not point to
        NAT or Service Gateway for that tier.
        """
        vcn = Vcn(name="test-vcn", compartment_id="ocid1.compartment.test")
        vcn.finalize_network()

        def check(rules):
            has_svc = any(r.get("destination_type") == "SERVICE_CIDR_BLOCK" for r in (rules or []))
            self.assertFalse(has_svc, "Public egress must not have SERVICE_CIDR_BLOCK rule")

        return vcn.public_security_list.egress_security_rules.apply(check)

    # ------------------------------------------------------------------
    # DRG tests
    # ------------------------------------------------------------------

    def test_drg_not_created_by_default(self):
        """Test that DRG is None when drg=False (default)."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
        )
        self.assertIsNone(vcn.drg, "drg must be None when drg=False")
        self.assertIsNone(vcn.drg_attachment, "drg_attachment must be None when drg=False")

    @pulumi.runtime.test
    def test_drg_created_when_enabled(self):
        """Test that DRG and its VCN attachment are created when drg=True."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            drg=True,
        )

        self.assertIsNotNone(vcn.drg, "drg resource must be set when drg=True")
        self.assertIsNotNone(vcn.drg_attachment, "drg_attachment must be set when drg=True")

        def check_drg(args):
            drg_id, attach_id = args
            self.assertIsNotNone(drg_id, "DRG must have an ID")
            self.assertIsNotNone(attach_id, "DRG attachment must have an ID")

        assert vcn.drg is not None
        assert vcn.drg_attachment is not None
        return pulumi.Output.all(
            vcn.drg.id,
            vcn.drg_attachment.id,
        ).apply(check_drg)

    @pulumi.runtime.test
    def test_drg_on_premise_routes_injected(self):
        """Test that on-premise CIDRs are added to private, secure, and management route tables."""
        on_premise_cidrs = ["10.10.0.0/16", "192.168.1.0/24"]
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            drg=True,
            on_premise_cidrs=on_premise_cidrs,
        )

        def check_private_routes(route_rules):
            destinations = [r.get("destination") for r in route_rules]
            for cidr in on_premise_cidrs:
                self.assertIn(cidr, destinations, f"Private route table must contain DRG route for {cidr}")

        def check_secure_routes(route_rules):
            destinations = [r.get("destination") for r in route_rules]
            for cidr in on_premise_cidrs:
                self.assertIn(cidr, destinations, f"Secure route table must contain DRG route for {cidr}")

        def check_management_routes(route_rules):
            destinations = [r.get("destination") for r in route_rules]
            for cidr in on_premise_cidrs:
                self.assertIn(cidr, destinations, f"Management route table must contain DRG route for {cidr}")

        def check_public_routes(route_rules):
            destinations = [r.get("destination") for r in route_rules]
            for cidr in on_premise_cidrs:
                self.assertNotIn(cidr, destinations, f"Public route table must NOT contain DRG route for {cidr}")

        private_check = vcn.private_route_table.route_rules.apply(check_private_routes)
        secure_check = vcn.secure_route_table.route_rules.apply(check_secure_routes)
        management_check = vcn.management_route_table.route_rules.apply(check_management_routes)
        public_check = vcn.public_route_table.route_rules.apply(check_public_routes)

        return pulumi.Output.all(private_check, secure_check, management_check, public_check)

    def test_drg_on_premise_cidrs_ignored_when_drg_disabled(self):
        """Test that on_premise_cidrs has no effect when drg=False."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            drg=False,
            on_premise_cidrs=["10.10.0.0/16"],
        )
        self.assertIsNone(vcn.drg, "drg must be None when drg=False even with on_premise_cidrs set")

    # ------------------------------------------------------------------
    # add_security_list_rules / add_security_rules
    # ------------------------------------------------------------------

    def test_add_security_list_rules_after_finalize_raises(self):
        """add_security_list_rules() raises RuntimeError when called after finalize_network."""
        vcn = Vcn(name="test-vcn", compartment_id="ocid1.compartment.test")
        vcn.finalize_network()
        with self.assertRaises(RuntimeError):
            vcn.add_security_list_rules(public_ingress=[])

    @pulumi.runtime.test
    def test_add_security_rules_translates_ingress_and_egress(self):
        """add_security_rules() populates public/private security lists via cloud-neutral rules."""
        vcn = Vcn(name="test-vcn", compartment_id="ocid1.compartment.test")
        rules = SecurityRules(
            public_ingress=[IngressRule(protocol="tcp", source="internet", port_min=443, port_max=443)],
            private_egress=[EgressRule(protocol="tcp", destination="cloud-services", port_min=443, port_max=443)],
        )
        vcn.add_security_rules(rules)
        vcn.finalize_network()

        def check_public_ingress(ingress_rules):
            cidrs = [r.get("source") for r in (ingress_rules or [])]
            self.assertIn("0.0.0.0/0", cidrs, "internet source must translate to 0.0.0.0/0")

        def check_private_egress(egress_rules):
            types = [r.get("destination_type") for r in (egress_rules or [])]
            self.assertIn("SERVICE_CIDR_BLOCK", types, "cloud-services destination must have SERVICE_CIDR_BLOCK type")

        public_check = vcn.public_security_list.ingress_security_rules.apply(check_public_ingress)
        private_check = vcn.private_security_list.egress_security_rules.apply(check_private_egress)
        return pulumi.Output.all(public_check, private_check)

    @pulumi.runtime.test
    def test_add_security_rules_management_tier(self):
        """add_security_rules() correctly routes management_ingress rules."""
        vcn = Vcn(name="test-vcn", compartment_id="ocid1.compartment.test")
        rules = SecurityRules(
            management_ingress=[IngressRule(protocol="tcp", source="10.0.0.0/8", port_min=22, port_max=22)],
        )
        vcn.add_security_rules(rules)
        vcn.finalize_network()

        def check(ingress_rules):
            sources = [r.get("source") for r in (ingress_rules or [])]
            self.assertIn("10.0.0.0/8", sources)

        return vcn.management_security_list.ingress_security_rules.apply(check)


class TestVcnRef(unittest.TestCase):
    """Test cases for VcnRef — cross-stack VCN reference."""

    def _make_ref(self, **kwargs):
        defaults = dict(
            vcn_id="ocid1.vcn.oc1.phx.test",
            public_subnet_id="ocid1.subnet.public.test",
            private_subnet_id="ocid1.subnet.private.test",
            public_subnet_cidr="10.0.192.0/19",
            private_subnet_cidr="10.0.0.0/17",
            cidr_block="10.0.0.0/16",
            secure_subnet_id="ocid1.subnet.secure.test",
            secure_subnet_cidr="10.0.128.0/18",
            management_subnet_id="ocid1.subnet.mgmt.test",
            management_subnet_cidr="10.0.224.0/19",
        )
        defaults.update(kwargs)
        return VcnRef(**defaults)

    def test_vcnref_requires_cidr_block(self):
        """VcnRef raises ValueError when cidr_block is None."""
        with self.assertRaises(ValueError):
            VcnRef(
                vcn_id="ocid1.vcn.test",
                public_subnet_id="ocid1.subnet.pub.test",
                private_subnet_id="ocid1.subnet.priv.test",
                public_subnet_cidr="10.0.0.0/19",
                private_subnet_cidr="10.0.0.0/17",
                cidr_block=None,
            )

    def test_vcnref_cidr_accessors(self):
        """VcnRef CIDR accessors return the values passed at construction."""
        ref = self._make_ref()
        self.assertEqual(ref.get_public_subnet_cidr(), "10.0.192.0/19")
        self.assertEqual(ref.get_private_subnet_cidr(), "10.0.0.0/17")
        self.assertEqual(ref.get_secure_subnet_cidr(), "10.0.128.0/18")
        self.assertEqual(ref.get_management_subnet_cidr(), "10.0.224.0/19")

    def test_vcnref_optional_subnets_none_by_default(self):
        """VcnRef has None secure/management subnets when not provided."""
        ref = VcnRef(
            vcn_id="ocid1.vcn.test",
            public_subnet_id="ocid1.subnet.pub.test",
            private_subnet_id="ocid1.subnet.priv.test",
            public_subnet_cidr="10.0.0.0/19",
            private_subnet_cidr="10.0.0.0/17",
            cidr_block="10.0.0.0/16",
        )
        self.assertIsNone(ref.secure_subnet)
        self.assertIsNone(ref.management_subnet)
        with self.assertRaises(ValueError):
            ref.get_secure_subnet_cidr()
        with self.assertRaises(ValueError):
            ref.get_management_subnet_cidr()

    def test_vcnref_drg_id_none_by_default(self):
        """VcnRef.drg_id is None when not provided."""
        ref = self._make_ref()
        self.assertIsNone(ref.drg_id)

    def test_vcnref_drg_id_set(self):
        """VcnRef stores drg_id when provided."""
        ref = self._make_ref(drg_id="ocid1.drg.test")
        self.assertIsNotNone(ref.drg_id)

    def test_vcnref_add_security_list_rules_nonempty_raises(self):
        """VcnRef.add_security_list_rules() raises RuntimeError for non-empty rule lists."""
        import pulumi_oci as oci

        ref = self._make_ref()
        dummy_rule = oci.core.SecurityListIngressSecurityRuleArgs(
            protocol="6", source="0.0.0.0/0", source_type="CIDR_BLOCK"
        )
        with self.assertRaises(RuntimeError):
            ref.add_security_list_rules(public_ingress=[dummy_rule])

    def test_vcnref_add_security_list_rules_all_none_is_noop(self):
        """VcnRef.add_security_list_rules() accepts all-None without raising."""
        ref = self._make_ref()
        ref.add_security_list_rules()  # must not raise

    def test_vcnref_finalize_network_is_noop(self):
        """VcnRef.finalize_network() is a no-op and does not raise."""
        ref = self._make_ref()
        ref.finalize_network()  # must not raise

    def test_vcnref_security_list_stubs_present(self):
        """VcnRef exposes security list stubs when IDs are provided."""
        ref = self._make_ref(
            public_security_list_id="ocid1.sl.pub.test",
            private_security_list_id="ocid1.sl.priv.test",
        )
        self.assertIsNotNone(ref.public_security_list)
        self.assertIsNotNone(ref.private_security_list)

    def test_vcnref_security_list_stubs_none_when_not_provided(self):
        """VcnRef security list stubs are None when IDs are omitted."""
        ref = self._make_ref()
        self.assertIsNone(ref.public_security_list)
        self.assertIsNone(ref.private_security_list)


if __name__ == "__main__":
    unittest.main()
