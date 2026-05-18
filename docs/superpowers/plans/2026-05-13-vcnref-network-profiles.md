# VcnRef Network Profiles Implementation Plan

> **Historical plan:** This document records an implementation plan and may describe pre-implementation state. It is not a current product manual; use the source code and API reference for current behavior.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `VcnRef` a strict reference to CloudSpells-standard OCI VCNs and allow OKE with `VcnRef` only when the source VCN stack exports the exact OKE network profile.

**Architecture:** Add CloudSpells network schema/profile metadata, export it from `Vcn.export()`, and make `VcnRef` validate that referenced networks are CloudSpells VCNs. Move OKE subnet security-list requirements into a reusable network profile helper; live `Vcn` installs the profile, while `VcnRef` only verifies the source stack already exported it.

**Tech Stack:** Python 3.11+, Pulumi Python, `pulumi_oci`, `pytest`, `ruff`, `pyright`, CloudSpells OCI provider.

---

## File Structure

- Create `packages/cloudspells-oci/src/cloudspells/providers/oci/_network_profiles.py`
  - Owns CloudSpells OCI VCN schema/profile constants.
  - Owns deterministic OKE profile IDs.
  - Owns OKE `SecurityRules` generation shared by `Vcn` and `OkeCluster`.
- Modify `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py`
  - Add schema/profile state to `Vcn`.
  - Export schema/profile metadata.
  - Require schema/profile metadata in `VcnRef`.
  - Add `Vcn.enable_oke_profile()` and `VcnRef.require_network_profile()`.
- Modify `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py`
  - Stop calling `vcn.add_security_rules(...)` directly from OKE.
  - For live `Vcn`, call `vcn.enable_oke_profile(...)`.
  - For `VcnRef`, require the exact OKE profile ID.
- Modify `tests/test_vcn.py`
  - Cover schema/profile export and `VcnRef` validation.
- Modify `tests/test_oke.py`
  - Cover live `Vcn` profile installation.
  - Cover `VcnRef` rejection when OKE profile is missing.
  - Cover `VcnRef` success when OKE profile is exported.
- Modify docs:
  - `docs/how-to/vcnref.md`
  - `docs/reference/vcn-architecture.md`
  - `docs/reference/oke-architecture.md`
  - `docs/tutorials/oke.md`

---

### Task 1: Add Failing VCN Profile Tests

**Files:**
- Modify: `tests/test_vcn.py`

- [ ] **Step 1: Add imports for new constants**

Add these imports near the existing OCI network imports:

```python
from cloudspells.providers.oci._network_profiles import (
    CLOUDSPELLS_OCI_VCN_SCHEMA,
    NETWORK_PROFILE_BASELINE,
    oke_profile_id,
)
```

- [ ] **Step 2: Update `TestVcnRef._make_ref()` to describe a CloudSpells-standard VCN**

Change the defaults in `tests/test_vcn.py`:

```python
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
    cloudspells_network_schema=CLOUDSPELLS_OCI_VCN_SCHEMA,
    network_profiles=[NETWORK_PROFILE_BASELINE],
)
```

- [ ] **Step 3: Add test that `Vcn.export()` publishes schema and profiles**

Add this test to `TestVcn`:

```python
def test_export_publishes_cloudspells_schema_and_profiles(self):
    """Vcn.export() publishes the CloudSpells network contract metadata."""
    vcn = self._make_vcn()

    with patch("pulumi.export") as mock_export:
        vcn.export()

    exports = {call.args[0]: call.args[1] for call in mock_export.call_args_list}
    self.assertEqual(exports["cloudspells_network_schema"], CLOUDSPELLS_OCI_VCN_SCHEMA)
    self.assertIn(NETWORK_PROFILE_BASELINE, exports["cloudspells_network_profiles"])
```

- [ ] **Step 4: Add tests that `VcnRef` requires the CloudSpells schema**

Add these tests to `TestVcnRef`:

