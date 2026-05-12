"""CloudSpells CLI entry point.

Registers commands and sub-apps on the `cs` Typer application.

Commands
--------
- `cs wizard`   — interactive guided spell-casting experience  ← start here
- `cs new`      — scaffold a stack from a spell template
- `cs up`       — deploy or preview a stack
- `cs destroy`  — tear down a stack
- `cs output`   — read stack outputs
- `cs refresh`  — reconcile state with live OCI resources
- `cs status`   — display the resource tree (no live API calls)
- `cs config`   — manage stack configuration keys
- `cs stack`    — list and manage Pulumi stacks
- `cs backend`  — generate backend URLs for remote state storage
- `cs project`  — orchestrate multi-spell projects
"""

__all__ = ["app"]

from typing import Annotated

import typer
from cloudspells.cli import __version__
from cloudspells.cli.commands.backend import backend_app
from cloudspells.cli.commands.config import config_app
from cloudspells.cli.commands.destroy import destroy
from cloudspells.cli.commands.new import new
from cloudspells.cli.commands.output import output
from cloudspells.cli.commands.project import project_app
from cloudspells.cli.commands.refresh import refresh
from cloudspells.cli.commands.stack import stack_app
from cloudspells.cli.commands.status import status
from cloudspells.cli.commands.up import up
from cloudspells.cli.commands.wizard import wizard

app = typer.Typer(
    name="cs",
    help=(
        "[bold cyan]CloudSpells[/bold cyan] — Infrastructure automation for Oracle Cloud\n\n"
        "New here? Run [bold]cs wizard[/bold] for the guided experience.\n"
        "Every command has [bold]--help[/bold]."
    ),
    add_completion=True,
    no_args_is_help=True,
    pretty_exceptions_short=True,
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
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
    version: Annotated[  # pyright: ignore[reportUnusedParameter]
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
    """CloudSpells — The Ancient Art of Cloud Conjuration."""


# ── Primary commands ───────────────────────────────────────────────────────

app.command("wizard")(wizard)
app.command("new")(new)
app.command("up")(up)
app.command("destroy")(destroy)
app.command("output")(output)
app.command("refresh")(refresh)
app.command("status")(status)

# ── Sub-apps ───────────────────────────────────────────────────────────────

app.add_typer(config_app)
app.add_typer(stack_app)
app.add_typer(backend_app)
app.add_typer(project_app)
