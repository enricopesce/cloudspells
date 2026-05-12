"""cs refresh — reconcile Pulumi state with live OCI resources.

Wraps `pulumi.automation` to run `pulumi refresh` against the stack in a
given directory without requiring the `pulumi` CLI on PATH.
"""

__all__ = ["refresh"]

from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.streaming import make_on_output
from cloudspells.cli.automation.workspace import get_stack
from cloudspells.cli.console import console
from cloudspells.cli.theme import fmt_result


def refresh(
    path: Annotated[Path | None, typer.Argument(help="Stack directory. Defaults to current directory.")] = None,
    stack: Annotated[str, typer.Option(help="Pulumi stack name.")] = "dev",
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompt.")] = False,
) -> None:
    """Reconcile Pulumi state with the live state of OCI resources.

    Queries every resource in the stack from OCI and updates the Pulumi
    state file to match.  No resources are created or destroyed.

    Raises:
        typer.Exit: On missing `Pulumi.yaml`, automation errors, or user abort.

    Examples:
        cs refresh

        cs refresh --yes

        cs refresh ./my-network --stack prod --yes
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        console.print("  Run [bold]cs new <template> <name>[/bold] to scaffold a stack.")
        raise typer.Exit(1)

    if not yes:
        typer.confirm(f"Refresh stack '{stack}' in {work_dir}?", abort=True)

    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] Failed to initialise stack: {exc}")
        raise typer.Exit(1) from exc

    cb = make_on_output(console)
    console.rule(f"[bold cyan]Refreshing[/bold cyan] [dim]{work_dir.name} / {stack}[/dim]", style="cyan dim")

    try:
        result = stack_obj.refresh(on_output=cb)
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] Refresh failed: {exc}")
        raise typer.Exit(1) from exc

    console.print(f"\n[bold]Result:[/bold] {fmt_result(result.summary.result)}")
