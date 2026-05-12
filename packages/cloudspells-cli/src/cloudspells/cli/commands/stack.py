"""cs stack — list and manage Pulumi stacks in a project directory.

Wraps the Pulumi Automation API `LocalWorkspace` to enumerate and remove
stacks without requiring the `pulumi` CLI on PATH.
"""

__all__ = ["stack_app"]

from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.workspace import get_stack, get_workspace
from cloudspells.cli.console import console
from rich import box
from rich.table import Table

stack_app = typer.Typer(
    name="stack",
    help="List and manage Pulumi stacks.",
    no_args_is_help=True,
)

_PATH_ARG = typer.Argument(help="Stack directory. Defaults to current directory.")


def _require_pulumi_yaml(work_dir: Path) -> None:
    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        raise typer.Exit(1)


@stack_app.command("list")
def stack_list(
    path: Annotated[Path | None, _PATH_ARG] = None,
) -> None:
    """List all Pulumi stacks in the project directory.

    Raises:
        typer.Exit: On missing `Pulumi.yaml` or automation errors.

    Examples:
        cs stack list

        cs stack list ./my-network
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()
    _require_pulumi_yaml(work_dir)

    try:
        ws = get_workspace(work_dir)
        stacks = ws.list_stacks()
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] Failed to list stacks: {exc}")
        raise typer.Exit(1) from exc

    if not stacks:
        console.print("[dim]No stacks found.[/dim]")
        return

    table = Table(
        show_header=True,
        header_style="bold cyan",
        box=box.ROUNDED,
        border_style="dim",
    )
    table.add_column("Name", style="bold")
    table.add_column("Resources", justify="right", style="green")
    table.add_column("Last Update", style="dim")
    table.add_column("In Progress", style="yellow", justify="center")

    for s in stacks:
        resources = str(s.resource_count) if s.resource_count is not None else "-"
        last_update = str(s.last_update) if s.last_update else "-"
        in_progress = "●" if s.update_in_progress else ""
        table.add_row(s.name, resources, last_update, in_progress)

    console.print(table)


@stack_app.command("rm")
def stack_rm(
    name: Annotated[str, typer.Argument(help="Stack name to remove.")],
    path: Annotated[Path | None, _PATH_ARG] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompt.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Remove even if the stack still has resources.")] = False,
) -> None:
    """Remove a stack and its state from the project.

    The stack must have no resources unless `--force` is passed.
    Use `cs destroy` first to tear down live resources.

    Raises:
        typer.Exit: On missing `Pulumi.yaml`, user abort, or automation errors.

    Examples:
        cs stack rm dev --yes

        cs stack rm old-stack --force --yes

        cs stack rm staging ./my-network --yes
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()
    _require_pulumi_yaml(work_dir)

    if not yes:
        typer.confirm(f"Remove stack '{name}' from {work_dir}?", abort=True)

    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(name, work_dir, env_vars)
        stack_obj.workspace.remove_stack(name, force=force)
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[bold green]✓[/bold green] Stack [cyan]{name}[/cyan] removed.")
