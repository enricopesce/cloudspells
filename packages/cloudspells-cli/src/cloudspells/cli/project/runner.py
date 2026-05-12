"""CloudSpells project runner — sequential deploy and destroy across spells.

Provides `deploy_project` and `destroy_project`, the two core operations
used by `cs project up` and `cs project destroy`. Each function scaffolds
missing spell directories on demand and drives the Pulumi Automation API
directly — no subprocess calls to the `cs` CLI.
"""

__all__ = ["deploy_project", "destroy_project", "project_status"]

from collections.abc import Callable
from pathlib import Path

from cloudspells.cli.automation.workspace import get_stack
from cloudspells.cli.project.model import ProjectConfig, SpellRef
from cloudspells.cli.templates import SPELL_REGISTRY, render


def _ensure_spell_dir(spell_ref: SpellRef, work_dir: Path, stack_name: str) -> Path:
    """Scaffold the spell directory if it does not already contain a Pulumi.yaml.

    Args:
        spell_ref: Spell to scaffold.
        work_dir: Parent project directory.
        stack_name: Pulumi stack name used in the generated program.

    Returns:
        Absolute path to the spell directory.

    Raises:
        ValueError: If the spell type is not in the registry.
    """
    if spell_ref.spell not in SPELL_REGISTRY:
        raise ValueError(f"Unknown spell '{spell_ref.spell}'")
    spell_dir = work_dir / spell_ref.name
    if not (spell_dir / "Pulumi.yaml").exists():
        files = render(spell_ref.spell, spell_ref.name, stack_name)
        spell_dir.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (spell_dir / fname).write_text(content)
    return spell_dir


def deploy_project(
    project: ProjectConfig,
    stack_name: str,
    work_dir: Path,
    env_vars: dict[str, str],
    preview: bool,
    cb: Callable[[str], None],
) -> None:
    """Deploy (or preview) all spells in a project in declaration order.

    Missing spell directories are scaffolded automatically before deployment.

    Args:
        project: Parsed project manifest.
        stack_name: Pulumi stack name to target (e.g. `"dev"`, `"prod"`).
        work_dir: Project root directory containing `project.yaml`.
        env_vars: Environment variables to inject into every Pulumi workspace
            (typically `{"PULUMI_CONFIG_PASSPHRASE": ...}`).
        preview: When `True`, runs `pulumi preview` instead of `pulumi up`.
        cb: Output callback passed to each Pulumi operation.

    Raises:
        ValueError: If a spell type in `project.spells` is not registered.
        pulumi.automation.errors.CommandError: If any Pulumi operation fails.
    """
    for spell_ref in project.spells:
        spell_dir = _ensure_spell_dir(spell_ref, work_dir, stack_name)
        stack = get_stack(stack_name, spell_dir, env_vars)
        if preview:
            stack.preview(on_output=cb)
        else:
            stack.up(on_output=cb)


def destroy_project(
    project: ProjectConfig,
    stack_name: str,
    work_dir: Path,
    env_vars: dict[str, str],
    cb: Callable[[str], None],
) -> None:
    """Destroy all deployed spells in a project in reverse declaration order.

    Spell directories that do not contain a `Pulumi.yaml` are skipped silently.

    Args:
        project: Parsed project manifest.
        stack_name: Pulumi stack name to target.
        work_dir: Project root directory containing `project.yaml`.
        env_vars: Environment variables to inject into every Pulumi workspace.
        cb: Output callback passed to each Pulumi operation.

    Raises:
        pulumi.automation.errors.CommandError: If any Pulumi operation fails.
    """
    for spell_ref in reversed(project.spells):
        spell_dir = work_dir / spell_ref.name
        if not (spell_dir / "Pulumi.yaml").exists():
            continue
        stack = get_stack(stack_name, spell_dir, env_vars)
        stack.destroy(on_output=cb)


def project_status(
    project: ProjectConfig,
    stack_name: str,
    work_dir: Path,
    env_vars: dict[str, str],
) -> list[dict[str, str | int]]:
    """Return a status summary for every spell in the project.

    Each entry in the returned list is a dict with keys:
    `"name"`, `"spell"`, `"status"`, and `"resources"`.

    Args:
        project: Parsed project manifest.
        stack_name: Pulumi stack name to query.
        work_dir: Project root directory.
        env_vars: Environment variables to inject into every Pulumi workspace.

    Returns:
        List of status dicts, one per spell in declaration order.
    """
    rows: list[dict[str, str | int]] = []
    for spell_ref in project.spells:
        spell_dir = work_dir / spell_ref.name
        if not (spell_dir / "Pulumi.yaml").exists():
            rows.append({"name": spell_ref.name, "spell": spell_ref.spell, "status": "not scaffolded", "resources": 0})
            continue
        try:
            stack = get_stack(stack_name, spell_dir, env_vars)
            deployment = stack.export_stack()
            if deployment.deployment:
                all_resources = deployment.deployment.get("resources", [])
                count = sum(1 for r in all_resources if r.get("type") != "pulumi:pulumi:Stack")
                rows.append({
                    "name": spell_ref.name,
                    "spell": spell_ref.spell,
                    "status": "deployed",
                    "resources": count,
                })
            else:
                rows.append({"name": spell_ref.name, "spell": spell_ref.spell, "status": "empty", "resources": 0})
        except Exception:
            rows.append({"name": spell_ref.name, "spell": spell_ref.spell, "status": "not deployed", "resources": 0})
    return rows
