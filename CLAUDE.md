# CLAUDE.md

CloudSpells encodes fixed, opinionated OCI reference architectures via Pulumi Python — not a cloud-API wrapper or Terraform replacement.

## CS Design Rules

| Rule | Description |
|------|-------------|
| CS-001 | **No passthrough parameters.** The spell decides; callers never forward raw provider options. |
| CS-002 | **No auto-discovery.** Never call cloud APIs to resolve values the caller did not supply (latest image, latest K8s version, etc.). |
| CS-003 | **Minimal caller input.** Caller supplies only `name`, `compartment_id`, and `vcn: Vcn \| VcnRef`. Everything else is derived or securely defaulted inside the spell. |
| CS-004 | **Opinionated topology.** Subnet tier placement is the spell's decision, not the caller's. |
| CS-005 | **VCN lazy init.** Call `vcn.add_security_list_rules()` during `__init__`, then `vcn.finalize_network()` before any subnet-dependent resource. |
| CS-006 | **`Vcn \| VcnRef` everywhere.** Any spell touching a VCN must accept `vcn: Vcn \| VcnRef`. |
| CS-007 | **Inherits `BaseResource`.** Every spell class must. |
| CS-008 | **`ResourceNamer` for all names.** `self.create_resource_name("suffix")` — never f-string name building. |
| CS-009 | **Full docs required.** Every public class, method, and module needs a Google-style docstring (`Args:`, `Returns:`, `Raises:`, `Attributes:`, `Example:` as applicable). |
| CS-010 | **Pure Markdown docstrings.** No RST syntax (`` ``value`` ``, `::` blocks, `*italic*`). |

**Create-time-only inputs** (`availability_domain`, `fault_domain`): auto-resolve via `oci.identity.get_availability_domains_output()` (async only — never the blocking form). Expose as optional overrides (`param: pulumi.Input[str] | None = None`).

## Quality Gate

Run before declaring any code change complete:

```bash
source .venv/bin/activate
ruff check packages/ tests/ && ruff format --check packages/ tests/ && pyright && pytest
```

Individual: `ruff check packages/ tests/ --fix` · `ruff format packages/ tests/` · `pyright` · `pytest` · `vulture packages/ --min-confidence 80`

Single test: `pytest tests/test_vcn.py::TestVcn::test_vcn_creates_base_resources`

## Agent & Skill Routing

| Trigger | Route to |
|---------|----------|
| Creating any new spell | `new-spell` skill |
| "review / audit / check / analyse" code | `spell-reviewer` agent |
| "apply the fixes" / "fix the issues" after a review | `spell-fixer` agent |
| "audit docs" / "fix the docs" | `docs-auditor` agent |
| Simple bounded edit to existing code | Direct execution |

## Operational Protocols

- **Quality gate**: run the full gate before declaring any code change complete.
- **Parallel tool calls**: parallelize all independent reads, searches, and writes in a single message.
- **Delegate, don't inline**: for review, audit, or new-spell work, invoke the designated agent — do not reproduce its workflow inline.
- **Self-improvement**: when a non-obvious pattern recurs across sessions, prompt the user about capturing it in a skill or rule file.
