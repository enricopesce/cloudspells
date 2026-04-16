"""cs output — read and display CloudSpells stack outputs."""

__all__ = ["output"]

import json
from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.workspace import get_stack
from cloudspells.cli.console import console
from rich.table import Table


def output(
    path: Annotated[Path | None, typer.Argument(help="Stack directory. Defaults to current directory.")] = None,
    key: Annotated[str | None, typer.Option("--key", "-k", help="Output key to retrieve. Omit for all.")] = None,
    stack: Annotated[str, typer.Option(help="Pulumi stack name.")] = "dev",
    as_json: Annotated[bool, typer.Option("--json", help="Emit all outputs as JSON.")] = False,
) -> None:
    """Read and display stack outputs.

    With no `--key`, displays all outputs as a Rich table.  With `--key`,
    prints the raw value to stdout — useful for scripting.

    Raises:
        typer.Exit: On missing `Pulumi.yaml`, automation errors, or unknown key.

    Examples:
        cs output

        cs output --key kubeconfig

        cs output --json

        cs output ./my-network --stack prod
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[red]Error:[/red] No Pulumi.yaml found in {work_dir}")
        raise typer.Exit(1)

    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
        outputs = stack_obj.outputs()
    except CommandError as exc:
        console.print(f"[red]Error:[/red] Failed to read outputs: {exc}")
        raise typer.Exit(1) from exc

    if key is not None:
        if key not in outputs:
            console.print(f"[red]Error:[/red] Output key '{key}' not found.")
            console.print(f"  Available: {', '.join(sorted(outputs))}")
            raise typer.Exit(1)
        typer.echo(outputs[key].value)
        return

    if not outputs:
        console.print("[dim]No outputs.[/dim]")
        return

    if as_json:
        data = {k: ("[secret]" if v.secret else v.value) for k, v in outputs.items()}
        typer.echo(json.dumps(data, indent=2))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Key")
    table.add_column("Value")
    for k, v in sorted(outputs.items()):
        value_str = "[secret]" if v.secret else str(v.value)
        table.add_row(k, value_str)
    console.print(table)