```python
def test_vcnref_requires_cloudspells_schema(self):
    """VcnRef rejects direct references that do not assert the CloudSpells VCN schema."""
    with self.assertRaises(ValueError) as ctx:
        VcnRef(
            vcn_id="ocid1.vcn.test",
            public_subnet_id="ocid1.subnet.pub.test",
            private_subnet_id="ocid1.subnet.priv.test",
            public_subnet_cidr="10.0.0.0/19",
            private_subnet_cidr="10.0.0.0/17",
            cidr_block="10.0.0.0/16",
        )
    self.assertIn("CloudSpells OCI VCN schema", str(ctx.exception))

def test_vcnref_rejects_wrong_cloudspells_schema(self):
    """VcnRef rejects references whose schema marker is not the supported CloudSpells VCN schema."""
    with self.assertRaises(ValueError) as ctx:
        self._make_ref(cloudspells_network_schema="cloudspells.oci.vcn/v0")
    self.assertIn("Unsupported CloudSpells OCI VCN schema", str(ctx.exception))
```

- [ ] **Step 5: Add tests for required network profiles**

Add these tests to `TestVcnRef`:

```python
def test_vcnref_require_network_profile_accepts_existing_profile(self):
    """VcnRef.require_network_profile() accepts a profile exported by the source VCN."""
    profile_id = oke_profile_id(["203.0.113.0/24"])
    ref = self._make_ref(network_profiles=[NETWORK_PROFILE_BASELINE, profile_id])

    check = ref.require_network_profile(profile_id)

    self.assertEqual(check, profile_id)

def test_vcnref_require_network_profile_rejects_missing_profile(self):
    """VcnRef.require_network_profile() rejects profiles not exported by the source VCN."""
    profile_id = oke_profile_id(["203.0.113.0/24"])
    ref = self._make_ref(network_profiles=[NETWORK_PROFILE_BASELINE])

    with self.assertRaises(RuntimeError) as ctx:
        ref.require_network_profile(profile_id)

    self.assertIn("source CloudSpells VCN stack does not export required network profile", str(ctx.exception))
```

- [ ] **Step 6: Run the focused failing tests**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_export_publishes_cloudspells_schema_and_profiles tests/test_vcn.py::TestVcnRef -q
```

Expected: FAIL because `_network_profiles.py`, schema export, constructor arguments, and `require_network_profile()` do not exist yet.

- [ ] **Step 7: Commit failing tests**

```bash
git add tests/test_vcn.py
git commit -m "test: define CloudSpells VCN reference profile contract"
```

---

### Task 2: Implement CloudSpells VCN Profile Primitives

**Files:**
- Create: `packages/cloudspells-oci/src/cloudspells/providers/oci/_network_profiles.py`
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/network.py`
- Test: `tests/test_vcn.py`

- [ ] **Step 1: Create `_network_profiles.py`**

Create `packages/cloudspells-oci/src/cloudspells/providers/oci/_network_profiles.py` with:

