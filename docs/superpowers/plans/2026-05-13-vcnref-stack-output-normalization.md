# VcnRef Stack Output Normalization Implementation Plan

> **Historical plan:** This document records an implementation plan and may describe pre-implementation state. It is not a current product manual; use the source code and API reference for current behavior.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `VcnRef.from_stack_reference()` fail clearly for missing or null required stack outputs, and remove the remaining optional `StackReference.get_output()` ambiguity for `drg_id`.

**Architecture:** Treat every value in the canonical CloudSpells `Vcn.export()` contract as a required output key. Values that are structurally optional, such as `drg_id`, are exported with an explicit `None` value rather than by omitting the output. `VcnRef` validates output-backed required IDs and CIDRs when Pulumi resolves them, so `Output[None]` cannot silently become a subnet, security-list, or DRG attach ID.

**Tech Stack:** Pulumi Python, `pulumi.Output`, `pulumi.StackReference`, `unittest`, existing CloudSpells OCI network tests.

---

## File Structure

- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py`
  - Always export `drg_id` from `Vcn.export()`.
  - Add small private validation helpers inside `VcnRef.__init__`.
  - Use `require_output("drg_id")` in `VcnRef.from_stack_reference()`.
  - Add a `VcnRef.require_drg_id()` accessor for consumers that need a non-null DRG ID.
- Modify: `tests/test_vcn.py`
  - Add regression coverage for `drg_id` export behavior.
  - Add regression coverage for `from_stack_reference()` using `require_output()` instead of `get_output()`.
  - Add regression coverage that `Output[None]` required IDs raise before returning `None`.
  - Add tests for `require_drg_id()`.
- Modify: `docs/how-to/vcnref.md`
  - Clarify that `drg_id` is a required output key whose value may be `None`.
- Modify: `docs/reference/vcn-architecture.md`
  - Keep the reference table aligned with the code contract.

---

### Task 1: Add Failing Regression Tests

**Files:**
- Modify: `tests/test_vcn.py`

- [ ] **Step 1: Extend `test_export_publishes_cloudspells_schema_and_profiles` to assert `drg_id` is exported without a DRG**

Replace the body of `TestVcn.test_export_publishes_cloudspells_schema_and_profiles` with:

```python
def test_export_publishes_cloudspells_schema_profiles_and_null_drg(self):
    """Vcn.export() publishes CloudSpells contract metadata and an explicit null DRG."""
    vcn = self._make_vcn(drg=False)

    with patch("pulumi.export") as mock_export:
        vcn.export()

    exports = {call.args[0]: call.args[1] for call in mock_export.call_args_list}
    self.assertEqual(exports["cloudspells_network_schema"], CLOUDSPELLS_OCI_VCN_SCHEMA)
    self.assertEqual(exports["cloudspells_network_profiles"], [NETWORK_PROFILE_BASELINE])
    self.assertIn("drg_id", exports)
    self.assertIsNone(exports["drg_id"])
```

- [ ] **Step 2: Add a focused test that `from_stack_reference()` requires `drg_id`**

First, update the existing `required_outputs` dictionary in
`test_vcnref_from_stack_reference_consumes_cloudspells_contract` by adding:

```python
"drg_id": pulumi.Output.from_input(None),
```

Then remove this line from the same test:

```python
stack_ref.get_output.return_value = None
```

Add this method to `TestVcnRef`, immediately after `test_vcnref_from_stack_reference_consumes_cloudspells_contract`:

```python
def test_vcnref_from_stack_reference_requires_explicit_drg_output(self):
    """VcnRef.from_stack_reference() treats drg_id as an explicit contract output."""
    required_outputs = {
        "vcn_id": "ocid1.vcn.oc1.phx.test",
        "cidr_block": "10.0.0.0/16",
        "public_subnet_id": "ocid1.subnet.public.test",
        "private_subnet_id": "ocid1.subnet.private.test",
        "secure_subnet_id": "ocid1.subnet.secure.test",
        "management_subnet_id": "ocid1.subnet.mgmt.test",
        "public_subnet_cidr": "10.0.192.0/19",
        "private_subnet_cidr": "10.0.0.0/17",
        "secure_subnet_cidr": "10.0.128.0/18",
        "management_subnet_cidr": "10.0.224.0/19",
        "public_security_list_id": "ocid1.sl.public.test",
        "private_security_list_id": "ocid1.sl.private.test",
        "secure_security_list_id": "ocid1.sl.secure.test",
        "management_security_list_id": "ocid1.sl.management.test",
        "cloudspells_network_schema": CLOUDSPELLS_OCI_VCN_SCHEMA,
        "cloudspells_network_profiles": [NETWORK_PROFILE_BASELINE],
        "drg_id": pulumi.Output.from_input(None),
    }
    with patch("pulumi.StackReference") as mock_stack_reference:
        stack_ref = mock_stack_reference.return_value
        stack_ref.require_output.side_effect = lambda key: required_outputs[key]

        ref = VcnRef.from_stack_reference("org/platform/prod")

    stack_ref.require_output.assert_any_call("drg_id")
    stack_ref.get_output.assert_not_called()
    self.assertIsNotNone(ref.drg_id)
    self.assertIsNone(self._resolve_output(ref.drg_id))
