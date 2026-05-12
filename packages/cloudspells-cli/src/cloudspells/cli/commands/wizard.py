"""cs wizard — interactive guided experience.

A step-by-step TUI that walks through the most common CloudSpells operations
without requiring knowledge of flags or subcommands.
"""

__all__ = ["wizard"]

from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.banner import print_banner
from cloudspells.cli.console import console
from cloudspells.cli.theme import SPELL_LORE, fmt_changes, fmt_result
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

# ── Action menu ────────────────────────────────────────────────────────────

_ACTIONS: dict[str, tuple[str, str, str]] = {
    "1": ("⚡", "Create a new stack", "Scaffold and optionally deploy new infrastructure"),
    "2": ("🚀", "Deploy changes", "Apply pending changes to a deployed stack"),
    "3": ("🔍", "Inspect stack state", "View resources tracked in a deployed stack"),
    "4": ("🔄", "Refresh from cloud", "Reconcile Pulumi state with live OCI resources"),
    "5": ("🗑️ ", "Destroy resources", "Tear down all resources in a stack"),
    "6": ("📁", "Manage projects", "Orchestrate multiple stacks as a single project"),
}

# ── Entry point ────────────────────────────────────────────────────────────


def wizard(
    no_banner: Annotated[
        bool,
        typer.Option("--no-banner", help="Skip the opening banner (useful in scripts).", hidden=True),
    ] = False,
) -> None:
    """Interactive guided wizard for common CloudSpells operations.

    Walks through the most common operations with guided prompts and rich
    visual output.  No flags to memorise.

    Examples:
        cs wizard

        cs wizard --no-banner
    """
    if not no_banner:
        print_banner()

    console.print(
        Panel(
            "[dim]  Select an action to get started.  [/dim]",
            border_style="dim cyan",
            padding=(0, 2),
        )
    )
    console.print()

    for key, (symbol, title, subtitle) in _ACTIONS.items():
        console.print(f"  [dim][[bold]{key}[/bold]][/dim]  {symbol}  [bold]{title}[/bold]")
        console.print(f"           [dim]{subtitle}[/dim]")
        console.print()

    choice = Prompt.ask(
        "[bold cyan]Select[/bold cyan]",
        choices=list(_ACTIONS.keys()),
    )
    console.print()

    dispatch = {
        "1": _wizard_new,
        "2": _wizard_deploy,
        "3": _wizard_status,
        "4": _wizard_refresh,
        "5": _wizard_destroy,
        "6": _wizard_project,
    }
    dispatch[choice]()


# ── New stack ──────────────────────────────────────────────────────────────


def _wizard_new() -> None:
    """Guide the user through scaffolding and optionally deploying a new stack."""
    from cloudspells.cli.templates import SPELL_REGISTRY
    from cloudspells.cli.templates import render as _render

    console.rule("[bold cyan]Select a Template[/bold cyan]", style="cyan dim")
    console.print()

    canonical = [s for s in SPELL_LORE if s in SPELL_REGISTRY]

    for i, key in enumerate(canonical, 1):
        lore = SPELL_LORE[key]
        g = lore["glyph"]
        n = lore["name"]
        console.print(f"  [dim][[bold]{i}[/bold]][/dim]  {g}  [bold cyan]{key}[/bold cyan]  [dim]{n}[/dim]")
        console.print(f"           [dim]{lore['lore']}[/dim]")
        console.print()

    choices = [str(i) for i in range(1, len(canonical) + 1)]
    idx = int(Prompt.ask("[bold]Template[/bold]", choices=choices)) - 1
    spell_key = canonical[idx]
    lore = SPELL_LORE[spell_key]

    console.print()
    console.print(f"[cyan]→[/cyan] Template: [bold cyan]{lore['name']}[/bold cyan]  [dim]{lore['lore']}[/dim]")
    console.print()

    name = Prompt.ask("[bold]Stack name[/bold]")

    out_dir = Path(name)
    if out_dir.exists():
        overwrite = Confirm.ask(f"[yellow]'{name}' already exists. Overwrite?[/yellow]", default=False)
        if not overwrite:
            console.print("[dim]Cancelled.[/dim]")
            return

    files = _render(spell_key, name, "dev")
    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, content in files.items():
        (out_dir / fname).write_text(content)

    console.print()
    console.print("[bold green]✓[/bold green] Stack scaffolded:")
    console.print(f"  [dim]{name}/Pulumi.yaml[/dim]")
    console.print(f"  [dim]{name}/__main__.py[/dim]")
    console.print()
    console.print(
        "[dim]Set your compartment OCID before deploying:[/dim]\n"
        f"  [bold]cs config set compartment_ocid <OCID>[/bold]  "
        f"[dim](from {name}/)[/dim]"
    )
    console.print()

    deploy_now = Confirm.ask("[bold]Deploy now?[/bold]", default=False)
    if deploy_now:
        _wizard_deploy(path=out_dir)