```python
"""CloudSpells OCI VCN schema and network profile helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import pulumi
from cloudspells.core.abstractions.network import (
    CLOUD_SERVICES,
    INTERNET,
    EgressRule,
    IngressRule,
    SecurityRules,
)

CLOUDSPELLS_OCI_VCN_SCHEMA = "cloudspells.oci.vcn/v1"
"""Schema marker exported by CloudSpells-managed OCI VCN stacks."""

NETWORK_PROFILE_BASELINE = "cloudspells.oci.vcn.profile/base/v1"
"""Baseline profile present on every CloudSpells-managed OCI VCN."""


def normalize_cidrs(cidrs: Sequence[str] | None) -> tuple[str, ...]:
    """Return a stable, duplicate-free CIDR tuple.

    Args:
        cidrs: CIDR list supplied by the caller, or `None`.

    Returns:
        Sorted tuple with duplicate CIDRs removed.
    """
    return tuple(sorted(dict.fromkeys(cidrs or [])))


def oke_profile_id(kubectl_allowed_cidrs: Sequence[str] | None) -> str:
    """Return the deterministic CloudSpells OKE network profile ID.

    Args:
        kubectl_allowed_cidrs: CIDRs allowed to reach the Kubernetes API on
            TCP 6443. `None` and `[]` are equivalent.

    Returns:
        Stable profile ID suitable for stack export and cross-stack checks.
    """
    cidrs = normalize_cidrs(kubectl_allowed_cidrs)
    if not cidrs:
        return "cloudspells.oci.vcn.profile/oke/v1/kubectl:none"
    digest = hashlib.sha256("\n".join(cidrs).encode("utf-8")).hexdigest()[:16]
    return f"cloudspells.oci.vcn.profile/oke/v1/kubectl:{digest}"


def require_cloudspells_schema(schema: Any) -> str:
    """Validate a CloudSpells OCI VCN schema marker.

    Args:
        schema: Value exported by the source stack.

    Returns:
        The supported schema string.

    Raises:
        RuntimeError: If the source stack did not export the schema marker.
        ValueError: If the schema marker is present but unsupported.
    """
    if schema is None:
        raise RuntimeError(
            "VcnRef requires a CloudSpells OCI VCN schema export. "
            "Deploy the source VCN with Vcn.export() before referencing it."
        )
    if schema != CLOUDSPELLS_OCI_VCN_SCHEMA:
        raise ValueError(
            f"Unsupported CloudSpells OCI VCN schema: {schema!r}. "
            f"Expected {CLOUDSPELLS_OCI_VCN_SCHEMA!r}."
        )
    return CLOUDSPELLS_OCI_VCN_SCHEMA


def require_profile_id(profile_id: str, profiles: Any) -> str:
    """Validate that a source stack exported `profile_id`.

    Args:
        profile_id: Required profile ID.
        profiles: Exported profile list from the source CloudSpells VCN stack.

    Returns:
        The required profile ID when present.

    Raises:
        RuntimeError: If the profile list is missing or does not contain the
            required profile.
    """
    if profiles is None:
        raise RuntimeError(
            "VcnRef source CloudSpells VCN stack does not export network profiles. "
            "Deploy the source VCN with Vcn.export() before referencing it."
        )
    profile_set = {str(profile) for profile in profiles}
    if profile_id not in profile_set:
        raise RuntimeError(
            "VcnRef source CloudSpells VCN stack does not export required network profile "
            f"{profile_id!r}. Enable the profile in the source VCN stack, run pulumi up "
            "there, then redeploy this stack."
        )
    return profile_id


def oke_security_rules(
    public_subnet_cidr: pulumi.Input[str],
    private_subnet_cidr: pulumi.Input[str],
    kubectl_allowed_cidrs: Sequence[str] | None,
) -> SecurityRules:
    """Build subnet-level security rules required by OKE.

    Args:
        public_subnet_cidr: CIDR of the public subnet tier.
        private_subnet_cidr: CIDR of the private subnet tier.
        kubectl_allowed_cidrs: CIDRs allowed to reach the Kubernetes API on
            TCP 6443. `None` and `[]` mean no external kubectl security-list
            ingress is installed.

    Returns:
        Cloud-neutral security rules for the OKE network profile.
    """

    def tcp_ingress(source: pulumi.Input[str], port_min: int, port_max: int, description: str) -> IngressRule:
        return IngressRule(
            protocol="tcp",
            source=source,
            port_min=port_min,
            port_max=port_max,
            description=description,
        )

    def all_ingress(source: pulumi.Input[str], description: str) -> IngressRule:
        return IngressRule(protocol="all", source=source, description=description)

    def tcp_egress(
        destination: pulumi.Input[str],
        port_min: int | None,
        port_max: int | None,
        description: str,
    ) -> EgressRule:
        return EgressRule(
            protocol="tcp",
            destination=destination,
            port_min=port_min,
            port_max=port_max,
            description=description,
        )

    def all_egress(destination: pulumi.Input[str], description: str) -> EgressRule:
        return EgressRule(protocol="all", destination=destination, description=description)

    public_ingress = [
        tcp_ingress(
            private_subnet_cidr,
            6443,
            6443,
            "Workers and pods communicate with Kubernetes API server for cluster operations and service discovery",
        ),
        tcp_ingress(
            private_subnet_cidr,
            12250,
            12250,
            "Workers and pods communicate with Kubernetes control plane for internal cluster operations",
        ),
        tcp_ingress(
            INTERNET,
            443,
            443,
            "Load Balancer receives HTTPS traffic from internet for public web applications and APIs",
        ),
        tcp_ingress(
            INTERNET,
            80,
            80,
            "Load Balancer receives HTTP traffic from internet for public applications",
        ),
    ]
    for cidr in normalize_cidrs(kubectl_allowed_cidrs):
        public_ingress.append(
            tcp_ingress(
                cidr,
                6443,
                6443,
                f"Allow kubectl access to Kubernetes API from {cidr}",
            )
        )

    return SecurityRules(
        public_ingress=public_ingress,
        public_egress=[
            tcp_egress(
                CLOUD_SERVICES,
                None,
                None,
                "Control plane communicates with OCI services for cluster management and telemetry",
            ),
            tcp_egress(
                private_subnet_cidr,
                10250,
                10250,
                "Control plane manages worker nodes via kubelet for pod operations and health monitoring",
            ),
            tcp_egress(
                private_subnet_cidr,
                30000,
                32767,
                "Load Balancer forwards traffic to worker nodes via NodePort for Kubernetes service routing",
            ),
            tcp_egress(
                private_subnet_cidr,
                10256,
                10256,
                "Load Balancer checks worker node health via kube-proxy",
            ),
            all_egress(
                private_subnet_cidr,
                "Control plane reaches pods on arbitrary ports for webhooks, admission controllers, and metrics",
            ),
        ],
        private_ingress=[
            tcp_ingress(
                public_subnet_cidr,
                10250,
                10250,
                "Control plane manages pods on worker nodes via kubelet for commands, logs, and health monitoring",
            ),
            tcp_ingress(
                public_subnet_cidr,
                30000,
                32767,
                "Load Balancer forwards traffic to worker nodes via NodePort to reach Kubernetes services",
            ),
            tcp_ingress(
                public_subnet_cidr,
                10256,
                10256,
                "Load Balancer verifies worker node health via kube-proxy endpoint before routing traffic",
            ),
            all_ingress(
                public_subnet_cidr,
                "Control plane reaches pods on arbitrary ports for webhooks and admission controllers",
            ),
        ],
        private_egress=[
            tcp_egress(
                CLOUD_SERVICES,
                None,
                None,
                "Workers and pods communicate with OCI services for container images, logging, and monitoring",
            ),
            tcp_egress(
                public_subnet_cidr,
                6443,
                6443,
                "Workers and pods communicate with Kubernetes API to register, report status, and access resources",
            ),
            tcp_egress(
                public_subnet_cidr,
                12250,
                12250,
                "Workers and pods communicate with control plane for internal cluster operations",
            ),
            tcp_egress(
                INTERNET,
                443,
                443,
                "Workers pull container images and pods call external APIs via HTTPS",
            ),
            tcp_egress(
                INTERNET,
                80,
                80,
                "Workers pull container images from HTTP registries and access OCI pre-authenticated URLs",
            ),
        ],
    )
```

