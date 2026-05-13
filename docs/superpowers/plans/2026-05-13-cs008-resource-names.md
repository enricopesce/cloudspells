# CS-008 Resource Names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all f-string-derived suffixes passed to `create_resource_name(...)`, decouple repeated resource names from caller labels where practical, and add a regression test for CS-008.

**Architecture:** Finite CloudSpells-owned resources use literal suffix maps or config fields. Repeated resources whose cardinality comes from a list use a new private OCI helper, `ordinal_suffix()`, which creates deterministic ordinal suffixes from a literal prefix and a zero-based index; caller labels remain available for lookup, tags, and descriptions but stop shaping Pulumi logical names. A static AST test prevents reintroducing f-strings, concatenation, `.format()`, or `%` formatting directly inside `create_resource_name(...)` calls, and requires `ordinal_suffix()` prefixes to be literals.

**Tech Stack:** Python 3.11, Pulumi Python, pulumi-oci, pytest, ruff, pyright, vulture.

---

## File Structure

- Create: `packages/cloudspells-oci/src/cloudspells/providers/oci/_naming.py`
  - Private helper for CloudSpells-owned ordinal suffixes used by repeated OCI resources.
- Create: `tests/test_cs008_resource_names.py`
  - AST regression test for direct dynamic suffix construction in `create_resource_name(...)`.
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py`
  - Replace tier f-string suffixes with literal suffix fields in `_SubnetConfig` and literal tier config.
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py`
  - Replace flow-log tier f-string suffixes with literal suffix arguments.
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py`
  - Add ordinal rule slots independent of public labels; preserve label uniqueness.
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py`
  - Use ordinal volume and attachment suffixes; keep `VolumeSpec.label` for lookups and tags.
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py`
  - Update docstring so `label` is not documented as a resource-name suffix.
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py`
  - Use ordinal node-pool and kubectl-rule suffixes; keep `NodePoolConfig.name` as a semantic pool label.
- Modify: `tests/test_vcn.py`
  - Assert VCN tier resources keep the expected names after literal mapping.
- Modify: `tests/test_network_logging.py`
  - Assert flow logs use literal tier suffixes.
- Modify: `tests/test_nsg.py`
  - Assert rule resource names are ordinal and duplicate labels fail early.
- Modify: `tests/test_compute.py`
  - Assert volume resource names are ordinal while label accessors still work.
- Modify: `tests/test_oke.py`
  - Assert node-pool and kubectl-rule names are ordinal while node-pool count and CIDR behavior remain intact.
- Modify: docs where wording says public labels are used as resource name suffixes:
  - `README.md`
  - `docs/tutorials/compute.md`
  - `docs/tutorials/oke.md`
  - `docs/reference/oke-architecture.md`
  - `packages/cloudspells-core/src/cloudspells/core/abstractions/compute.py`

## Decisions

- Do not remove `VolumeSpec.label`, `NodePoolConfig.name`, or NSG helper `label` parameters in this fix. That would be a larger public API migration.
- Do stop using those values in new Pulumi resource names.
- Resource logical names for existing deployed stacks will change for the affected repeated resources. This can cause Pulumi previews to show replacements unless state aliases or state renames are handled separately. This plan documents the behavior change but does not add migration aliases, because aliases would need to reproduce the old caller-derived names and should be planned as a separate state-migration task.

---

### Task 1: Add CS-008 Static Regression Test

**Files:**
- Create: `tests/test_cs008_resource_names.py`

- [ ] **Step 1: Write the failing AST test**

Create `tests/test_cs008_resource_names.py`:

```python
"""Static CS-008 checks for CloudSpells resource names."""

from __future__ import annotations

import ast
from pathlib import Path


PROVIDER_ROOT = Path("packages/cloudspells-oci/src/cloudspells/providers/oci")


def _python_files() -> list[Path]:
    """Return OCI provider Python files that should obey CS-008."""
    return sorted(path for path in PROVIDER_ROOT.glob("*.py") if path.name != "__init__.py")


def _is_create_resource_name_call(node: ast.Call) -> bool:
    """Return True when `node` calls `.create_resource_name(...)`."""
    return isinstance(node.func, ast.Attribute) and node.func.attr == "create_resource_name"


def _is_format_call(node: ast.AST) -> bool:
    """Return True when `node` is `"{}".format(...)` style formatting."""
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"


def _is_percent_format(node: ast.AST) -> bool:
    """Return True when `node` is old-style string interpolation."""
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)


def _dynamic_name_reason(node: ast.AST) -> str | None:
    """Return a CS-008 violation reason for direct dynamic suffix expressions."""
    if isinstance(node, ast.JoinedStr):
        return "f-string"
    if isinstance(node, ast.BinOp):
        if _is_percent_format(node):
            return "percent-format"
        return "string-concatenation"
    if _is_format_call(node):
        return "format-call"
    return None


def test_create_resource_name_does_not_receive_inline_dynamic_suffixes() -> None:
    """`create_resource_name(...)` calls must not inline dynamic suffix construction."""
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_create_resource_name_call(node):
                continue
            if not node.args:
                continue
            reason = _dynamic_name_reason(node.args[0])
            if reason is not None:
                violations.append(f"{path}:{node.lineno}: create_resource_name uses {reason}")

    assert violations == []


def test_ordinal_suffix_prefixes_are_literals() -> None:
    """Ordinal resource suffix prefixes must be CloudSpells-owned literals."""
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "ordinal_suffix":
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                violations.append(f"{path}:{node.lineno}: ordinal_suffix prefix must be a string literal")

    assert violations == []
```