# ── Deploy ─────────────────────────────────────────────────────────────────


def _wizard_deploy(path: Path | None = None) -> None:
    """Guide the user through deploying or previewing a stack."""
    from cloudspells.cli.automation.passphrase import resolve_passphrase
    from cloudspells.cli.automation.streaming import make_on_output
    from cloudspells.cli.automation.workspace import get_stack
    from pulumi.automation.errors import CommandError

    if path is None:
        path_str = Prompt.ask("[bold]Stack directory[/bold]", default=".")
        path = Path(path_str)

    work_dir = path.resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        console.print("  Run [bold]cs new <template> <name>[/bold] to scaffold a stack first.")
        return

    stack_name = Prompt.ask("[bold]Stack name[/bold]", default="dev")
    preview = Confirm.ask("[bold]Preview only — no changes applied?[/bold]", default=False)

    if not preview:
        confirmed = Confirm.ask(
            f"[bold]Deploy stack '[cyan]{stack_name}[/cyan]'?[/bold]",
            default=True,
        )
        if not confirmed:
            console.print("[dim]Cancelled. No changes applied.[/dim]")
            return

    console.print()
    verb = "Previewing changes" if preview else "Deploying"
    console.print(f"[bold cyan]→ {verb}...[/bold cyan]")
    console.print()

    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack_name, work_dir, env_vars)
    except CommandError as exc:
        console.print(f"[bold red]✗ Failed to initialise stack:[/bold red] {exc}")
        return

    cb = make_on_output(console)

    try:
        if preview:
            result = stack_obj.preview(on_output=cb)
            summary = result.change_summary or {}
            console.print(f"\n[bold]Changes:[/bold] {fmt_changes(summary)}")
        else:
            result = stack_obj.up(on_output=cb)
            summary = result.summary.resource_changes or {}
            console.print("\n[bold green]✓ Deploy succeeded[/bold green]")
            console.print(f"[bold]Changes:[/bold] {fmt_changes(summary)}")
    except CommandError as exc:
        console.print(f"[bold red]✗ Deploy failed:[/bold red] {exc}")


# ── Status ─────────────────────────────────────────────────────────────────


def _wizard_status() -> None:
    """Guide the user through inspecting a stack's resource tree."""
    from cloudspells.cli.automation.passphrase import resolve_passphrase
    from cloudspells.cli.automation.workspace import get_stack
    from rich.tree import Tree

    def _urn_label(urn: str) -> str:
        parts = urn.split("::")
        return f"[magenta]{parts[2]}[/magenta] [dim]::[/dim] [bold]{parts[3]}[/bold]" if len(parts) >= 4 else urn

    path_str = Prompt.ask("[bold]Stack directory[/bold]", default=".")
    stack_name = Prompt.ask("[bold]Stack name[/bold]", default="dev")
    work_dir = Path(path_str).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        return

    env_vars = resolve_passphrase()
    stack_obj = get_stack(stack_name, work_dir, env_vars)
    deployment = stack_obj.export_stack()
    data = deployment.deployment

    if not data:
        console.print("[dim]Stack has no state yet. Run cs up (or option 2) to deploy.[/dim]")
        return

    resources = [r for r in data.get("resources", []) if r.get("type") != "pulumi:pulumi:Stack"]

    if not resources:
        console.print("[dim]No resources in stack state.[/dim]")
        return

    console.print()
    tree = Tree(f"[bold cyan]{work_dir.name}[/bold cyan] [dim]/ {stack_name}[/dim]")
    for r in resources:
        urn = r.get("urn", "")
        rid = r.get("id", "")
        label = _urn_label(urn) if urn else r.get("type", "unknown")
        node = tree.add(label)
        if rid:
            node.add(f"[dim]id:[/dim] [dim cyan]{rid}[/dim cyan]")
    console.print(tree)
    console.print(f"\n[dim]{len(resources)} resource(s)[/dim]")


