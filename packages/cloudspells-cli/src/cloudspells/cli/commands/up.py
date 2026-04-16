"""cs up — deploy a CloudSpells stack (or preview changes).

Wraps `pulumi.automation` to run `pulumi up` or `pulumi preview` against
the stack in a given directory without requiring the `pulumi` CLI on PATH.
"""

__all__ = ["up"]

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.streaming import make_on_output
from cloudspells.cli.automation.workspace import get_stack
from cloudspells.cli.console import console


def up(
    path: Annotated[Path | None, typer.Argument(help="Stack directory. Defaults to current directory.")] = None,
    preview: Annotated[bool, typer.Option("--preview", "-p", help="Preview only — no changes applied.")] = False,
    stack: Annotated[str, typer.Option(help="Pulumi stack name.")] = "dev",
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompt.")] = False,
) -> None:
    """Deploy a CloudSpells stack, or preview changes without applying them.

    Runs in the current directory by default.  Pass a PATH argument to
    target a different stack directory.

    Raises:
        typer.Exit: On missing `Pulumi.yaml`, automation errors, or user abort.

    Examples:
        cs up

        cs up --preview

        cs up ./my-network --stack prod

        cs up --yes
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[red]Error:[/red] No Pulumi.yaml found in {work_dir}")
        console.print("  Run 'cs new <spell> <name>' to scaffold a new stack.")
        raise typer.Exit(1)

    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
    except CommandError as exc:
        console.print(f"[red]Error:[/red] Failed to initialise stack: {exc}")
        raise typer.Exit(1) from exc

    cb = make_on_output(console)

    if preview:
        console.print(f"[bold]Previewing stack '{stack}' in {work_dir}...[/bold]")
        try:
            result = stack_obj.preview(on_output=cb)
        except CommandError as exc:
            console.print(f"[red]Error:[/red] Preview failed: {exc}")
            raise typer.Exit(1) from exc
        changes = result.change_summary or {}
        console.print(f"\n[bold]Summary:[/bold] {_format_changes(changes)}")
    else:
        if not yes:
            typer.confirm(f"Deploy stack '{stack}' in {work_dir}?", abort=True)
        console.print(f"[bold]Deploying stack '{stack}' in {work_dir}...[/bold]")
        try:
            up_result = stack_obj.up(on_output=cb)
        except CommandError as exc:
            console.print(f"[red]Error:[/red] Deployment failed: {exc}")
            raise typer.Exit(1) from exc
        changes = up_result.summary.resource_changes or {}
        console.print(f"\n[bold]Result:[/bold] {up_result.summary.result}")
        console.print(f"[bold]Changes:[/bold] {_format_changes(changes)}")


def _format_changes(changes: Mapping[Any, int]) -> str:
    """Format a resource-changes dict as a compact coloured summary string.

    Args:
        changes: Mapping of change symbol (`"+"`, `"~"`, `"-"`, `"="`) to
            the count of affected resources.

    Returns:
        Space-separated Rich markup string (e.g. `"[green]+3[/green] [red]-1[/red]"`),
        or `"no changes"` when the dict is empty or all counts are zero.
    """
    parts = []
    for sym, color in (("+", "green"), ("~", "yellow"), ("-", "red"), ("=", "dim")):
        count = int(changes.get(sym, 0))  # type: ignore[arg-type]
        if count:
            parts.append(f"[{color}]{sym}{count}[/{color}]")
    return " ".join(parts) if parts else "no changes"
