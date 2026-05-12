"""cs config — manage Pulumi stack configuration keys.

Wraps the Pulumi Automation API `set_config`, `get_config`, and
`get_all_config` operations without requiring the `pulumi` CLI on PATH.
"""

__all__ = ["config_app"]

import json
from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.workspace import get_stack
from cloudspells.cli.console import console
from rich import box
from rich.table import Table

config_app = typer.Typer(
    name="config",
    help="Manage stack configuration keys.",
    no_args_is_help=True,
)

_PATH_ARG = typer.Argument(help="Stack directory. Defaults to current directory.")
_STACK_OPT = typer.Option(help="Pulumi stack name.")


def _require_pulumi_yaml(work_dir: Path) -> None:
    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        raise typer.Exit(1)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key to set.")],
    value: Annotated[str, typer.Argument(help="Value to assign.")],
    secret: Annotated[bool, typer.Option("--secret", help="Encrypt the value as a secret.")] = False,
    path: Annotated[Path | None, _PATH_ARG] = None,
    stack: Annotated[str, _STACK_OPT] = "dev",
) -> None:
    """Set a stack configuration key.

    Use `--secret` to store the value encrypted with the stack passphrase.

    Raises:
        typer.Exit: On missing `Pulumi.yaml` or automation errors.

    Examples:
        cs config set compartment_ocid ocid1.compartment.oc1..xxx

        cs config set db_password s3cr3t --secret

        cs config set node_count 3 --stack prod
    """
    from pulumi.automation import ConfigValue
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()
    _require_pulumi_yaml(work_dir)
    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
        stack_obj.set_config(key, ConfigValue(value=value, secret=secret))
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    label = " [dim yellow](secret)[/dim yellow]" if secret else ""
    console.print(f"[bold green]✓[/bold green] [cyan]{key}[/cyan]{label}")


@config_app.command("get")
def config_get(
    key: Annotated[str, typer.Argument(help="Config key to retrieve.")],
    path: Annotated[Path | None, _PATH_ARG] = None,
    stack: Annotated[str, _STACK_OPT] = "dev",
) -> None:
    """Print the value of a single configuration key.

    Secrets are displayed as `[secret]`. Pipe to `--key` for scripting.

    Raises:
        typer.Exit: On missing `Pulumi.yaml`, unknown key, or automation errors.

    Examples:
        cs config get compartment_ocid

        cs config get node_count --stack prod
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()
    _require_pulumi_yaml(work_dir)
    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
        cv = stack_obj.get_config(key)
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    typer.echo("[secret]" if cv.secret else cv.value)


@config_app.command("list")
def config_list(
    path: Annotated[Path | None, _PATH_ARG] = None,
    stack: Annotated[str, _STACK_OPT] = "dev",
    as_json: Annotated[bool, typer.Option("--json", help="Emit all config as JSON.")] = False,
) -> None:
    """List all configuration keys for the stack.

    Raises:
        typer.Exit: On missing `Pulumi.yaml` or automation errors.

    Examples:
        cs config list

        cs config list --stack prod

        cs config list --json
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()
    _require_pulumi_yaml(work_dir)
    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
        all_config = stack_obj.get_all_config()
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if not all_config:
        console.print("[dim]No configuration keys set.[/dim]")
        return

    if as_json:
        data = {k: ("[secret]" if v.secret else v.value) for k, v in all_config.items()}
        typer.echo(json.dumps(data, indent=2))
        return

    table = Table(
        show_header=True,
        header_style="bold cyan",
        box=box.ROUNDED,
        border_style="dim",
    )
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_column("Secret", style="yellow", justify="center")
    for k, cv in sorted(all_config.items()):
        value_str = "[dim][secret][/dim]" if cv.secret else cv.value
        secret_str = "●" if cv.secret else ""
        table.add_row(k, value_str, secret_str)
    console.print(table)