# ── Refresh ────────────────────────────────────────────────────────────────


def _wizard_refresh() -> None:
    """Guide the user through reconciling Pulumi state with live OCI resources."""
    from cloudspells.cli.automation.passphrase import resolve_passphrase
    from cloudspells.cli.automation.streaming import make_on_output
    from cloudspells.cli.automation.workspace import get_stack
    from pulumi.automation.errors import CommandError

    path_str = Prompt.ask("[bold]Stack directory[/bold]", default=".")
    stack_name = Prompt.ask("[bold]Stack name[/bold]", default="dev")
    work_dir = Path(path_str).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        return

    console.print()
    console.print("[cyan]→ Refreshing state from OCI...[/cyan]")
    console.print()

    env_vars = resolve_passphrase()
    cb = make_on_output(console)

    try:
        stack_obj = get_stack(stack_name, work_dir, env_vars)
        result = stack_obj.refresh(on_output=cb)
        console.print(f"\n[bold green]✓ Refresh complete.[/bold green] Result: {fmt_result(result.summary.result)}")
    except CommandError as exc:
        console.print(f"[bold red]✗ Refresh failed:[/bold red] {exc}")


# ── Destroy ────────────────────────────────────────────────────────────────


def _wizard_destroy() -> None:
    """Guide the user through safely destroying a stack."""
    from cloudspells.cli.automation.passphrase import resolve_passphrase
    from cloudspells.cli.automation.streaming import make_on_output
    from cloudspells.cli.automation.workspace import get_stack
    from pulumi.automation.errors import CommandError

    path_str = Prompt.ask("[bold]Stack directory[/bold]", default=".")
    stack_name = Prompt.ask("[bold]Stack name[/bold]", default="dev")
    work_dir = Path(path_str).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        return

    console.print()
    console.print(
        Panel(
            f"[bold yellow]All resources in stack '[cyan]{stack_name}[/cyan]' "
            "will be permanently destroyed.[/bold yellow]\n"
            "[dim]This action cannot be undone.[/dim]",
            border_style="yellow",
            padding=(0, 2),
        )
    )
    console.print()

    confirmed = Confirm.ask(
        f"[bold yellow]Destroy all resources in '[cyan]{stack_name}[/cyan]'?[/bold yellow]",
        default=False,
    )
    if not confirmed:
        console.print("[dim]Cancelled. No resources were destroyed.[/dim]")
        return

    console.print()
    console.print("[bold yellow]→ Destroying resources...[/bold yellow]")
    console.print()

    env_vars = resolve_passphrase()
    cb = make_on_output(console)

    try:
        stack_obj = get_stack(stack_name, work_dir, env_vars)
        result = stack_obj.destroy(on_output=cb)
        console.print(f"\n[bold green]✓ Destroy complete.[/bold green] Result: {fmt_result(result.summary.result)}")
    except CommandError as exc:
        console.print(f"[bold red]✗ Destroy failed:[/bold red] {exc}")


# ── Projects ───────────────────────────────────────────────────────────────


def _wizard_project() -> None:
    """Print a quick reference for multi-stack project commands."""
    console.print()
    console.rule("[bold cyan]Project Management[/bold cyan]", style="cyan dim")
    console.print()

    steps = [
        ("Create a new project", "cs project new <name> <template> [<template>...]"),
        ("Deploy the full project", "cs project up"),
        ("Preview pending changes", "cs project up --preview"),
        ("Check all stack statuses", "cs project status"),
        ("Destroy all stacks", "cs project destroy"),
    ]

    for title, cmd in steps:
        console.print(f"  [dim]{title}[/dim]")
        console.print(f"    [bold cyan]{cmd}[/bold cyan]")
        console.print()
