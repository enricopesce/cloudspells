# Release Model

CloudSpells is a monorepo with independently released Python distributions.
The repository, CI gate, tests, and documentation stay together, but a release
tag publishes exactly one package.

## Packages

| Package | Purpose | Depends on |
| --- | --- | --- |
| `cloudspells-core` | Cloud-neutral base classes, abstractions, naming, tagging, and shared constants | `pulumi` |
| `cloudspells-oci` | OCI provider spells | `cloudspells-core`, `pulumi`, `pulumi-oci` |
| `cloudspells-cli` | Optional `cs` command for scaffolding and stack operations | `cloudspells-core`, `cloudspells-oci` |

Application stacks normally install the provider they use:

```bash
pip install cloudspells-oci
```

The provider installs `cloudspells-core` automatically. Install
`cloudspells-core` directly only when building provider packages or shared
CloudSpells abstractions.

## Release Rules

| Change | Release |
| --- | --- |
| Shared abstractions, naming, tagging, or base resource behavior | `cloudspells-core`, then any provider that needs the new core API |
| OCI spell behavior only | `cloudspells-oci` |
| CLI scaffolding or stack-management behavior only | `cloudspells-cli` |
| Documentation only | No package release |

Provider packages depend on a compatible `cloudspells-core` minor line. For
example, `cloudspells-oci` `0.2.x` depends on `cloudspells-core>=0.2.0,<0.3.0`.
That keeps patch releases independent while preventing an older provider from
silently accepting a future incompatible core release.

## Quality Gate

Every publish tag triggers a mandatory quality job that runs in parallel with
package resolution. The build step cannot start until the quality job passes.
The following checks run against the full repository on every publish:

| Check | Tool | Command |
| --- | --- | --- |
| Lint | ruff | `ruff check packages/ tests/` |
| Format | ruff | `ruff format --check packages/ tests/` |
| Type check | pyright | `pyright` |
| Tests | pytest | `pytest` |
| Dead code | vulture | `vulture packages/ --min-confidence 80` |

A failure in any of these checks blocks the build and publish jobs entirely.
Fix the failure, delete the tag, and re-push a corrected tag to retry.

## Release Tags

Release tags include the distribution name:

```bash
git tag cloudspells-core-v0.2.1
git tag cloudspells-oci-v0.2.1
git tag cloudspells-cli-v0.1.1
git push origin cloudspells-oci-v0.2.1
```

The publish workflow resolves the package from the tag, verifies that the tag
version matches `packages/<package>/pyproject.toml`, builds only that package,
and publishes only that package's artifacts.

### `cloudspells-cli` dual version requirement

For `cloudspells-cli` releases, the tag version must match **two** files:

1. `packages/cloudspells-cli/pyproject.toml` — the `[project] version` field.
2. `packages/cloudspells-cli/src/cloudspells/cli/__init__.py` — the `__version__`
   module-level string.

If either file is out of sync with the tag, the build job fails with an error
naming the mismatched value. Update both files before pushing a CLI release tag.
