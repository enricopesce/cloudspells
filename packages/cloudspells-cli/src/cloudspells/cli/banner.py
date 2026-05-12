"""CloudSpells ASCII banner — the grimoire cover page.

Call `print_banner()` to render the wizard banner on any console.
"""

__all__ = ["BANNER_MARKUP", "print_banner"]

from rich.align import Align
from rich.panel import Panel
from rich.text import Text

BANNER_MARKUP = (
    "[bold magenta]                                    [/bold magenta]\n"
    "[bold magenta]  ⚡  C L O U D S P E L L S  ⚡   [/bold magenta]\n"
    "[bold magenta]                                    [/bold magenta]\n"
    "[dim]  ────────────────────────────────  [/dim]\n"
    "[italic dim]  The Ancient Art of Cloud Conjuration  [/italic dim]"
)


def print_banner() -> None:
    """Render the CloudSpells wizard banner to the console.

    Displays a magenta-bordered panel with the project name and tagline.
    Suitable for the opening of any interactive wizard command.
    """
    from cloudspells.cli.console import console

    console.print()
    console.print(
        Panel(
            Align.center(Text.from_markup(BANNER_MARKUP)),
            border_style="magenta",
            padding=(0, 4),
        )
    )
    console.print()
