"""cs project — orchestrate multi-spell CloudSpells projects.

A project is a `project.yaml` file that declares an ordered list of spell
stacks.  `cs project up` deploys them in order; `cs project destroy` tears
them down in reverse.
"""

__all__ = ["project_app"]

from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.streaming import make_on_output
from cloudspells.cli.console import console
from cloudspells.cli.project.model import ProjectConfig, SpellRef
from cloudspells.cli.project.runner import deploy_project, destroy_project, project_status
from cloudspells.cli.templates import SPELL_REGISTRY, list_spells, render
from rich.table import Table

project_app = typer.Typer(
    name="project",
    help="Orchestrate multi-spell projects.",
    no_args_is_help=True,
)

_YAML = "project.yaml"

_PATH_ARG = typer.Argument(help="Project directory. Defaults to current directory.")
_STACK_OPT = typer.Option(help="Pulumi stack name.")


def _load_project(work_dir: Path) -> ProjectConfig:
    yaml_path = work_dir / _YAML
    if not yaml_path.exists():
        console.print(f"[red]Error:[/red] No {_YAML} found in {work_dir}")
        console.print("  Run 'cs project new <name> <spell>...' to scaffold one.")
        raise typer.Exit(1)
    return ProjectConfig.load(yaml_path)


@project_app.command("new")
def project_new(
    name: Annotated[str, typer.Argument(help="Project name and directory to create.")],
    spells: Annotated[list[str] | None, typer.Argument(help="Spell types to include (e.g. vcn oke storage).")] = None,
    description: Annotated[str, typer.Option("--description", "-d", help="Short project description.")] = "",
    stack: Annotated[str, _STACK_OPT] = "dev",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing directory.")] = False,
) -> None:
    """Scaffold a new multi-spell project directory.

    Creates `<NAME>/project.yaml` and one subdirectory per spell, each
    containing a `Pulumi.yaml` and `__main__.py` ready to configure.

    Raises:
        typer.Exit: On unknown spell types, existing directory without
            `--force`, or `--list` flag.

    Examples:
        cs project new my-prod vcn oke storage

        cs project new dev-env vcn compute --description "Dev environment"
    """
    if not spells:
        console.print("[red]Error:[/red] At least one spell type is required.")
        console.print(f"  Available: {', '.join(list_spells())}")
        raise typer.Exit(1)

    unknown = [s for s in spells if s not in SPELL_REGISTRY]
    if unknown:
        console.print(f"[red]Error:[/red] Unknown spell(s): {', '.join(unknown)}")
        console.print(f"  Available: {', '.join(list_spells())}")
        raise typer.Exit(1)

    out_dir = Path(name)
    if out_dir.exists() and not force:
        console.print(f"[red]Error:[/red] Directory '{name}' already exists. Use --force to overwrite.")
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    spell_refs: list[SpellRef] = []
    for spell in spells:
        spell_name = f"{name}-{spell}"
        spell_refs.append(SpellRef(spell=spell, name=spell_name))
        files = render(spell, spell_name, stack)
        spell_dir = out_dir / spell_name
        spell_dir.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (spell_dir / fname).write_text(content)
        console.print(f"[green]✓[/green] Scaffolded {spell_name}/")

    project = ProjectConfig(name=name, description=description, spells=spell_refs)
    project.save(out_dir / _YAML)
    console.print(f"[green]✓[/green] Created {name}/{_YAML}")

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  cd {name}")
    console.print("  # set compartment_ocid in each spell subdirectory")
    console.print("  cs project up --preview")
    console.print("  cs project up")


@project_app.command("up")
def project_up(
    path: Annotated[Path | None, _PATH_ARG] = None,
    stack: Annotated[str, _STACK_OPT] = "dev",
    preview: Annotated[bool, typer.Option("--preview", "-p", help="Preview only — no changes applied.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompt.")] = False,
) -> None:
    """Deploy all spells in a project in declaration order.

    Missing spell directories are scaffolded automatically before deployment.
    To preview without applying changes, use `--preview`.

    Raises:
        typer.Exit: On missing `project.yaml`, automation errors, or user abort.

    Examples:
        cs project up

        cs project up --preview

        cs project up ./my-prod --stack prod --yes
    """
    work_dir = (path or Path(".")).resolve()
    project = _load_project(work_dir)

    action = "Preview" if preview else "Deploy"
    if not yes and not preview:
        typer.confirm(f"{action} {len(project.spells)} spell(s) in project '{project.name}'?", abort=True)

    console.print(f"[bold]{action}ing project '{project.name}' ({len(project.spells)} spell(s))...[/bold]")
    env_vars = resolve_passphrase()
    cb = make_on_output(console)

    try:
        deploy_project(project, stack, work_dir, env_vars, preview, cb)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"\n[green]✓[/green] Project '{project.name}' {'previewed' if preview else 'deployed'}.")


@project_app.command("destroy")
def project_destroy(
    path: Annotated[Path | None, _PATH_ARG] = None,
    stack: Annotated[str, _STACK_OPT] = "dev",
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompt.")] = False,
) -> None:
    """Destroy all spells in a project in reverse declaration order.

    Spell directories without a `Pulumi.yaml` are skipped silently.

    Raises:
        typer.Exit: On missing `project.yaml`, automation errors, or user abort.

    Examples:
        cs project destroy --yes

        cs project destroy ./my-prod --stack prod --yes
    """
    work_dir = (path or Path(".")).resolve()
    project = _load_project(work_dir)

    if not yes:
        typer.confirm(f"Destroy all resources in project '{project.name}'?", abort=True)

    n = len(project.spells)
    console.print(f"[bold]Destroying project '{project.name}' ({n} spell(s), reverse order)...[/bold]")
    env_vars = resolve_passphrase()
    cb = make_on_output(console)

    destroy_project(project, stack, work_dir, env_vars, cb)
    console.print(f"\n[green]✓[/green] Project '{project.name}' destroyed.")


@project_app.command("status")
def project_status_cmd(
    path: Annotated[Path | None, _PATH_ARG] = None,
    stack: Annotated[str, _STACK_OPT] = "dev",
) -> None:
    """Show the deployment status of every spell in a project.

    Reads local Pulumi state — no live OCI API calls are made.
    Run `cs refresh` on individual stacks to sync state first.

    Raises:
        typer.Exit: On missing `project.yaml`.

    Examples:
        cs project status

        cs project status ./my-prod --stack prod
    """
    work_dir = (path or Path(".")).resolve()
    project = _load_project(work_dir)
    env_vars = resolve_passphrase()

    rows = project_status(project, stack, work_dir, env_vars)

    from rich import box

    table = Table(
        show_header=True,
        header_style="bold cyan",
        box=box.ROUNDED,
        border_style="dim",
        title=f"[bold]{project.name}[/bold] [dim]/ {stack}[/dim]",
        title_style="",
    )
    table.add_column("Stack", style="bold")
    table.add_column("Template", style="cyan")
    table.add_column("Status")
    table.add_column("Resources", justify="right", style="green")

    status_colours = {
        "deployed": "bold green",
        "not deployed": "yellow",
        "not scaffolded": "dim",
        "empty": "dim",
    }

    for row in rows:
        status_val = str(row["status"])
        colour = status_colours.get(status_val, "white")
        count = str(row["resources"]) if row["resources"] else "[dim]-[/dim]"
        table.add_row(str(row["name"]), str(row["spell"]), f"[{colour}]{status_val}[/{colour}]", count)

    console.print(table)