- [ ] **Step 2: Add imports to `network.py`**

Add these imports near the other local imports:

```python
from ._network_profiles import (
    CLOUDSPELLS_OCI_VCN_SCHEMA,
    NETWORK_PROFILE_BASELINE,
    oke_profile_id,
    oke_security_rules,
    require_cloudspells_schema,
    require_profile_id,
)
```

Add `Sequence` to the standard imports:

```python
from collections.abc import Sequence
```

- [ ] **Step 3: Add profile state and accessors to `Vcn`**

In `Vcn.__init__`, after `_applied_ambient_rule_fingerprints` is initialised, add:

```python
self._network_profiles: set[str] = {NETWORK_PROFILE_BASELINE}
```

Add these methods to `Vcn` before `export()`:

```python
def has_network_profile(self, profile_id: str) -> bool:
    """Return whether this VCN has registered `profile_id`.

    Args:
        profile_id: CloudSpells network profile ID.

    Returns:
        `True` when the profile is registered on this VCN.
    """
    return profile_id in self._network_profiles

def enable_oke_profile(self, kubectl_allowed_cidrs: Sequence[str] | None = None) -> str:
    """Register OKE subnet security rules and mark the OKE network profile.

    Args:
        kubectl_allowed_cidrs: CIDRs allowed to reach the Kubernetes API on
            TCP 6443. `None` and `[]` install no external kubectl ingress.

    Returns:
        The registered OKE network profile ID.

    Raises:
        RuntimeError: If called after `finalize_network()` and the profile was
            not already registered.
    """
    profile_id = oke_profile_id(kubectl_allowed_cidrs)
    if profile_id in self._network_profiles:
        return profile_id
    self.add_security_rules(
        oke_security_rules(
            public_subnet_cidr=self.get_public_subnet_cidr(),
            private_subnet_cidr=self.get_private_subnet_cidr(),
            kubectl_allowed_cidrs=kubectl_allowed_cidrs,
        )
    )
    self._network_profiles.add(profile_id)
    return profile_id
```

