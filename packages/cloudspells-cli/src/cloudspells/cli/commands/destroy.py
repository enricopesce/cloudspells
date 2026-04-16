"""cs destroy — tear down all resources in a CloudSpells stack."""

__all__ = ["destroy"]

from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.streaming import make_on_output
from cloudspells.cli.automation.workspace import get_stack
from cloudspells.cli.console import console


def destroy(
    path: Annotated[Path | None, typer.Argument(help="Stack directory. Defaults to current directory.")] = None,
    stack: Annotated[str, typer.Option(help="Pulumi stack name.")] = "dev",
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompt.")] = False,
    remove: Annotated[bool, typer.Option("--remove", help="Remove stack state after destroy.")] = False,
) -> None:
    """Tear down all resources in a CloudSpells stack.

    Raises:
        typer.Exit: On missing `Pulumi.yaml`, automation errors, or user abort.

    Examples:
        cs destroy

        cs destroy --yes

        cs destroy ./my-network --stack prod --yes
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[red]Error:[/red] No Pulumi.yaml found in {work_dir}")
        raise typer.Exit(1)

    if not yes:
        typer.confirm(f"Destroy all resources in stack '{stack}'?", abort=True)

    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
    except CommandError as exc:
        console.print(f"[red]Error:[/red] Failed to initialise stack: {exc}")
        raise typer.Exit(1) from exc

    cb = make_on_output(console)
    console.print(f"[bold]Destroying stack '{stack}' in {work_dir}...[/bold]")

    try:
        result = stack_obj.destroy(on_output=cb)
    except CommandError as exc:
        console.print(f"[red]Error:[/red] Destroy failed: {exc}")
        raise typer.Exit(1) from exc

    console.print(f"\n[bold]Result:[/bold] {result.summary.result}")

    if remove:
        try:
            stack_obj.workspace.remove_stack(stack)
            console.print(f"[green]✓[/green] Stack state '{stack}' removed.")
        except Exception as exc:
            console.print(f"[yellow]Warning:[/yellow] Failed to remove stack state: {exc}")