```

- [ ] **Step 3: Add a regression test for output-backed required ID validation**

Add this method to `TestVcnRef`, after the new `drg_id` stack-reference test:

```python
def test_vcnref_required_output_ids_reject_resolved_none(self):
    """VcnRef required IDs raise clearly if an Output resolves to None."""
    ref = self._make_ref(public_subnet_id=pulumi.Output.from_input(None))

    with self.assertRaises(ValueError) as ctx:
        self._resolve_output(ref.public_subnet.id)

    self.assertIn("public_subnet_id", str(ctx.exception))
    self.assertIn("resolved to None", str(ctx.exception))
```

- [ ] **Step 4: Add tests for a non-null DRG accessor**

Add these methods to `TestVcnRef`, after `test_vcnref_drg_id_set`:

```python
def test_vcnref_require_drg_id_accepts_present_drg(self):
    """VcnRef.require_drg_id() returns the DRG OCID when present."""
    ref = self._make_ref(drg_id=pulumi.Output.from_input("ocid1.drg.test"))

    self.assertEqual(self._resolve_output(ref.require_drg_id()), "ocid1.drg.test")

def test_vcnref_require_drg_id_rejects_missing_plain_drg(self):
    """VcnRef.require_drg_id() raises immediately when no DRG was supplied."""
    ref = self._make_ref()

    with self.assertRaises(RuntimeError) as ctx:
        ref.require_drg_id()

    self.assertIn("without a drg_id", str(ctx.exception))

def test_vcnref_require_drg_id_rejects_output_none_drg(self):
    """VcnRef.require_drg_id() raises when the DRG output resolves to None."""
    ref = self._make_ref(drg_id=pulumi.Output.from_input(None))

    with self.assertRaises(RuntimeError) as ctx:
        self._resolve_output(ref.require_drg_id())

    self.assertIn("resolved to None", str(ctx.exception))
```

- [ ] **Step 5: Run the focused tests and confirm they fail for the expected reasons**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_export_publishes_cloudspells_schema_profiles_and_null_drg tests/test_vcn.py::TestVcnRef::test_vcnref_from_stack_reference_requires_explicit_drg_output tests/test_vcn.py::TestVcnRef::test_vcnref_required_output_ids_reject_resolved_none tests/test_vcn.py::TestVcnRef::test_vcnref_require_drg_id_accepts_present_drg tests/test_vcn.py::TestVcnRef::test_vcnref_require_drg_id_rejects_missing_plain_drg tests/test_vcn.py::TestVcnRef::test_vcnref_require_drg_id_rejects_output_none_drg -q
```

Expected failures before implementation:

- `drg_id` is not present in `Vcn.export()` outputs.
- `StackReference.get_output("drg_id")` is still called.
- `public_subnet.id` resolves to `None` instead of raising.
- `VcnRef.require_drg_id()` does not exist.

---

### Task 2: Implement Output Validation and Explicit DRG Contract

**Files:**
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py`

- [ ] **Step 1: Always export `drg_id`**

In `Vcn.export()`, replace:

```python
if self.drg is not None and self.drg_attachment is not None:
    pulumi.export("drg_id", self.drg.id)
    pulumi.export("drg_attachment_id", self.drg_attachment.id)
```

with:

```python
pulumi.export("drg_id", self.drg.id if self.drg is not None else None)
if self.drg is not None and self.drg_attachment is not None:
    pulumi.export("drg_attachment_id", self.drg_attachment.id)
```

- [ ] **Step 2: Add resolved-value validation helpers inside `VcnRef.__init__`**

In `VcnRef.__init__`, replace the current `_with_schema_check` helper:

```python
def _with_schema_check(value: pulumi.Input[str]) -> pulumi.Output[str]:
    return pulumi.Output.all(pulumi.Output.from_input(value), schema_check).apply(lambda args: args[0])
```

with:

```python
def _require_resolved_value(field_name: str, value: Any) -> Any:
    if value is None:
        raise ValueError(
            f"VcnRef output '{field_name}' resolved to None. "
            "Ensure the source stack exports a non-null value for this required field."
        )
    return value

def _with_schema_check(field_name: str, value: pulumi.Input[str]) -> pulumi.Output[str]:
    if value is None:
        raise ValueError(
            f"VcnRef requires '{field_name}'. "
            "Pass a non-null value or use VcnRef.from_stack_reference() with a CloudSpells VCN stack."
        )
    return pulumi.Output.all(pulumi.Output.from_input(value), schema_check).apply(
        lambda args: _require_resolved_value(field_name, args[0])
    )