- [ ] **Step 4: Export schema and profiles from `Vcn.export()`**

At the start of the export list in `Vcn.export()`, after `pulumi.export("cidr_block", self.cidr_block)`, add:

```python
pulumi.export("cloudspells_network_schema", CLOUDSPELLS_OCI_VCN_SCHEMA)
pulumi.export("cloudspells_network_profiles", sorted(self._network_profiles))
```

- [ ] **Step 5: Extend `VcnRef.__init__`**

Add constructor parameters after `cidr_block`:

```python
cloudspells_network_schema: pulumi.Input[str] | None = None,
network_profiles: pulumi.Input[Sequence[str]] | None = None,
```

After `cidr_block` validation, add:

```python
if cloudspells_network_schema is None:
    raise ValueError(
        "VcnRef requires the CloudSpells OCI VCN schema marker. "
        "Use Vcn.export() in the source stack and VcnRef.from_stack_reference() here."
    )
if isinstance(cloudspells_network_schema, str):
    require_cloudspells_schema(cloudspells_network_schema)
self.cloudspells_network_schema = pulumi.Output.from_input(cloudspells_network_schema)
self.network_profiles = pulumi.Output.from_input(network_profiles or [])
self._network_profiles_plain: set[str] | None = (
    {str(profile) for profile in network_profiles}
    if isinstance(network_profiles, Sequence) and not isinstance(network_profiles, str)
    else None
)
self._profile_checks: list[pulumi.Output[str]] = [
    self.cloudspells_network_schema.apply(require_cloudspells_schema)
]
```

Add attributes to the class body:

```python
cloudspells_network_schema: pulumi.Output[str]
network_profiles: pulumi.Output[Sequence[str]]
_network_profiles_plain: set[str] | None
_profile_checks: list[pulumi.Output[str]]
```

- [ ] **Step 6: Add `VcnRef.require_network_profile()`**

Add this method before `add_security_rules()`:

```python
def require_network_profile(self, profile_id: str) -> str | pulumi.Output[str]:
    """Require a network profile exported by the source CloudSpells VCN stack.

    Args:
        profile_id: Required CloudSpells network profile ID.

    Returns:
        The profile ID for plain profile lists, or an output-backed profile
        check for stack-reference profile lists.

    Raises:
        RuntimeError: If a plain profile list is present and does not contain
            the required profile.
    """
    if self._network_profiles_plain is not None:
        return require_profile_id(profile_id, self._network_profiles_plain)
    check = self.network_profiles.apply(lambda profiles: require_profile_id(profile_id, profiles))
    self._profile_checks.append(check)
    return check

def get_profile_checks(self) -> list[pulumi.Output[str]]:
    """Return output-backed profile checks requested by consuming spells.

    Returns:
        Profile check outputs that consuming component resources should
        register so Pulumi evaluates stack-reference validation.
    """
    return list(self._profile_checks)
```

- [ ] **Step 7: Update `VcnRef.from_stack_reference()` to consume the CloudSpells contract**

Change required outputs to use `require_output()` and pass schema/profile outputs:

```python
ref = pulumi.StackReference(stack_name)
return cls(
    vcn_id=ref.require_output("vcn_id"),
    public_subnet_id=ref.require_output("public_subnet_id"),
    private_subnet_id=ref.require_output("private_subnet_id"),
    secure_subnet_id=ref.require_output("secure_subnet_id"),
    public_subnet_cidr=ref.require_output("public_subnet_cidr"),
    private_subnet_cidr=ref.require_output("private_subnet_cidr"),
    secure_subnet_cidr=ref.require_output("secure_subnet_cidr"),
    cidr_block=ref.require_output("cidr_block"),
    cloudspells_network_schema=ref.require_output("cloudspells_network_schema"),
    network_profiles=ref.require_output("cloudspells_network_profiles"),
    public_security_list_id=ref.require_output("public_security_list_id"),
    private_security_list_id=ref.require_output("private_security_list_id"),
    secure_security_list_id=ref.require_output("secure_security_list_id"),
    management_subnet_id=ref.require_output("management_subnet_id"),
    management_subnet_cidr=ref.require_output("management_subnet_cidr"),
    management_security_list_id=ref.require_output("management_security_list_id"),
    drg_id=ref.get_output("drg_id"),
)
```

