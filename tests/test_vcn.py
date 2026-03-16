"""Unit tests for VCN block."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.blocks.vcn.network import Vcn


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

        return vcn.flow_logs.log_group_id.apply(check_log_group)

    def test_flow_logs_not_created_before_finalize(self):
        """Test that flow_logs remains None before finalize_network() is called."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            flow_logs=True,
        )
        self.assertIsNone(vcn.flow_logs, "flow_logs must be None before finalize_network")


if __name__ == "__main__":
    unittest.main()