```

`Any` is already imported in this module, so no import change is needed.

- [ ] **Step 3: Pass field names through required ID and CIDR validation**

Update these assignments in `VcnRef.__init__`:

```python
self.id = _with_schema_check(vcn_id)
self.public_subnet = _SubnetRef(_with_schema_check(public_subnet_id))
self.private_subnet = _SubnetRef(_with_schema_check(private_subnet_id))
self._public_subnet_cidr: pulumi.Input[str] = public_subnet_cidr
self._private_subnet_cidr: pulumi.Input[str] = private_subnet_cidr
```

to:

```python
self.id = _with_schema_check("vcn_id", vcn_id)
self.public_subnet = _SubnetRef(_with_schema_check("public_subnet_id", public_subnet_id))
self.private_subnet = _SubnetRef(_with_schema_check("private_subnet_id", private_subnet_id))
self._public_subnet_cidr: pulumi.Input[str] = _with_schema_check("public_subnet_cidr", public_subnet_cidr)
self._private_subnet_cidr: pulumi.Input[str] = _with_schema_check("private_subnet_cidr", private_subnet_cidr)
```

- [ ] **Step 4: Pass field names through optional ref validation**

Update these optional assignments in `VcnRef.__init__`:

```python
self.public_security_list = (
    _SecurityListRef(_with_schema_check(public_security_list_id))
    if public_security_list_id is not None
    else None
)
self.private_security_list = (
    _SecurityListRef(_with_schema_check(private_security_list_id))
    if private_security_list_id is not None
    else None
)
self.secure_subnet = _SubnetRef(_with_schema_check(secure_subnet_id)) if secure_subnet_id is not None else None
self._secure_subnet_cidr: pulumi.Input[str] | None = secure_subnet_cidr
self.secure_security_list = (
    _SecurityListRef(_with_schema_check(secure_security_list_id))
    if secure_security_list_id is not None
    else None
)
self.management_subnet = (
    _SubnetRef(_with_schema_check(management_subnet_id)) if management_subnet_id is not None else None
)
self._management_subnet_cidr: pulumi.Input[str] | None = management_subnet_cidr
self.management_security_list = (
    _SecurityListRef(_with_schema_check(management_security_list_id))
    if management_security_list_id is not None
    else None
)
self.drg_id = _with_schema_check(drg_id) if drg_id is not None else None
```

to:

```python
self.public_security_list = (
    _SecurityListRef(_with_schema_check("public_security_list_id", public_security_list_id))
    if public_security_list_id is not None
    else None
)
self.private_security_list = (
    _SecurityListRef(_with_schema_check("private_security_list_id", private_security_list_id))
    if private_security_list_id is not None
    else None
)
self.secure_subnet = (
    _SubnetRef(_with_schema_check("secure_subnet_id", secure_subnet_id))
    if secure_subnet_id is not None
    else None
)
self._secure_subnet_cidr: pulumi.Input[str] | None = (
    _with_schema_check("secure_subnet_cidr", secure_subnet_cidr)
    if secure_subnet_cidr is not None
    else None
)
self.secure_security_list = (
    _SecurityListRef(_with_schema_check("secure_security_list_id", secure_security_list_id))
    if secure_security_list_id is not None
    else None
)
self.management_subnet = (
    _SubnetRef(_with_schema_check("management_subnet_id", management_subnet_id))
    if management_subnet_id is not None
    else None
)
self._management_subnet_cidr: pulumi.Input[str] | None = (
    _with_schema_check("management_subnet_cidr", management_subnet_cidr)
    if management_subnet_cidr is not None
    else None
)
self.management_security_list = (
    _SecurityListRef(_with_schema_check("management_security_list_id", management_security_list_id))
    if management_security_list_id is not None
    else None
)
self.drg_id = pulumi.Output.from_input(drg_id) if drg_id is not None else None
```

Keep `drg_id` as nullable because an explicit exported `None` is valid. Non-null use is enforced by `require_drg_id()`.

- [ ] **Step 5: Switch `from_stack_reference()` to require the explicit `drg_id` output**

Replace:

```python
drg_id=ref.get_output("drg_id"),
```

with:

```python
drg_id=ref.require_output("drg_id"),
```

- [ ] **Step 6: Add `VcnRef.require_drg_id()`**

Add this method to `VcnRef`, immediately before `get_private_subnet_cidr()`:

```python
def require_drg_id(self) -> pulumi.Output[str]:
    """Return the referenced DRG OCID, raising if the VCN has no DRG.

    Returns:
        The DRG OCID as a Pulumi output.

    Raises:
        RuntimeError: If this `VcnRef` was constructed without `drg_id`, or
            if an output-backed `drg_id` resolves to `None`.
    """
    if self.drg_id is None:
        raise RuntimeError(
            "VcnRef was constructed without a drg_id. "
            "Enable DRG on the source VCN stack before attaching DRG-dependent resources."
        )

    def _require_drg_id(value: str | None) -> str:
        if value is None:
            raise RuntimeError(
                "VcnRef drg_id resolved to None. "
                "Enable DRG on the source VCN stack before attaching DRG-dependent resources."
            )
        return value

    return pulumi.Output.from_input(self.drg_id).apply(_require_drg_id)
