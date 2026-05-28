"""Unit tests for IAM spells."""

import unittest
from dataclasses import dataclass

import pulumi

from tests.mocks import set_mocks

set_mocks()

from cloudspells.providers.oci.iam import (
    CompartmentAdminGroup,
    ComputeInstancePrincipal,
    IamGrant,
    OkeNodePrincipal,
)

_COMP = "ocid1.compartment.oc1..test"
_TENANCY = "ocid1.tenancy.oc1..test"
_INSTANCE_1 = "ocid1.instance.oc1..app1"
_INSTANCE_2 = "ocid1.instance.oc1..app2"


@dataclass(frozen=True)
class _PrincipalInstance:
    """Minimal compute-instance stand-in for IAM membership tests."""

    id: pulumi.Output[str]
    compartment_id: pulumi.Input[str]


def _instance(instance_id: str, compartment_id: pulumi.Input[str] = _COMP) -> _PrincipalInstance:
    """Return a fake principal member with an instance OCID output."""
    return _PrincipalInstance(id=pulumi.Output.from_input(instance_id), compartment_id=compartment_id)


class TestComputeInstancePrincipal(unittest.TestCase):
    """Test cases for ComputeInstancePrincipal spell."""

    @pulumi.runtime.test
    def test_dynamic_group_created(self):
        """Test that a DynamicGroup resource is created."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1)],
            grants=[IamGrant.read_secrets(), IamGrant.read_objects()],
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.dynamic_group.id.apply(check)

    @pulumi.runtime.test
    def test_dynamic_group_matches_single_instance_id(self):
        """Test that a single-instance principal matches only that instance OCID."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1)],
            grants=[IamGrant.read_secrets()],
        )

        def check(value: str) -> None:
            self.assertEqual(value, f"instance.id = '{_INSTANCE_1}'")

        return spell.dynamic_group.matching_rule.apply(check)

    @pulumi.runtime.test
    def test_dynamic_group_matches_multiple_instance_ids(self):
        """Test that a multi-instance principal uses an explicit instance OCID set."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1), _instance(_INSTANCE_2)],
            grants=[IamGrant.read_secrets()],
        )

        def check(value: str) -> None:
            self.assertEqual(
                value,
                f"any {{instance.id = '{_INSTANCE_1}', instance.id = '{_INSTANCE_2}'}}",
            )

        return spell.dynamic_group.matching_rule.apply(check)

    @pulumi.runtime.test
    def test_dynamic_group_can_match_existing_instance_ids(self):
        """Test that pre-existing instance OCIDs can be used as exact members."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            tenancy_id=_TENANCY,
            compartment_id=_COMP,
            instance_ids=[_INSTANCE_1],
            grants=[IamGrant.read_secrets()],
        )

        def check(value: str) -> None:
            self.assertEqual(value, f"instance.id = '{_INSTANCE_1}'")

        return spell.dynamic_group.matching_rule.apply(check)

    @pulumi.runtime.test
    def test_policy_uses_grant_objects(self):
        """Test that policy statements are generated from explicit IAM grants."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1)],
            grants=[IamGrant.raw("read secret-family")],
            stack_name="prod",
        )

        def check(args: list[object]) -> None:
            statements, dynamic_group_id = args
            self.assertEqual(
                statements,
                [f"Allow dynamic-group id {dynamic_group_id} to read secret-family in compartment id {_COMP}"],
            )

        return pulumi.Output.all(spell.policy.statements, spell.dynamic_group.id).apply(check)

    def test_instance_ids_require_compartment_id(self) -> None:
        """Test that explicit instance OCIDs require an explicit policy compartment."""
        with self.assertRaises(ValueError):
            ComputeInstancePrincipal(
                name="bad-app",
                tenancy_id=_TENANCY,
                instance_ids=[_INSTANCE_1],
                grants=[IamGrant.read_secrets()],
            )

    @pulumi.runtime.test
    def test_policy_created(self):
        """Test that a Policy resource is created."""
        spell = ComputeInstancePrincipal(
            name="test-app",
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1)],
            grants=[IamGrant.read_secrets()],
        )

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.policy.id.apply(check)

    @pulumi.runtime.test
    def test_name_follows_namer(self):
        """Test that dynamic group name uses ResourceNamer pattern."""
        spell = ComputeInstancePrincipal(
            name="app",
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1)],
            grants=[IamGrant.read_secrets()],
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
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1)],
            grants=[IamGrant.read_secrets()],
        )
        spell.export()

        def check(value: str) -> None:
            self.assertIsNotNone(value)

        return spell.get_dynamic_group_id().apply(check)

    def test_output_attributes_set(self) -> None:
        """Test that dynamic_group_id and policy_id attributes are set."""
        spell = ComputeInstancePrincipal(
            name="attr-app",
            tenancy_id=_TENANCY,
            instances=[_instance(_INSTANCE_1)],
            grants=[IamGrant.read_secrets()],
        )
        self.assertIsNotNone(spell.dynamic_group_id)
        self.assertIsNotNone(spell.policy_id)

    def test_empty_grants_raises(self) -> None:
        """Test that an empty grants list raises ValueError."""
        with self.assertRaises(ValueError):
            ComputeInstancePrincipal(
                name="bad-app",
                tenancy_id=_TENANCY,
                instances=[_instance(_INSTANCE_1)],
                grants=[],
            )

    def test_empty_instances_raises(self) -> None:
        """Test that an empty instance list raises ValueError."""
        with self.assertRaises(ValueError):
            ComputeInstancePrincipal(
                name="bad-app",
                tenancy_id=_TENANCY,
                instances=[],
                grants=[IamGrant.read_secrets()],
            )

    def test_raw_grant_rejects_full_policy_statement(self) -> None:
        """Test that raw grants remain grant fragments, not full statements."""
        with self.assertRaises(ValueError):
            IamGrant.raw("Allow dynamic-group app to read secret-family in tenancy")

    def test_grants_must_be_explicit(self) -> None:
        """ComputeInstancePrincipal does not grant broad defaults."""
        with self.assertRaises(ValueError):
            ComputeInstancePrincipal(
                name="bad-defaults",
                tenancy_id=_TENANCY,
                instances=[_instance(_INSTANCE_1)],
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
            dedicated_node_compartment=True,
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
            dedicated_node_compartment=True,
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
            dedicated_node_compartment=True,
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
            dedicated_node_compartment=True,
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
            dedicated_node_compartment=True,
        )
        self.assertIsNotNone(spell.dynamic_group_id)
        self.assertIsNotNone(spell.policy_id)

    def test_dedicated_node_compartment_must_be_acknowledged(self) -> None:
        """OkeNodePrincipal requires explicit compartment-wide matching intent."""
        with self.assertRaises(ValueError):
            OkeNodePrincipal(
                name="unsafe-k8s",
                compartment_id=_COMP,
                tenancy_id=_TENANCY,
            )


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