- [ ] **Step 2: Run test to verify it fails on the current violations**

Run:

```bash
.venv/bin/pytest tests/test_cs008_resource_names.py -q
```

Expected: FAIL. The failure list includes at least these current files:

```text
packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py
packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py
packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py
packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py
packages/cloudspells-oci/src/cloudspells/providers/oci/network.py
```

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_cs008_resource_names.py
git commit -m "test: add CS-008 resource name regression check"
```

---

### Task 2: Add Private OCI Naming Helper

**Files:**
- Create: `packages/cloudspells-oci/src/cloudspells/providers/oci/_naming.py`
- Test: `tests/test_cs008_resource_names.py`

- [ ] **Step 1: Add the helper**

Create `packages/cloudspells-oci/src/cloudspells/providers/oci/_naming.py`:

```python
"""Internal naming helpers for OCI provider spells.

These helpers are private to the OCI provider package. Public spells should
still call `BaseResource.create_resource_name(...)` for the final resource name.
"""

from __future__ import annotations


def ordinal_suffix(prefix: str, index: int) -> str:
    """Return a deterministic ordinal resource suffix.

    Use this only for repeated child resources whose count comes from an
    internal list position. The `prefix` must be a CloudSpells-owned literal,
    not caller input.

    Args:
        prefix: Literal suffix prefix such as `"vol"` or `"nsg-rule"`.
        index: Zero-based item index.

    Returns:
        Suffix string with a one-based ordinal, such as `"vol-1"`.

    Raises:
        ValueError: If `index` is negative.
    """
    if index < 0:
        raise ValueError("ordinal resource suffix index must be non-negative")
    return "-".join((prefix, str(index + 1)))
```

- [ ] **Step 2: Add direct helper tests to the static test file**

Append to `tests/test_cs008_resource_names.py`:

```python
from cloudspells.providers.oci._naming import ordinal_suffix


def test_ordinal_suffix_uses_one_based_indices() -> None:
    """Ordinal suffixes are deterministic and one-based."""
    assert ordinal_suffix("vol", 0) == "vol-1"
    assert ordinal_suffix("vol", 1) == "vol-2"


