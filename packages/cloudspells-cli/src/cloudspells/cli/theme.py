"""CloudSpells CLI theme — named colours and output formatting utilities."""

__all__ = ["CS_THEME", "SPELL_LORE", "fmt_changes", "fmt_result", "glyph"]

from collections.abc import Mapping
from typing import Any, TypedDict

from rich.theme import Theme


class SpellLore(TypedDict):
    """Metadata for a single stack template."""

    glyph: str
    name: str
    lore: str


#: Display metadata for every template in the registry, keyed by canonical ID.
SPELL_LORE: dict[str, SpellLore] = {
    "vcn": {
        "glyph": "🌐",
        "name": "Virtual Cloud Network",
        "lore": "VCN with subnets, route tables, and security rules",
    },
    "compute": {
        "glyph": "⚙️ ",
        "name": "Compute Instance",
        "lore": "OCI compute instance with networking and block storage",
    },
    "oke": {
        "glyph": "☸️ ",
        "name": "Kubernetes Cluster",
        "lore": "OKE cluster with managed node pools and autoscaling",
    },
    "autoscale": {
        "glyph": "↕️ ",
        "name": "Autoscaling Group",
        "lore": "Instance pool with OCI autoscaling policies",
    },
    "lb": {
        "glyph": "⚖️ ",
        "name": "Load Balancer",
        "lore": "OCI load balancer with backends and health checks",
    },
    "bastion": {
        "glyph": "🏰",
        "name": "Bastion Host",
        "lore": "Secure jump host for private subnet access",
    },
    "storage": {
        "glyph": "🗄️ ",
        "name": "Object Storage",
        "lore": "OCI Object Storage bucket with lifecycle rules",
    },
    "iam": {
        "glyph": "🔐",
        "name": "IAM Policies",
        "lore": "IAM groups, dynamic groups, and policy statements",
    },
    "web-db": {
        "glyph": "🏗️ ",
        "name": "Web + Database",
        "lore": "Full web-tier and database stack with all networking",
    },
}

#: Named Rich styles used throughout the CLI.
CS_THEME = Theme({
    "cs.success": "bold green",
    "cs.error": "bold red",
    "cs.action": "bold cyan",
    "cs.muted": "dim",
    "cs.accent": "bold cyan",
    "cs.warn": "bold yellow",
    "cs.header": "bold white",
    "cs.dim": "dim",
    "cs.key": "cyan",
    "cs.path": "dim cyan",
})


def fmt_changes(changes: Mapping[Any, int]) -> str:
    """Format a Pulumi resource-changes dict as a compact Rich markup string.

    Args:
        changes: Mapping of change symbol (`"+"`, `"~"`, `"-"`, `"="`) to
            the count of affected resources.

    Returns:
        Space-separated Rich markup string, or `"no changes"` when empty.
    """
    parts = []
    for sym, color in (("+", "green"), ("~", "yellow"), ("-", "red"), ("=", "dim")):
        count = int(changes.get(sym, 0))  # type: ignore[arg-type]
        if count:
            parts.append(f"[bold {color}]{sym}{count}[/bold {color}]")
    return " ".join(parts) if parts else "no changes"


def fmt_result(result: str) -> str:
    """Format a Pulumi result string with a colour-coded status indicator.

    Args:
        result: Pulumi result string, e.g. `"succeeded"`, `"failed"`.

    Returns:
        Rich markup string with appropriate colour.
    """
    if result == "succeeded":
        return f"[bold green]{result}[/bold green]"
    if result == "failed":
        return f"[bold red]{result}[/bold red]"
    return f"[yellow]{result}[/yellow]"


def glyph(spell: str) -> str:
    """Return the glyph for a template, or a default package emoji.

    Args:
        spell: Canonical template identifier.

    Returns:
        Unicode glyph string.
    """
    return SPELL_LORE.get(spell, SpellLore(glyph="📦", name="", lore=""))["glyph"]
