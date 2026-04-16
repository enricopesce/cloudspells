"""CloudSpells CLI entry point.

Registers the four MVP commands (new, up, destroy, output) on the `cs` Typer
application and wires up the `--version` / `-V` flag.
"""

__all__ = ["app"]

from typing import Annotated

import typer
from cloudspells.cli import __version__
from cloudspells.cli.commands.destroy import destroy
from cloudspells.cli.commands.new import new
from cloudspells.cli.commands.output import output
from cloudspells.cli.commands.up import up

app = typer.Typer(
    name="cs",
    help="CloudSpells CLI — scaffold and manage OCI infrastructure stacks.",
    add_completion=True,
    no_args_is_help=True,
    pretty_exceptions_short=True,
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    """Print the version string and exit when --version is passed.

    Raises:
        typer.Exit: Always raised when `--version` is supplied.
    """
    if value:
        typer.echo(f"cs {__version__}")
        raise typer.Exit()


@app.callback()
def _main(  # pyright: ignore[reportUnusedFunction]
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """CloudSpells CLI — scaffold and manage OCI infrastructure stacks."""


app.command("new")(new)
app.command("up")(up)
app.command("destroy")(destroy)
app.command("output")(output)