- [ ] **Step 8: Run focused VCN tests**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_export_publishes_cloudspells_schema_and_profiles tests/test_vcn.py::TestVcnRef -q
```

Expected: PASS.

- [ ] **Step 9: Run file quality gate**

Run:

```bash
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/network.py
```

Expected: PASS.

- [ ] **Step 10: Commit VCN profile primitives**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/_network_profiles.py packages/cloudspells-oci/src/cloudspells/providers/oci/network.py tests/test_vcn.py
git commit -m "feat: add CloudSpells VCN network profiles"
```

---

### Task 3: Make OKE Use Network Profiles Instead of Mutating VcnRef

**Files:**
- Modify: `packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py`
- Modify: `tests/test_oke.py`

- [ ] **Step 1: Add OKE profile imports to `tests/test_oke.py`**

Add:

```python
from cloudspells.providers.oci._network_profiles import (
    CLOUDSPELLS_OCI_VCN_SCHEMA,
    NETWORK_PROFILE_BASELINE,
    oke_profile_id,
)
```

- [ ] **Step 2: Update `_make_vcn_ref()` in `tests/test_oke.py`**

Add schema/profile defaults:

```python
cloudspells_network_schema=CLOUDSPELLS_OCI_VCN_SCHEMA,
network_profiles=[NETWORK_PROFILE_BASELINE],
```

- [ ] **Step 3: Replace the current OKE+VcnRef rejection test**

Change the test name and body:

```python
def test_oke_rejects_vcn_ref_without_oke_network_profile(self):
    """OkeCluster+VcnRef raises when the source VCN lacks the exact OKE profile."""
    vcn_ref = _make_vcn_ref()

    with self.assertRaises(RuntimeError) as ctx:
        OkeCluster(
            name="test-vcnref",
            compartment_id="ocid1.compartment.test",
            vcn=vcn_ref,
            kubernetes_version="v1.28.2",
            node_pools=[_DEFAULT_POOL],
            kubectl_allowed_cidrs=["10.0.0.0/8"],
        )

    self.assertIn("required network profile", str(ctx.exception))
```

- [ ] **Step 4: Add test that OKE accepts a VcnRef with the exact profile**

Add:

```python
def test_oke_accepts_vcn_ref_with_oke_network_profile(self):
    """OkeCluster can deploy against a VcnRef when the source VCN exports the exact OKE profile."""
    profile_id = oke_profile_id(["10.0.0.0/8"])
    vcn_ref = _make_vcn_ref(network_profiles=[NETWORK_PROFILE_BASELINE, profile_id])

    oke = OkeCluster(
        name="test-vcnref-profile",
        compartment_id="ocid1.compartment.test",
        vcn=vcn_ref,
        kubernetes_version="v1.28.2",
        node_pools=[_DEFAULT_POOL],
        kubectl_allowed_cidrs=["10.0.0.0/8"],
    )

    self.assertIs(oke.vcn, vcn_ref)
```

- [ ] **Step 5: Add test that live OKE registers the profile on `Vcn`**

Add:

```python
def test_oke_registers_oke_network_profile_on_live_vcn(self):
    """OkeCluster registers the exact OKE network profile on live Vcn."""
    vcn = self._make_vcn()
    cidrs = ["10.0.0.0/8"]

    OkeCluster(
        name="test-live-profile",
        compartment_id="ocid1.compartment.test",
        vcn=vcn,
        kubernetes_version="v1.28.2",
        node_pools=[_DEFAULT_POOL],
        kubectl_allowed_cidrs=cidrs,
    )

    self.assertTrue(vcn.has_network_profile(oke_profile_id(cidrs)))
```

- [ ] **Step 6: Run focused failing OKE tests**

Run:

```bash
.venv/bin/pytest tests/test_oke.py::TestOkeCluster::test_oke_rejects_vcn_ref_without_oke_network_profile tests/test_oke.py::TestOkeCluster::test_oke_accepts_vcn_ref_with_oke_network_profile tests/test_oke.py::TestOkeCluster::test_oke_registers_oke_network_profile_on_live_vcn -q
```