def test_ordinal_suffix_rejects_negative_indices() -> None:
    """Negative ordinal indices are invalid."""
    try:
        ordinal_suffix("vol", -1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("ordinal_suffix must reject negative indices")
```

- [ ] **Step 3: Run the helper tests**

Run:

```bash
.venv/bin/pytest tests/test_cs008_resource_names.py::test_ordinal_suffix_uses_one_based_indices tests/test_cs008_resource_names.py::test_ordinal_suffix_rejects_negative_indices -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/_naming.py tests/test_cs008_resource_names.py
git commit -m "refactor: add OCI ordinal resource suffix helper"
```

---

### Task 3: Fix VCN Tier Resource Names

**Files:**
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py`
- Modify: `tests/test_vcn.py`

- [ ] **Step 1: Add failing VCN name assertions**

In `tests/test_vcn.py`, add this test inside `class TestVcn` after `test_vcn_security_lists_created_after_finalize`:

```python
    @pulumi.runtime.test
    def test_vcn_tier_resource_names_are_literal_suffixes(self):
        """Tier security lists, route tables, and subnets use fixed suffixes."""
        vcn = Vcn(
            name="literal-vcn",
            compartment_id="ocid1.compartment.test",
            stack_name="unit",
        )
        vcn.finalize_network()

        assert vcn.public_subnet is not None
        assert vcn.private_subnet is not None
        assert vcn.secure_subnet is not None
        assert vcn.management_subnet is not None

        def check(ids):
            expected = [
                "unit-literal-vcn-sl-public-id",
                "unit-literal-vcn-sl-private-id",
                "unit-literal-vcn-sl-secure-id",
                "unit-literal-vcn-sl-management-id",
                "unit-literal-vcn-rt-public-id",
                "unit-literal-vcn-rt-private-id",
                "unit-literal-vcn-rt-secure-id",
                "unit-literal-vcn-rt-management-id",
                "unit-literal-vcn-sn-public-id",
                "unit-literal-vcn-sn-private-id",
                "unit-literal-vcn-sn-secure-id",
                "unit-literal-vcn-sn-management-id",
            ]
            self.assertEqual(ids, expected)

        return pulumi.Output.all(
            vcn.public_security_list.id,
            vcn.private_security_list.id,
            vcn.secure_security_list.id,
            vcn.management_security_list.id,
            vcn.public_route_table.id,
            vcn.private_route_table.id,
            vcn.secure_route_table.id,
            vcn.management_route_table.id,
            vcn.public_subnet.id,
            vcn.private_subnet.id,
            vcn.secure_subnet.id,
            vcn.management_subnet.id,
        ).apply(check)
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_vcn_tier_resource_names_are_literal_suffixes -q
```

Expected: PASS before code changes because current names match these values. This is a characterization test before the mechanical refactor.

- [ ] **Step 3: Replace f-string suffixes with literal tier config**

In `network.py`, change `_SubnetConfig` to carry tier and suffix metadata:

```python
@dataclass
class _SubnetConfig:
    """Internal configuration record for a single subnet.

    Used by `Vcn._create_subnets` to hold the per-subnet parameters
    resolved during `Vcn.finalize_network`.

    Attributes:
        tier: Subnet tier name (`"public"`, `"private"`, `"secure"`, or
            `"management"`).
        cidr: IPv4 CIDR block assigned to the subnet.
        is_public: `True` for a public subnet; `False` for a private subnet.
        dns_label: Short DNS label prefix passed to
            `BaseResource.create_dns_label`.
        security_list_suffix: Literal suffix for the tier security list.
        route_table_suffix: Literal suffix for the tier route table.
        subnet_suffix: Literal suffix for the tier subnet.
        ipv6_cidr: IPv6 `/64` CIDR to assign to the subnet, or `None`.
    """

    tier: str
    cidr: str
    is_public: bool
    dns_label: str
    security_list_suffix: str
    route_table_suffix: str
    subnet_suffix: str
    ipv6_cidr: pulumi.Input[str] | None = None
```

In `_create_security_lists`, replace the nested `_make(tier, ...)` signature with:

```python
        def _make(
            suffix: str,
            tier: str,
            ingress: list[oci.core.SecurityListIngressSecurityRuleArgs],
            egress: list[oci.core.SecurityListEgressSecurityRuleArgs],
        ) -> oci.core.SecurityList:
            name = self.create_resource_name(suffix)
            return oci.core.SecurityList(
                name,
                compartment_id=self.compartment_id,
                vcn_id=self.vcn.id,
                display_name=name,
                ingress_security_rules=ingress,
                egress_security_rules=egress,
                freeform_tags=self.create_network_resource_tags(name, "security-list", tier, tier),
                defined_tags=self._defined_tags,
                opts=pulumi.ResourceOptions(parent=self),
            )

        self.public_security_list = _make("sl-public", "public", self._public_ingress_rules, self._public_egress_rules)
        self.private_security_list = _make("sl-private", "private", self._private_ingress_rules, self._private_egress_rules)
        self.secure_security_list = _make("sl-secure", "secure", self._secure_ingress_rules, self._secure_egress_rules)
        self.management_security_list = _make(
            "sl-management", "management", self._management_ingress_rules, self._management_egress_rules
        )
```

In `_create_route_tables`, replace `_make_rt(tier, ...)` and calls with:

```python
        def _make_rt(suffix: str, tier: str, rules: list[oci.core.RouteTableRouteRuleArgs]) -> oci.core.RouteTable:
            name = self.create_resource_name(suffix)
            return oci.core.RouteTable(
                name,
                compartment_id=self.compartment_id,
                vcn_id=self.vcn.id,
                display_name=name,
                route_rules=rules,
                freeform_tags=self.create_network_resource_tags(name, "route-table", tier, tier),
                defined_tags=self._defined_tags,
                opts=pulumi.ResourceOptions(parent=self),
            )

        self.public_route_table = _make_rt("rt-public", "public", public_route_rules)
        self.private_route_table = _make_rt("rt-private", "private", private_route_rules)
        self.secure_route_table = _make_rt("rt-secure", "secure", secure_route_rules)
        self.management_route_table = _make_rt("rt-management", "management", management_route_rules)
```

In `_create_subnets`, replace `subnet_configs` with config objects that include literal suffixes:

```python
        subnet_configs: tuple[_SubnetConfig, ...] = (
            _SubnetConfig(
                "public",
                public_cidr,
                True,
                "pub",
                "sl-public",
                "rt-public",
                "sn-public",
                self._compute_ipv6_subnet_cidr(2) if self._ipv6_enabled else None,
            ),
            _SubnetConfig(
                "private",
                private_cidr,
                False,
                "priv",
                "sl-private",
                "rt-private",
                "sn-private",
                self._compute_ipv6_subnet_cidr(0) if self._ipv6_enabled else None,
            ),
            _SubnetConfig(
                "secure",
                secure_cidr,
                False,
                "sec",
                "sl-secure",
                "rt-secure",
                "sn-secure",
                self._compute_ipv6_subnet_cidr(1) if self._ipv6_enabled else None,
            ),
            _SubnetConfig(
                "management",
                management_cidr,
                False,
                "mgmt",
                "sl-management",
                "rt-management",
                "sn-management",
                self._compute_ipv6_subnet_cidr(3) if self._ipv6_enabled else None,
            ),
        )

        for config in subnet_configs:
            security_list: oci.core.SecurityList = getattr(self, f"{config.tier}_security_list")
            route_table: oci.core.RouteTable = getattr(self, f"{config.tier}_route_table")

            subnet_name = self.create_resource_name(config.subnet_suffix)
            setattr(
                self,
                f"{config.tier}_subnet",
                self._create_subnet(subnet_name, config, security_list, route_table, config.tier),
            )
```

- [ ] **Step 4: Run focused checks**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_vcn_tier_resource_names_are_literal_suffixes tests/test_cs008_resource_names.py -q
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/network.py
```

Expected: PASS for the VCN test and static CS-008 test should still fail only for the remaining modules.

- [ ] **Step 5: Commit**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/network.py tests/test_vcn.py
git commit -m "fix: use literal VCN tier resource suffixes"
```

---

### Task 4: Fix VCN Flow Log Resource Names

**Files:**
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py`
- Modify: `tests/test_network_logging.py`

- [ ] **Step 1: Add failing/characterization flow-log name test**

Add to `TestVcnFlowLogsCreation` in `tests/test_network_logging.py`:

```python
    @pulumi.runtime.test
    def test_flow_log_resource_names_use_literal_suffixes(self):
        """Flow log resources use fixed tier suffixes."""
        vcn = Vcn(name="fl-literal-vcn", compartment_id=COMP_ID, stack_name="unit")
        fl = VcnFlowLogs(name="fl-literal", vcn=vcn, stack_name="unit")

        assert fl.secure_flow_log is not None
        assert fl.management_flow_log is not None

        def check(ids):
            self.assertEqual(
                ids,
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
```

- [ ] **Step 2: Run focused test**

Run:

```bash
.venv/bin/pytest tests/test_network_logging.py::TestVcnFlowLogsCreation::test_flow_log_resource_names_use_literal_suffixes -q
```

Expected: PASS before code changes because current names match these values.

- [ ] **Step 3: Replace f-string suffix with literal suffix parameter**

In `network_logging.py`, change `_flow_log` signature and docstring:

```python
    def _flow_log(self, tier: str, suffix: str, subnet_id: pulumi.Input[str]) -> oci.logging.Log:
        """Create a VCN Flow Log `oci.logging.Log` for a single subnet.

        Args:
            tier: Short tier label used in tags.
            suffix: Literal resource-name suffix for this flow log.
            subnet_id: The subnet OCID to attach the flow log to.

        Returns:
            The newly created `oci.logging.Log` resource.
        """
        log_name = self.create_resource_name(suffix)
```

Update `_create_flow_logs` calls:

```python
        self.public_flow_log = self._flow_log("public", "flow-log-public", pub.id)
        self.private_flow_log = self._flow_log("private", "flow-log-private", priv.id)

        self.secure_flow_log = self._flow_log("secure", "flow-log-secure", sec.id) if sec else None
        self.management_flow_log = self._flow_log("management", "flow-log-management", mgmt.id) if mgmt else None
```

- [ ] **Step 4: Run focused checks**

Run:

```bash
.venv/bin/pytest tests/test_network_logging.py::TestVcnFlowLogsCreation::test_flow_log_resource_names_use_literal_suffixes tests/test_cs008_resource_names.py -q
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py
```

Expected: PASS for flow-log test; static CS-008 test should still fail only for remaining modules.

- [ ] **Step 5: Commit**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py tests/test_network_logging.py
git commit -m "fix: use literal flow log resource suffixes"
```

---

### Task 5: Fix NSG Rule Resource Names

**Files:**
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py`
- Modify: `tests/test_nsg.py`

- [ ] **Step 1: Add failing NSG rule name and duplicate-label tests**

Add to `TestNsgRuleHelpers` in `tests/test_nsg.py`:

```python
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
        """NSG helper labels remain unique even though labels no longer name resources."""
        vcn = Vcn(name="rule-dupe-vcn", compartment_id=COMP_ID, stack_name="unit")
        nsg = Nsg("rule-dupe", vcn=vcn, compartment_id=COMP_ID, stack_name="unit")

        nsg.allow_to_cidr("inet-out", INTERNET)
        with self.assertRaises(ValueError):
            nsg.allow_to_cidr("inet-out", INTERNET)
```

- [ ] **Step 2: Run focused tests to verify the name test fails**

Run:

```bash
.venv/bin/pytest tests/test_nsg.py::TestNsgRuleHelpers::test_nsg_rule_resource_name_uses_ordinal_slot_not_label tests/test_nsg.py::TestNsgRuleHelpers::test_duplicate_nsg_rule_label_raises -q
```

Expected: FAIL. Current rule ID is `unit-rule-name-nsg-rule-https-in-id`, and duplicate labels currently fail late or inconsistently through Pulumi naming rather than an explicit `ValueError`.

- [ ] **Step 3: Implement ordinal NSG rule slots**

In `nsg.py`, import the helper:

```python
from ._naming import ordinal_suffix
```

In `Nsg.__init__`, after `self.role = role`, initialize label tracking:

```python
        self._rule_labels: set[str] = set()
        self._next_rule_index = 0
```

In `_add_rule`, replace the resource-name creation with:

```python
        if label in self._rule_labels:
            raise ValueError(f"Nsg rule label must be unique within this NSG; duplicate label: {label!r}")
        self._rule_labels.add(label)
        rule_index = self._next_rule_index
        self._next_rule_index += 1
        resource_name = self.create_resource_name(ordinal_suffix("nsg-rule", rule_index))
```

Also update the default description so the user-facing label remains visible when no explicit description is supplied:

```python
            description=description or label,
```

Update `_add_rule` docstring line that currently says the Pulumi resource name is `{stack}-{nsg-name}-nsg-rule-{label}`:

```python
        The Pulumi resource name uses an internal ordinal suffix such as
        `{stack}-{nsg-name}-nsg-rule-1`. `label` remains the human-readable
        unique key for this rule within the NSG.
```

- [ ] **Step 4: Run focused checks**

Run:

```bash
.venv/bin/pytest tests/test_nsg.py::TestNsgRuleHelpers::test_nsg_rule_resource_name_uses_ordinal_slot_not_label tests/test_nsg.py::TestNsgRuleHelpers::test_duplicate_nsg_rule_label_raises tests/test_cs008_resource_names.py -q
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py
```

Expected: PASS for the NSG tests; static CS-008 test should still fail only for remaining modules.

- [ ] **Step 5: Commit**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py tests/test_nsg.py
git commit -m "fix: use ordinal NSG rule resource suffixes"
```

---

### Task 6: Fix Compute Volume Resource Names

**Files:**
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py`
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py`
- Modify: `packages/cloudspells-core/src/cloudspells/core/abstractions/compute.py`
- Modify: `tests/test_compute.py`

- [ ] **Step 1: Add failing compute resource-name test**

Add to `TestComputeInstance` in `tests/test_compute.py`:

```python
    @pulumi.runtime.test
    def test_volume_resource_names_use_ordinal_slots_not_labels(self):
        """Volume and attachment resource names use internal ordinal slots."""
        instance = ComputeInstance(
            name="slot-instance",
            compartment_id="ocid1.compartment.test",
            nsg=self._make_nsg(),
            image_id="ocid1.image.oc1.phx.test",
            availability_domain="AD-1",
            ssh_public_key="ssh-rsa AAAAB3... test-key",
            stack_name="unit",
            volumes=[
                VolumeSpec(size_in_gbs=100, label="data"),
                VolumeSpec(size_in_gbs=200, label="logs"),
            ],
        )

        def check(ids):
            self.assertEqual(
                ids,
                [
                    "unit-slot-instance-vol-1-id",
                    "unit-slot-instance-vol-2-id",
                    "unit-slot-instance-vol-attach-1-id",
                    "unit-slot-instance-vol-attach-2-id",
                ],
            )

        return pulumi.Output.all(
            instance.block_volumes[0].id,
            instance.block_volumes[1].id,
            instance.volume_attachments[0].id,
            instance.volume_attachments[1].id,
        ).apply(check)
```

- [ ] **Step 2: Run focused test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_compute.py::TestComputeInstance::test_volume_resource_names_use_ordinal_slots_not_labels -q
```

Expected: FAIL. Current IDs are label-derived, such as `unit-slot-instance-data-vol-id`.

- [ ] **Step 3: Implement ordinal volume suffixes**

In `compute.py`, import the helper:

```python
from ._naming import ordinal_suffix
```

Change the loop in `_attach_block_volumes`:

```python
        for index, spec in enumerate(self.volumes_spec):
            vol_name = self.create_resource_name(ordinal_suffix("vol", index))
            vol = oci.core.Volume(
                vol_name,
                availability_domain=availability_domain,
                compartment_id=self.compartment_id,
                display_name=vol_name,
                size_in_gbs=str(spec.size_in_gbs),
                vpus_per_gb=str(spec.vpus_per_gb),
                freeform_tags=self.create_freeform_tags(
                    vol_name,
                    "block-volume",
                    {
                        "SizeGB": str(spec.size_in_gbs),
                        "Label": spec.label,
                        "PerfTier": str(spec.vpus_per_gb),
                        "AttachedTo": instance_name,
                    },
                ),
                opts=pulumi.ResourceOptions(parent=self),
            )
            att_name = self.create_resource_name(ordinal_suffix("vol-attach", index))
            att = oci.core.VolumeAttachment(
                att_name,
                instance_id=self.instance.id,
                volume_id=vol.id,
                attachment_type="paravirtualized",
                display_name=att_name,
                is_read_only=spec.is_read_only,
                device=spec.device,
                opts=pulumi.ResourceOptions(
                    parent=self,
                    delete_before_replace=True,
                    depends_on=[self.instance, vol],
                ),
            )
            self.block_volumes.append(vol)
            self.volume_attachments.append(att)
```

Update `ComputeInstance.__init__` docstring for `volumes`:

```python
            volumes: Ordered list of `VolumeSpec` objects describing the
                block volumes to attach. Each entry must have a unique `label`;
                the label is used for lookup helpers, outputs, and tags, while
                Pulumi resource names use CloudSpells-owned ordinal slots.
```

Update module docstring if needed:

```python
- Accepts a list of `VolumeSpec` objects to attach one or more block volumes;
  labels are used for lookups and tags, not Pulumi resource names.
```

- [ ] **Step 4: Update VolumeSpec and abstraction docstrings**

In `packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py`, replace the `label` attribute text with:

```python
        label: Short slug used by `ComputeInstance` lookup helpers, outputs,
            and freeform tags (e.g. `"data"`, `"logs"`, `"db"`). Must start
            with a lowercase letter, end with a lowercase letter or digit, and
            contain only lowercase letters, digits, or single hyphens.
```

In `packages/cloudspells-core/src/cloudspells/core/abstractions/compute.py`, replace any wording that says the label derives the resource name suffix with:

```python
        label: Logical slug used by provider implementations for lookup
            helpers, outputs, and tags.
```

- [ ] **Step 5: Run focused checks**

Run:

```bash
.venv/bin/pytest tests/test_compute.py::TestComputeInstance::test_volume_resource_names_use_ordinal_slots_not_labels tests/test_compute.py::TestComputeInstance::test_get_volume_id_by_label tests/test_compute.py::TestComputeInstance::test_get_volume_returns_oci_resource tests/test_cs008_resource_names.py -q
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py
make check-file FILE=packages/cloudspells-core/src/cloudspells/core/abstractions/compute.py
```

Expected: PASS for focused compute behavior. Static CS-008 test should still fail only for remaining modules.

- [ ] **Step 6: Commit**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py packages/cloudspells-core/src/cloudspells/core/abstractions/compute.py tests/test_compute.py
git commit -m "fix: use ordinal compute volume resource suffixes"
```

---

### Task 7: Fix OKE Node Pool and Kubectl Rule Resource Names

**Files:**
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py`
- Modify: `tests/test_oke.py`

- [ ] **Step 1: Add failing OKE resource-name tests**

Add to `TestOkeCluster` in `tests/test_oke.py`:

```python
    @pulumi.runtime.test
    def test_oke_node_pool_resource_names_use_ordinal_slots_not_names(self):
        """Node pool resource names use internal ordinal slots."""
        pools = [
            NodePoolConfig(
                name="system",
                shape="VM.Standard.A1.Flex",
                image="ocid1.image.test",
                node_count=2,
                ocpus=2,
                memory_in_gbs=16,
            ),
            NodePoolConfig(
                name="app",
                shape="VM.Standard.E4.Flex",
                image="ocid1.image.test",
                node_count=5,
                ocpus=8,
                memory_in_gbs=64,
            ),
        ]
        oke = OkeCluster(
            name="slot-cluster",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            kubernetes_version="v1.28.2",
            node_pools=pools,
            kubectl_allowed_cidrs=["10.0.0.0/8"],
            stack_name="unit",
        )

        def check(ids):
            self.assertEqual(ids, ["unit-slot-cluster-pool-1-id", "unit-slot-cluster-pool-2-id"])

        return pulumi.Output.all(oke.node_pools[0].id, oke.node_pools[1].id).apply(check)

    @pulumi.runtime.test
    def test_kubectl_rule_resource_names_use_ordinal_slots(self):
        """External kubectl NSG rules use internal ordinal slots."""
        oke = OkeCluster(
            name="kubectl-slots",
            compartment_id="ocid1.compartment.test",
            vcn=self._make_vcn(),
            kubernetes_version="v1.28.2",
            node_pools=[_DEFAULT_POOL],
            kubectl_allowed_cidrs=["10.0.0.0/8", "192.168.1.0/24"],
            stack_name="unit",
        )

        def check(ids):
            self.assertEqual(
                ids,
                [
                    "unit-kubectl-slots-api-nsg-ingress-kubectl-1-id",
                    "unit-kubectl-slots-api-nsg-ingress-kubectl-2-id",
                ],
            )

        return pulumi.Output.all(
            oke._api_nsg_rules[4].id,
            oke._api_nsg_rules[5].id,
        ).apply(check)
```

- [ ] **Step 2: Run focused tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_oke.py::TestOkeCluster::test_oke_node_pool_resource_names_use_ordinal_slots_not_names tests/test_oke.py::TestOkeCluster::test_kubectl_rule_resource_names_use_ordinal_slots -q
```

Expected: FAIL. Current node pools are `pool-system` / `pool-app`; current kubectl rule IDs end in `kubectl-0` / `kubectl-1`.

- [ ] **Step 3: Implement ordinal suffixes in kubernetes.py**

In `kubernetes.py`, import the helper:

```python
from ._naming import ordinal_suffix
```

Change the node-pool loop header and `pool_name` assignment:

```python
        for index, cfg in enumerate(node_pools):
            pool_name = self.create_resource_name(ordinal_suffix("pool", index))  # type: ignore[attr-defined]
```

In the same `NodePool` resource, replace the `freeform_tags=` argument with:

```python
                freeform_tags=self.create_freeform_tags(  # type: ignore[attr-defined]
                    pool_name,
                    "oke-node-pool",
                    {"PoolLabel": cfg.name},
                ),
```

Change the kubectl-rule creation:

```python
        for i, cidr in enumerate(self.kubectl_allowed_cidrs):
            rules.append(
                self._r(
                    self.create_resource_name(ordinal_suffix("api-nsg-ingress-kubectl", i)),  # type: ignore[attr-defined]
                    nsg,
                    direction="INGRESS",
                    protocol=TCP,
                    source=cidr,
                    source_type="CIDR_BLOCK",
                    tcp_options=_nsg_tcp_port(6443),
                    description=f"External kubectl and CI tooling reach the Kubernetes API from {cidr}",
                    opts=opts,
                )
            )
```

Update `NodePoolConfig` docstring:

```python
        name: Short semantic label for this pool (e.g. `"system"`, `"app"`).
            Used in tags and caller-side identification. Pulumi resource names
            use CloudSpells-owned ordinal slots.
```

Update concrete class docstrings where they describe `node_pools`:

```python
            node_pools: List of `NodePoolConfig` descriptors. Each entry
                creates a separate node pool on the cluster. The descriptor
                `name` is a semantic label; resource names use ordinal slots.
```

- [ ] **Step 4: Run focused checks**

Run:

```bash
.venv/bin/pytest tests/test_oke.py::TestOkeCluster::test_oke_node_pool_resource_names_use_ordinal_slots_not_names tests/test_oke.py::TestOkeCluster::test_kubectl_rule_resource_names_use_ordinal_slots tests/test_oke.py::TestOkeCluster::test_oke_creates_multiple_node_pools tests/test_oke.py::TestOkeCluster::test_kubectl_allowed_cidrs_stored tests/test_cs008_resource_names.py -q
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py
```

Expected: PASS. Static CS-008 test should now pass if all code fixes are complete.

- [ ] **Step 5: Commit**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py tests/test_oke.py
git commit -m "fix: use ordinal OKE repeated resource suffixes"
```

---

### Task 8: Update User-Facing Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/tutorials/compute.md`
- Modify: `docs/tutorials/oke.md`
- Modify: `docs/reference/oke-architecture.md`
- Modify: any generated/API docs only if this repository stores generated content directly; otherwise source docstrings from previous tasks are sufficient.

- [ ] **Step 1: Replace label-as-resource-name wording**

Run:

```bash
rg -n "resource name suffix|derive the resource name|used to derive|Pulumi resource name suffix" README.md docs packages/cloudspells-core/src packages/cloudspells-oci/src
```

Expected before edits: matches in compute, volume, Kubernetes, and possibly abstractions.

Edit prose so it says:

```markdown
`VolumeSpec.label` is used for lookup helpers, outputs, and tags. CloudSpells
uses internal ordinal slots for the underlying Pulumi resource names.
```

For OKE docs, use:

```markdown
`NodePoolConfig.name` is a semantic label for the pool. CloudSpells uses
internal ordinal slots for the underlying Pulumi node pool resource names.
```

- [ ] **Step 2: Document state-impact note**

Add a short note to `docs/concepts/design.md` under the naming/design rules section:

```markdown
### Repeated Child Resource Names

Repeated child resources use CloudSpells-owned ordinal suffixes such as
`vol-1`, `pool-1`, or `nsg-rule-1`. Caller labels remain useful for lookup
helpers, outputs, tags, and human descriptions, but they do not shape Pulumi
logical names. This keeps resource naming under the spell's control and avoids
turning labels into provider-name passthroughs.
```

- [ ] **Step 3: Run doc-oriented checks**

Run:

```bash
rg -n "resource name suffix|derive the resource name|used to derive|Pulumi resource name suffix" README.md docs packages/cloudspells-core/src packages/cloudspells-oci/src
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py
```

Expected: remaining matches, if any, refer to `BaseResource.create_resource_name("suffix")` or internal CloudSpells-owned suffixes, not caller labels.

- [ ] **Step 4: Commit**

```bash
git add README.md docs packages/cloudspells-core/src/cloudspells/core/abstractions/compute.py packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py packages/cloudspells-oci/src/cloudspells/providers/oci/volume.py
git commit -m "docs: clarify repeated resource naming semantics"
```

---

### Task 9: Full Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Confirm no inline f-string suffixes remain**

Run:

```bash
rg -n "create_resource_name\\(f[\"']" packages/cloudspells-oci/src/cloudspells/providers/oci packages/cloudspells-core/src
```

Expected: no output.

- [ ] **Step 2: Run focused static and behavior tests**

Run:

```bash
.venv/bin/pytest tests/test_cs008_resource_names.py tests/test_vcn.py::TestVcn::test_vcn_tier_resource_names_are_literal_suffixes tests/test_network_logging.py::TestVcnFlowLogsCreation::test_flow_log_resource_names_use_literal_suffixes tests/test_nsg.py::TestNsgRuleHelpers::test_nsg_rule_resource_name_uses_ordinal_slot_not_label tests/test_compute.py::TestComputeInstance::test_volume_resource_names_use_ordinal_slots_not_labels tests/test_oke.py::TestOkeCluster::test_oke_node_pool_resource_names_use_ordinal_slots_not_names tests/test_oke.py::TestOkeCluster::test_kubectl_rule_resource_names_use_ordinal_slots -q
```

Expected: PASS.

- [ ] **Step 3: Run full quality gate**

Run:

```bash
make check
```

Expected:

```text
Quality gate passed.
```

- [ ] **Step 4: Final commit if previous tasks were batched**

If implementation was done without the per-task commits above, commit once:

```bash
git add packages tests docs README.md
git commit -m "fix: enforce CS-008 resource naming"
```

---

## Self-Review

- Spec coverage:
  - `nsg.py:686`: covered by Task 5.
  - `compute.py:404` and `compute.py:424`: covered by Task 6.
  - `kubernetes.py:379` and `kubernetes.py:647`: covered by Task 7.
  - `network.py:791`, `network.py:874`, and `network.py:983`: covered by Task 3.
  - `network_logging.py:201`: covered by Task 4.
  - Regression prevention: covered by Task 1 and Task 9.
- Placeholder scan:
  - No task contains "TBD", "TODO", "implement later", or "similar to".
  - Each code-changing step includes concrete code or exact replacement text.
- Type consistency:
  - `ordinal_suffix(prefix: str, index: int) -> str` is imported consistently as `from ._naming import ordinal_suffix`.
  - Existing Pulumi resources still receive `str` names from `BaseResource.create_resource_name(...)`.
  - Public labels remain `str` values used by existing lookup methods and tags.