```

- [ ] **Step 7: Run the focused tests from Task 1**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_export_publishes_cloudspells_schema_profiles_and_null_drg tests/test_vcn.py::TestVcnRef::test_vcnref_from_stack_reference_requires_explicit_drg_output tests/test_vcn.py::TestVcnRef::test_vcnref_required_output_ids_reject_resolved_none tests/test_vcn.py::TestVcnRef::test_vcnref_require_drg_id_accepts_present_drg tests/test_vcn.py::TestVcnRef::test_vcnref_require_drg_id_rejects_missing_plain_drg tests/test_vcn.py::TestVcnRef::test_vcnref_require_drg_id_rejects_output_none_drg -q
```

Expected: all selected tests pass.

---

### Task 3: Update Documentation

**Files:**
- Modify: `docs/how-to/vcnref.md`
- Modify: `docs/reference/vcn-architecture.md`

- [ ] **Step 1: Update `docs/how-to/vcnref.md` DRG wording**

Replace:

```markdown
| `drg_id` | DRG attach points (optional — `None` when no DRG) |
```

with:

```markdown
| `drg_id` | DRG attach points (required output key; value is `None` when no DRG is attached) |
```

Replace:

```markdown
All required outputs must exist in the source stack (except `drg_id`, which is `None` when no DRG is attached) or `VcnRef.from_stack_reference()` will fail. All are exported automatically by `vcn.export()`.
```

with:

```markdown
All listed output keys must exist in the source stack or `VcnRef.from_stack_reference()` will fail. `drg_id` is exported explicitly with value `None` when no DRG is attached. All are exported automatically by `vcn.export()`.
```

- [ ] **Step 2: Update `docs/reference/vcn-architecture.md` DRG wording**

Replace:

```markdown
| `drg_id` | `str \| None` | DRG OCID (optional — `None` when no DRG is attached) |
```

with:

```markdown
| `drg_id` | `str \| None` | DRG OCID; output key is always exported, value is `None` when no DRG is attached |
```

- [ ] **Step 3: Run doc grep to confirm no stale optional-output wording remains**

Run:

```bash
rg -n "drg_id.*optional|except `drg_id`|get_output\\(\"drg_id\"\\)" docs packages/cloudspells-oci/src/cloudspells/providers/oci/network.py
```

Use this narrower command if the plan document itself appears in the results:

```bash
rg -n "drg_id.*optional|except `drg_id`|get_output\\(\"drg_id\"\\)" docs/how-to docs/reference packages/cloudspells-oci/src/cloudspells/providers/oci/network.py
```

Expected: no matches for stale `drg_id` optional-key wording or `get_output("drg_id")` in product docs or source.

---

### Task 4: Run Quality Gates

**Files:**
- No source edits in this task.

- [ ] **Step 1: Run focused VCN tests**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py::TestVcn tests/test_vcn.py::TestVcnRef -q
```

Expected: all VCN and VCNRef tests pass.

- [ ] **Step 2: Run the file-level check**

Run:

```bash
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/network.py
```

Expected: lint/type/test checks for `network.py` pass.

- [ ] **Step 3: Run the full CloudSpells gate**

Run:

```bash
make check
```

Expected: full quality gate passes.

- [ ] **Step 4: Review the final diff**

Run:

```bash
git diff -- packages/cloudspells-oci/src/cloudspells/providers/oci/network.py tests/test_vcn.py docs/how-to/vcnref.md docs/reference/vcn-architecture.md
```

Expected:

- `Vcn.export()` always exports `drg_id`.
- `VcnRef.from_stack_reference()` no longer calls `get_output()`.
- `Output[None]` required IDs raise a clear `ValueError`.
- `require_drg_id()` is available for consumers that need a non-null DRG.
- Docs describe `drg_id` as a required output key with nullable value.

---

## Self-Review

- Spec coverage: The plan covers the stale review item by preserving the existing `require_output()` behavior for topology-defining outputs and fixing the remaining `get_output("drg_id")` ambiguity.
- Placeholder scan: No `TBD`, generic "add tests", or unspecified implementation steps remain.
- Type consistency: `drg_id` remains nullable on the `VcnRef` object, while `require_drg_id()` returns `pulumi.Output[str]` for consumers that require a concrete DRG OCID.