Expected: FAIL until `kubernetes.py` uses network profiles.

- [ ] **Step 7: Update imports in `kubernetes.py`**

Remove unused imports made obsolete by deleting OKE local rule construction:

```python
from cloudspells.core.abstractions.network import CLOUD_SERVICES, EgressRule, IngressRule, SecurityRules
```

Replace them with:

```python
from ._network_profiles import oke_profile_id
```

Keep imports that are still used elsewhere in the file.

- [ ] **Step 8: Replace OKE security-list registration in `_build_cluster()`**

Replace:

```python
# Layer 1: subnet-level security list rules
self._add_oke_security_lists_rules()
self.vcn.finalize_network()
```

with:

```python
# Layer 1: subnet-level security profile
network_profile_check: str | pulumi.Output[str] | None = None
if isinstance(self.vcn, Vcn):
    self.vcn.enable_oke_profile(self.kubectl_allowed_cidrs)
else:
    network_profile_check = self.vcn.require_network_profile(
        oke_profile_id(self.kubectl_allowed_cidrs)
    )
self.vcn.finalize_network()
```

- [ ] **Step 9: Register profile checks as OKE component outputs**

Replace the existing `self.register_outputs({...})` block in `_build_cluster()` with:

```python
outputs: dict[str, pulumi.Output[str] | str] = {
    "cluster_id": self.cluster.id,
    "api_nsg_id": self.api_nsg.id,
    "lb_nsg_id": self.lb_nsg.id,
    "worker_nsg_id": self.worker_nsg.id,
    "pod_nsg_id": self.pod_nsg.id,
}
if network_profile_check is not None:
    outputs["network_profile_check"] = network_profile_check

self.register_outputs(outputs)  # type: ignore[attr-defined]
```

- [ ] **Step 10: Delete `_add_oke_security_lists_rules()` from `kubernetes.py`**

Remove the entire private method `_add_oke_security_lists_rules()`. Its rule construction now lives in `_network_profiles.py` and is invoked through `Vcn.enable_oke_profile()`.

- [ ] **Step 11: Run focused OKE tests**

Run:

```bash
.venv/bin/pytest tests/test_oke.py::TestOkeCluster::test_oke_rejects_vcn_ref_without_oke_network_profile tests/test_oke.py::TestOkeCluster::test_oke_accepts_vcn_ref_with_oke_network_profile tests/test_oke.py::TestOkeCluster::test_oke_registers_oke_network_profile_on_live_vcn -q
```

Expected: PASS.

- [ ] **Step 12: Run Kubernetes file gate**

Run:

```bash
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py
```

Expected: PASS.

- [ ] **Step 13: Commit OKE profile integration**

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py tests/test_oke.py
git commit -m "fix: gate OKE VcnRef usage on exported network profile"
```

---

### Task 4: Update Documentation and Examples

**Files:**
- Modify: `docs/how-to/vcnref.md`
- Modify: `docs/reference/vcn-architecture.md`
- Modify: `docs/reference/oke-architecture.md`
- Modify: `docs/tutorials/oke.md`

- [ ] **Step 1: Update `docs/how-to/vcnref.md` contract wording**

Add this paragraph after the opening description:

```markdown
`VcnRef` is not a generic OCI VCN import mechanism. It only references VCNs created by CloudSpells and exported with the CloudSpells OCI VCN schema. The source stack must publish the standard `Vcn.export()` outputs, including `cloudspells_network_schema` and `cloudspells_network_profiles`.
```

- [ ] **Step 2: Update the `VcnRef` capability table**

Change the table rows to include:

```markdown
| Accepts arbitrary OCI VCNs | No | No |
| Validates CloudSpells schema | Owns schema | Requires exported schema |
| Network profiles | Installs and exports profiles | Requires pre-exported profiles |
```

- [ ] **Step 3: Add OKE profile workflow to `docs/how-to/vcnref.md`**

Add:

```markdown
## OKE with VcnRef

OKE requires subnet-level security-list rules. Because `VcnRef` is read-only, those rules must be installed in the source VCN stack before the OKE stack references it:

