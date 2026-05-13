"""Unit tests for the VcnFlowLogs spell."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci.network import Vcn
from cloudspells.providers.oci.network_logging import VcnFlowLogs

COMP_ID = "ocid1.compartment.oc1..test"


class TestVcnFlowLogsCreation(unittest.TestCase):
    """Tests for VcnFlowLogs resource creation."""

    @pulumi.runtime.test
    def test_log_group_created(self):
        """VcnFlowLogs creates a log group resource."""
        vcn = Vcn(name="fl-vcn", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl", vcn=vcn)

        def check(log_group_id: str) -> None:
            self.assertIsNotNone(log_group_id)

        return fl.log_group_id.apply(check)

    @pulumi.runtime.test
    def test_public_flow_log_created(self):
        """VcnFlowLogs creates a flow log for the public subnet."""
        vcn = Vcn(name="fl-pub", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-pub", vcn=vcn)

        def check(log_id: str) -> None:
            self.assertIsNotNone(log_id)

        return fl.public_flow_log.id.apply(check)

    @pulumi.runtime.test
    def test_private_flow_log_created(self):
        """VcnFlowLogs creates a flow log for the private subnet."""
        vcn = Vcn(name="fl-priv", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-priv", vcn=vcn)

        def check(log_id: str) -> None:
            self.assertIsNotNone(log_id)

        return fl.private_flow_log.id.apply(check)

    @pulumi.runtime.test
    def test_flow_log_resource_names_use_literal_suffixes(self):
        """VcnFlowLogs uses fixed suffixes for per-tier logs."""
        vcn = Vcn(name="fl-literal-vcn", compartment_id=COMP_ID, stack_name="unit")
        fl = VcnFlowLogs(name="fl-literal", vcn=vcn, stack_name="unit")

        assert fl.secure_flow_log is not None
        assert fl.management_flow_log is not None

        def check(ids):
            self.assertEqual(
                list(ids),
                [
                    "unit-fl-literal-flow-log-public-id",
                    "unit-fl-literal-flow-log-private-id",
                    "unit-fl-literal-flow-log-secure-id",
                    "unit-fl-literal-flow-log-management-id",
                ],
            )

        return pulumi.Output.all(
            fl.public_flow_log.id,
            fl.private_flow_log.id,
            fl.secure_flow_log.id,
            fl.management_flow_log.id,
        ).apply(check)

    def test_secure_flow_log_present_for_live_vcn(self) -> None:
        """VcnFlowLogs creates a secure flow log when vcn is a live Vcn."""
        vcn = Vcn(name="fl-sec", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-sec", vcn=vcn)
        self.assertIsNotNone(fl.secure_flow_log)

    def test_management_flow_log_present_for_live_vcn(self) -> None:
        """VcnFlowLogs creates a management flow log when vcn is a live Vcn."""
        vcn = Vcn(name="fl-mgmt", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-mgmt", vcn=vcn)
        self.assertIsNotNone(fl.management_flow_log)

    def test_log_group_id_attribute_set(self) -> None:
        """log_group_id Output attribute is set."""
        vcn = Vcn(name="fl-lgid", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-lgid", vcn=vcn)
        self.assertIsNotNone(fl.log_group_id)


class TestVcnFlowLogsRetentionValidation(unittest.TestCase):
    """Tests for VcnFlowLogs retention_duration validation."""

    def test_default_retention_accepted(self) -> None:
        """Default retention_duration of 90 is accepted without raising."""
        vcn = Vcn(name="fl-r90", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-r90", vcn=vcn)
        self.assertIsNotNone(fl.log_group)

    def test_valid_retention_30(self) -> None:
        """retention_duration=30 is accepted."""
        vcn = Vcn(name="fl-r30", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-r30", vcn=vcn, retention_duration=30)
        self.assertIsNotNone(fl.log_group)

    def test_valid_retention_180(self) -> None:
        """retention_duration=180 is accepted."""
        vcn = Vcn(name="fl-r180", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-r180", vcn=vcn, retention_duration=180)
        self.assertIsNotNone(fl.log_group)

    def test_invalid_retention_raises(self) -> None:
        """retention_duration not in {30,60,90,120,150,180} raises ValueError."""
        vcn = Vcn(name="fl-rbad", compartment_id=COMP_ID)
        with self.assertRaises(ValueError):
            VcnFlowLogs(name="fl-rbad", vcn=vcn, retention_duration=45)

    def test_invalid_retention_zero_raises(self) -> None:
        """retention_duration=0 raises ValueError."""
        vcn = Vcn(name="fl-r0", compartment_id=COMP_ID)
        with self.assertRaises(ValueError):
            VcnFlowLogs(name="fl-r0", vcn=vcn, retention_duration=0)


class TestVcnFlowLogsCompartmentInference(unittest.TestCase):
    """Tests for VcnFlowLogs compartment_id inference and validation."""

    def test_compartment_inferred_from_vcn(self) -> None:
        """compartment_id is inferred from the live Vcn when not supplied."""
        vcn = Vcn(name="fl-cinfer", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-cinfer", vcn=vcn)
        self.assertIsNotNone(fl.compartment_id)

    def test_explicit_compartment_accepted(self) -> None:
        """Explicit compartment_id is accepted alongside a live Vcn."""
        vcn = Vcn(name="fl-cexpl", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-cexpl", vcn=vcn, compartment_id=COMP_ID)
        self.assertIsNotNone(fl.log_group)


class TestVcnFlowLogsExport(unittest.TestCase):
    """Tests for VcnFlowLogs.export()."""

    def test_export_does_not_raise(self) -> None:
        """export() completes without raising."""
        vcn = Vcn(name="fl-exp", compartment_id=COMP_ID)
        fl = VcnFlowLogs(name="fl-exp", vcn=vcn)
        fl.export()  # should not raise


if __name__ == "__main__":
    unittest.main()
