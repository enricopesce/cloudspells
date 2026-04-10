"""Unit tests for IAM spells."""

import unittest

import pulumi

from tests.mocks import set_mocks

set_mocks()

from cloudspells.providers.oci.iam import (
    CompartmentAdminGroup,
    ComputeInstancePrincipal,
    OkeNodePrincipal,
)

_COMP = "ocid1.compartment.oc1..test"
_TENANCY = "ocid1.tenancy.oc1..test"


class TestComputeInstancePrincipal(unittest.TestCase):
    """Test cases for ComputeInstancePrincipal spell."""

    @pulumi.runtime.test
    def test_dynamic_group_created(self):
        """Test that a DynamicGroup resource is created."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
            grants=["read secret-family", "read object-family"],
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.dynamic_group.id.apply(check)

    @pulumi.runtime.test
    def test_policy_created(self):
        """Test that a Policy resource is created."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
            grants=["read secret-family"],
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.policy.id.apply(check)

    @pulumi.runtime.test
    def test_name_follows_namer(self):
        """Test that dynamic group name uses ResourceNamer pattern."""
        spell = ComputeInstancePrincipal(
            name="app",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
            grants=["read secret-family"],
            stack_name="prod",
        )

        def check(value: str) -> None:
            self.assertIn("prod", value)
            self.assertIn("app", value)

        return spell.get_dynamic_group_id().apply(check)

    @pulumi.runtime.test
    def test_export_publishes_keys(self):
        """Test that export() publishes dynamic_group_id and policy_id outputs."""
        spell = ComputeInstancePrincipal(
            name="export-app",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
            grants=["read secret-family"],
        )
        spell.export()

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.get_dynamic_group_id().apply(check)

    def test_output_attributes_set(self) -> None:
        """Test that dynamic_group_id and policy_id attributes are set."""
        spell = ComputeInstancePrincipal(
            name="attr-app",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
            grants=["read secret-family"],
        )
        self.assertIsNotNone(spell.dynamic_group_id)
        self.assertIsNotNone(spell.policy_id)

    def test_empty_grants_raises(self) -> None:
        """Test that an empty grants list raises ValueError."""
        with self.assertRaises(ValueError):
            ComputeInstancePrincipal(
                name="bad-app",
                compartment_id=_COMP,
                tenancy_id=_TENANCY,
                grants=[],
            )


class TestOkeNodePrincipal(unittest.TestCase):
    """Test cases for OkeNodePrincipal spell."""

    @pulumi.runtime.test
    def test_dynamic_group_created(self):
        """Test that a DynamicGroup resource is created."""
        spell = OkeNodePrincipal(
            name="test-k8s",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.dynamic_group.id.apply(check)

    @pulumi.runtime.test
    def test_policy_created(self):
        """Test that a Policy resource is created."""
        spell = OkeNodePrincipal(
            name="test-k8s",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.policy.id.apply(check)

    @pulumi.runtime.test
    def test_name_follows_namer(self):
        """Test that dynamic group name uses ResourceNamer pattern."""
        spell = OkeNodePrincipal(
            name="k8s",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
            stack_name="prod",
        )

        def check(value: str) -> None:
            self.assertIn("prod", value)
            self.assertIn("k8s", value)

        return spell.get_dynamic_group_id().apply(check)

    @pulumi.runtime.test
    def test_export_publishes_keys(self):
        """Test that export() publishes dynamic_group_id and policy_id outputs."""
        spell = OkeNodePrincipal(
            name="export-k8s",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )
        spell.export()

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.get_policy_id().apply(check)

    def test_output_attributes_set(self) -> None:
        """Test that dynamic_group_id and policy_id attributes are set."""
        spell = OkeNodePrincipal(
            name="attr-k8s",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )
        self.assertIsNotNone(spell.dynamic_group_id)
        self.assertIsNotNone(spell.policy_id)


class TestCompartmentAdminGroup(unittest.TestCase):
    """Test cases for CompartmentAdminGroup spell."""

    @pulumi.runtime.test
    def test_group_created(self):
        """Test that a Group resource is created."""
        spell = CompartmentAdminGroup(
            name="test-ops",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.group.id.apply(check)

    @pulumi.runtime.test
    def test_policy_created(self):
        """Test that a Policy resource is created."""
        spell = CompartmentAdminGroup(
            name="test-ops",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.policy.id.apply(check)

    @pulumi.runtime.test
    def test_name_follows_namer(self):
        """Test that group name uses ResourceNamer pattern."""
        spell = CompartmentAdminGroup(
            name="ops",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
            stack_name="prod",
        )

        def check(value: str) -> None:
            self.assertIn("prod", value)
            self.assertIn("ops", value)

        return spell.get_group_id().apply(check)

    @pulumi.runtime.test
    def test_export_publishes_keys(self):
        """Test that export() publishes group_id and policy_id outputs."""
        spell = CompartmentAdminGroup(
            name="export-ops",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )
        spell.export()

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.get_group_id().apply(check)

    def test_output_attributes_set(self) -> None:
        """Test that group_id and policy_id attributes are set."""
        spell = CompartmentAdminGroup(
            name="attr-ops",
            compartment_id=_COMP,
            tenancy_id=_TENANCY,
        )
        self.assertIsNotNone(spell.group_id)
        self.assertIsNotNone(spell.policy_id)


if __name__ == "__main__":
    unittest.main()
