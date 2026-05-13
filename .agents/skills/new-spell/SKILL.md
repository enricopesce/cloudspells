---
name: new-spell
description: Use when adding a new CloudSpells OCI spell; designs use cases, public interfaces, implementation, mocks, tests, docs, and validation.
---

# New CloudSpells Spell

Use this skill when creating a new OCI spell under `packages/cloudspells-oci`.

## Workflow

1. Ask what OCI service or resource the new spell provisions.
2. Derive the top 5 production use cases for that service and present them as candidate spell classes.
3. Wait for the user to approve or adjust the use cases before designing interfaces.
4. Inspect the current codebase before editing:
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/__init__.py`
   - `packages/cloudspells-core/src/cloudspells/core/abstractions/`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py`
   - `packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py`
   - the closest existing spell module
   - `packages/cloudspells-core/src/cloudspells/core/base.py`
   - `tests/mocks.py`
5. Design every public class before writing implementation code.
6. Verify Pulumi OCI SDK constructor signatures before using new provider resources.
7. Implement the module, exports, mocks, tests, and docs.
8. Run `make check` before reporting completion.

## Non-Negotiable Rules

- Follow CS-001 through CS-012 from `AGENTS.md`.
- Caller input stays minimal and natural; provider encoding belongs inside the spell.
- Review existing spell patterns before inventing a new structure.
- If two or more public spell classes share identical accessor or export logic, use a private `_<Resource>Mixin`.
- Use Google-style Markdown docstrings for public APIs.
- Never simulate tool output.

## Interface Design Table

Present this table for each approved use case before implementation:

| Field | Value |
| --- | --- |
| Class name | `<UseCase><Resource>` |
| Inherits | `BaseResource` or `(_<Resource>Mixin, BaseResource)` |
| Constructor parameters | `name`, `compartment_id`, optional `vcn`, and minimal use-case-specific inputs |
| Architecture decisions baked in | access model, tier, lifecycle, scaling, retention, security posture |
| OCI resources created | exact Pulumi OCI resource classes |
| Public outputs | output attributes and `get_*()` methods |
| Validation guards | explicit `ValueError` conditions |

## Reference

Use `references/cloudspells-patterns.md` for canonical structure, test patterns, and source-file responsibilities.
