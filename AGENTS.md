# CloudSpells

CloudSpells implements opinionated OCI reference architectures with Pulumi Python. Each spell owns its architecture and defaults.

## Design rules

- **CS-001** Keep raw provider options out of spell signatures. Model caller inputs in terms of the use case.
- **CS-002** Keep cloud discovery out of default selection, including latest images and Kubernetes versions. CS-012 defines the exception for placement.
- **CS-003** Minimize required inputs to `name`, `compartment_id`, and `vcn: Vcn | VcnRef` where applicable. Derive or securely default the remaining values. Require additional inputs only when the use case needs caller-owned information, such as an explicit image OCID.
- **CS-004** Choose subnet tiers in the spell.
- **CS-005** Accumulate rules with `vcn.add_security_list_rules()` during construction. Call `vcn.finalize_network()` before using subnet IDs or creating subnet-dependent resources.
- **CS-006** Accept `vcn: Vcn | VcnRef` in every spell that uses a VCN.
- **CS-007** Inherit from `BaseResource` in every spell class.
- **CS-008** Generate resource names with `self.create_resource_name("suffix")`.
- **CS-009** Write Google-style docstrings for public modules, classes, and methods. Include `Args:`, `Returns:`, `Raises:`, `Attributes:`, and `Example:` as applicable.
- **CS-010** Use Markdown inline code and fenced code blocks in docstrings. Avoid RST markup and italic markup that renders as literal asterisks in the documentation.
- **CS-011** Extract identical accessors shared by spells in one module into a private `_<Resource>Mixin`. Keep it out of exports and inherit from `(_<Resource>Mixin, BaseResource)`.
- **CS-012** Keep `availability_domain` and `fault_domain` as create-time placement inputs. Expose optional overrides as `pulumi.Input[str] | None = None`. Resolve the default availability domain with `oci.identity.get_availability_domains_output()` and follow the existing spell's placement pattern for fault domains. Avoid blocking provider invokes.

## Working in this repository

- Read the scoped guidance for [packages](packages/AGENTS.md), [tests](tests/AGENTS.md), and [examples](examples/AGENTS.md) before working in those paths.
- Run `make check` from the repository root after code changes. It uses `.venv` and mirrors CI's Ruff, Pyright, pytest with coverage, and Vulture checks. See [the Makefile](Makefile) and [CI workflow](.github/workflows/ci.yml).
- Use `make check-file FILE=path/to/file.py` for quick feedback. See [test guidance](tests/AGENTS.md) for focused test runs.
- Get explicit authorization before running commands that change a live Pulumi stack. Avoid force pushes, hard resets, and recursive deletion of the filesystem root or a home directory.

## Codex workflows

| Request | Workflow |
| --- | --- |
| Create a new OCI spell | Use the [`$new-spell` skill](.agents/skills/new-spell/SKILL.md). |
| Review source code | Use the `spell-reviewer` custom agent. |
| Apply source review findings | Use the `spell-fixer` custom agent with the approved findings. |
| Audit documentation | Use the `docs-auditor` custom agent. |
| Apply documentation audit findings | Use the `docs-fixer` custom agent with the approved findings. |
| Audit repository standards | Use the `standards-auditor` custom agent. |

Work directly on bounded edits. When subagents are available, delegate the listed reviews, audits, and report-driven fixes to the matching agent. The audit agents return findings to the parent, which can save a requested report under `review-reports/` and pass its path to the fixer.
