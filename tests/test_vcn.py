"""Unit tests for VCN block."""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks
set_mocks()

# Import AFTER mocks are set
from blocks.vcn.network import Vcn


class TestVcn(unittest.TestCase):
    """Test cases for VCN block."""

    @pulumi.runtime.test
    def test_vcn_creates_base_resources(self):
        """Test that VCN creates core networking resources."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
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
        """Test that VCN creates public and private route tables."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
        )

        def check_route_tables(args):
            public_rt_id, private_rt_id = args
            self.assertIsNotNone(public_rt_id, "Public route table must be created")
            self.assertIsNotNone(private_rt_id, "Private route table must be created")

        return pulumi.Output.all(
            vcn.public_route_table.id,
            vcn.private_route_table.id,
        ).apply(check_route_tables)

    @pulumi.runtime.test
    def test_vcn_subnets_not_created_before_finalize(self):
        """Test that subnets are None before finalize_network() is called."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
        )

        # Before finalization, subnets should be None
        self.assertIsNone(vcn.public_subnet, "Public subnet should be None before finalization")
        self.assertIsNone(vcn.private_subnet, "Private subnet should be None before finalization")

    @pulumi.runtime.test
    def test_vcn_subnets_created_after_finalize(self):
        """Test that subnets are created after finalize_network() is called."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
        )
        vcn.finalize_network()

        # Assert subnets exist before accessing
        assert vcn.public_subnet is not None
        assert vcn.private_subnet is not None

        def check_subnets(args):
            public_id, private_id = args
            self.assertIsNotNone(public_id, "Public subnet must be created after finalization")
            self.assertIsNotNone(private_id, "Private subnet must be created after finalization")

        return pulumi.Output.all(
            vcn.public_subnet.id,
            vcn.private_subnet.id,
        ).apply(check_subnets)

    @pulumi.runtime.test
    def test_vcn_security_lists_created_after_finalize(self):
        """Test that security lists are created after finalize_network()."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
        )
        vcn.finalize_network()

        # Assert security lists exist before accessing
        assert vcn.public_security_list is not None
        assert vcn.private_security_list is not None

        def check_security_lists(args):
            public_sl_id, private_sl_id = args
            self.assertIsNotNone(public_sl_id, "Public security list must be created")
            self.assertIsNotNone(private_sl_id, "Private security list must be created")

        return pulumi.Output.all(
            vcn.public_security_list.id,
            vcn.private_security_list.id,
        ).apply(check_security_lists)

    def test_vcn_cidr_calculation(self):
        """Test that subnet CIDRs are correctly calculated."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
            cidr_block="10.0.0.0/16",
        )

        public_cidr = vcn.get_public_subnet_cidr()
        private_cidr = vcn.get_private_subnet_cidr()

        # With /16, we split into two /17 subnets
        self.assertEqual(public_cidr, "10.0.0.0/17", "Public subnet should be first /17")
        self.assertEqual(private_cidr, "10.0.128.0/17", "Private subnet should be second /17")

    def test_vcn_custom_cidr(self):
        """Test VCN with custom CIDR block."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
            cidr_block="192.168.0.0/16",
        )

        public_cidr = vcn.get_public_subnet_cidr()
        private_cidr = vcn.get_private_subnet_cidr()

        self.assertEqual(public_cidr, "192.168.0.0/17")
        self.assertEqual(private_cidr, "192.168.128.0/17")

    def test_vcn_finalize_idempotent(self):
        """Test that finalize_network() can be called multiple times safely."""
        vcn = Vcn(
            name="test-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unittest",
        )

        # Call finalize twice - should not raise
        vcn.finalize_network()
        vcn.finalize_network()

        # Should still have valid subnets
        self.assertIsNotNone(vcn.public_subnet)
        self.assertIsNotNone(vcn.private_subnet)


if __name__ == "__main__":
    unittest.main()
