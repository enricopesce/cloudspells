# CloudSpells Agent Instructions

CloudSpells encodes fixed, opinionated OCI reference architectures with Pulumi Python. It is not a cloud API wrapper, Terraform replacement, or passthrough layer.

## Design Rules

Follow these rules for every code change:

| Rule | Requirement |
| --- | --- |
| CS-001 | No passthrough parameters. The spell decides; callers never forward raw provider options. |
| CS-002 | No deploy-time auto-discovery for values that define what is deployed, such as images and Kubernetes versions. |
| CS-003 | Keep caller input minimal: `name`, `compartment_id`, and the natural network anchor. Use `vcn: Vcn | VcnRef` when the spell owns direct network attachment; use a role-bearing `nsg: Nsg` when the resource attaches through an NSG. Do not require both. |
| CS-004 | Subnet tier placement is the spell's decision. Callers express architectural intent through spell type or role-bearing abstractions such as `Nsg(role=...)`, not raw subnet-tier parameters. |
| CS-005 | For VCN-attached spells that own security-list behavior, register rules during `__init__`, then call `vcn.finalize_network()` before subnet-dependent resources. Spells whose required dependency already owns the rules, such as `ComputeInstance(nsg=...)`, finalize the dependency's VCN after that dependency is constructed. |
| CS-006 | Any spell touching a VCN accepts `vcn: Vcn | VcnRef` directly unless the VCN is carried by a required higher-level dependency such as `Nsg`; in that case derive the VCN from the dependency and do not duplicate the input. |
| CS-007 | Every spell class inherits `BaseResource`. |
| CS-008 | Use `self.create_resource_name("suffix")` for resource names; do not build names with f-strings. |
| CS-009 | Every public module, class, and method has Google-style docstrings. |
| CS-010 | Docstrings use pure Markdown, not RST syntax. |
| CS-011 | If two or more spell classes in one module share identical accessor logic, extract a private `_<Resource>Mixin`. |
| CS-012 | Create-time-only placement inputs such as `availability_domain` and `fault_domain` may auto-resolve internally via async OCI output calls and remain optional overrides. |
| CS-013 | `ComputeInstance` requires `nsg: Nsg` with `nsg.role`. It derives VCN placement from `nsg.vcn` and subnet placement from `nsg.role.subnet_tier`; it must not accept public `vcn` or `subnet` parameters. |

CloudSpells absorbs provider-specific encoding and boilerplate. Callers pass natural Python values; spells handle transformations such as base64, JSON serialization, and provider naming details internally.

## Quality Gate

Run the full gate before declaring any code change complete:

```bash
make check
```

Useful focused commands:

```bash
make check-file FILE=packages/cloudspells-oci/src/cloudspells/providers/oci/<module>.py
.venv/bin/pytest tests/test_vcn.py::TestVcn::test_vcn_creates_base_resources
```

## Routing

| Trigger | Codex route |
| --- | --- |
| Creating a new OCI spell | Use `$new-spell`. |
| Review, audit, check, or analyse spell code | Use the `spell-reviewer` subagent. |
| Apply fixes from an approved spell review | Use the `spell-fixer` subagent. |
| Audit docs, check docs, or review docs | Use the `docs-auditor` subagent. |
| Apply approved documentation fixes | Use the `docs-fixer` subagent. |
| Audit standards or produce a compliance report | Use the `standards-auditor` subagent. |
| Simple bounded edit to existing code | Execute directly in the current session. |

Review and audit agents are read-only. Fixer agents edit only from approved reports and must not re-audit or invent new scope.

## Workflow

- Prefer repo patterns over new abstractions.
- Read the relevant files before editing.
- Use parallel reads and searches when gathering context.
- Preserve existing Claude files until Codex parity is validated.
- When a recurring non-obvious pattern appears, ask whether it belongs in an instruction file or skill.