```python
# platform/vcn/__main__.py
vcn = Vcn(name="platform", compartment_id=compartment_id)
vcn.enable_oke_profile(kubectl_allowed_cidrs=["203.0.113.0/24"])
vcn.export()
```

```python
# services/oke/__main__.py
vcn = VcnRef.from_stack_reference("org/platform/prod")
cluster = OkeCluster(
    name="app",
    compartment_id=compartment_id,
    vcn=vcn,
    kubernetes_version="v1.32.1",
    node_pools=[pool],
    kubectl_allowed_cidrs=["203.0.113.0/24"],
)
```

The `kubectl_allowed_cidrs` list must match between the source VCN profile and the OKE stack. If it does not match, `OkeCluster` fails with a required network profile error.
```

- [ ] **Step 4: Update `docs/reference/vcn-architecture.md`**

In the `VcnRef` section, replace “only supported for VCNs created by CloudSpells” with:

```markdown
`VcnRef` is only supported for VCNs created by CloudSpells and exported with `Vcn.export()`. The source stack must publish `cloudspells_network_schema="cloudspells.oci.vcn/v1"` and a `cloudspells_network_profiles` list. These outputs are the compatibility contract between the network-owning stack and service stacks.
```

- [ ] **Step 5: Update OKE docs**

In both `docs/reference/oke-architecture.md` and `docs/tutorials/oke.md`, add:

```markdown
When OKE uses a live `Vcn`, `OkeCluster` installs the OKE network profile before `finalize_network()`. When OKE uses `VcnRef`, it does not mutate the referenced VCN; it requires the source stack to have exported the exact OKE profile first. Enable that in the VCN stack with `vcn.enable_oke_profile(kubectl_allowed_cidrs=[...])`.
```

- [ ] **Step 6: Run doc spell checks**

Run:

```bash
make check-file FILE=docs/how-to/vcnref.md
make check-file FILE=docs/reference/vcn-architecture.md
make check-file FILE=docs/reference/oke-architecture.md
make check-file FILE=docs/tutorials/oke.md
```

Expected: PASS for each file.

- [ ] **Step 7: Commit docs**

```bash
git add docs/how-to/vcnref.md docs/reference/vcn-architecture.md docs/reference/oke-architecture.md docs/tutorials/oke.md
git commit -m "docs: clarify CloudSpells VcnRef network profiles"
```

---

### Task 5: Run Full Verification

**Files:**
- Verify all modified code and docs.

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
.venv/bin/pytest tests/test_vcn.py tests/test_oke.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full quality gate**

Run:

```bash
make check
```

Expected: PASS. Ruff, format check, Pyright, pytest, coverage, and Vulture must all complete successfully.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git diff --stat
git diff -- packages/cloudspells-oci/src/cloudspells/providers/oci/network.py packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py packages/cloudspells-oci/src/cloudspells/providers/oci/_network_profiles.py
```

Expected: Diff shows only schema/profile support, OKE profile gating, tests, and documentation updates.

- [ ] **Step 4: Commit verification note if working without per-task commits**

If prior task commits were intentionally skipped, make one scoped commit:

```bash
git add packages/cloudspells-oci/src/cloudspells/providers/oci/_network_profiles.py packages/cloudspells-oci/src/cloudspells/providers/oci/network.py packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py tests/test_vcn.py tests/test_oke.py docs/how-to/vcnref.md docs/reference/vcn-architecture.md docs/reference/oke-architecture.md docs/tutorials/oke.md
git commit -m "fix: require CloudSpells network profiles for VcnRef OKE"
```

---

## Self-Review

- Spec coverage: The plan enforces CloudSpells-only VCN references through schema metadata, preserves `VcnRef` read-only behavior, and fixes OKE by requiring or installing a profile instead of mutating imported security lists.
- Type consistency: `oke_profile_id()` returns `str`; `Vcn.enable_oke_profile()` returns `str`; `VcnRef.require_network_profile()` returns `str | pulumi.Output[str]`; OKE registers the returned value in component outputs when it is output-backed.
- Scope: This plan does not add arbitrary OCI VCN import support. Manual `VcnRef(...)` remains possible only when the caller explicitly supplies the CloudSpells schema marker and standard topology values.
- Verification: Focused tests cover VCN contract and OKE behavior; `make check` remains the final gate.
