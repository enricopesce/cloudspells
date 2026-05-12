"""Shared Rich console for the CloudSpells CLI — themed for the wizard experience."""

__all__ = ["console"]

from cloudspells.cli.theme import CS_THEME
from rich.console import Console

console: Console = Console(theme=CS_THEME)
