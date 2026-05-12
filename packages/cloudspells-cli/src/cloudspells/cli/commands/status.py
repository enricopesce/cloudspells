"""cs status — display the resource tree of a deployed stack.

Reads the Pulumi state snapshot via `stack.export_stack()` and renders
a Rich tree without querying OCI (no live API calls, instant).
"""

__all__ = ["status"]

from pathlib import Path
from typing import Annotated

import typer
from cloudspells.cli.automation.passphrase import resolve_passphrase
from cloudspells.cli.automation.workspace import get_stack
from cloudspells.cli.console import console
from rich.tree import Tree


def _urn_label(urn: str) -> str:
    """Extract a concise `type::name` label from a full Pulumi URN.

    Args:
        urn: Full Pulumi URN string, e.g.
            `"urn:pulumi:dev::my-vcn::oci:Core/vcn:Vcn::my-vcn-vcn"`.

    Returns:
        Rich-markup label with type in magenta and name in bold.
    """
    parts = urn.split("::")
    if len(parts) >= 4:
        return f"[magenta]{parts[2]}[/magenta] [dim]::[/dim] [bold]{parts[3]}[/bold]"
    return urn


def status(
    path: Annotated[Path | None, typer.Argument(help="Stack directory. Defaults to current directory.")] = None,
    stack: Annotated[str, typer.Option(help="Pulumi stack name.")] = "dev",
) -> None:
    """Display the resource tree of a deployed stack (no live API calls).

    Reads the local Pulumi state snapshot and renders every tracked resource
    as a Rich tree.  Run `cs refresh` first to sync state with OCI.

    Raises:
        typer.Exit: On missing `Pulumi.yaml` or automation errors.

    Examples:
        cs status

        cs status ./my-network --stack prod
    """
    from pulumi.automation.errors import CommandError

    work_dir = (path or Path(".")).resolve()

    if not (work_dir / "Pulumi.yaml").exists():
        console.print(f"[bold red]✗[/bold red] No Pulumi.yaml found in {work_dir}")
        console.print("  Run [bold]cs new <template> <name>[/bold] to scaffold a stack.")
        raise typer.Exit(1)

    env_vars = resolve_passphrase()

    try:
        stack_obj = get_stack(stack, work_dir, env_vars)
        deployment = stack_obj.export_stack()
    except CommandError as exc:
        console.print(f"[bold red]✗[/bold red] Failed to read stack state: {exc}")
        raise typer.Exit(1) from exc

    data = deployment.deployment
    if not data:
        console.print("[dim]Stack has no state yet. Run [bold]cs up[/bold] to deploy.[/dim]")
        return

    resources = [r for r in data.get("resources", []) if r.get("type") != "pulumi:pulumi:Stack"]

    if not resources:
        console.print("[dim]No resources in stack state.[/dim]")
        return

    console.rule(f"[bold cyan]{work_dir.name}[/bold cyan] [dim]/ {stack}[/dim]", style="cyan dim")
    tree = Tree(f"[bold cyan]{work_dir.name}[/bold cyan] [dim]/ {stack}[/dim]")
    for r in resources:
        urn = r.get("urn", "")
        rtype = r.get("type", "")
        rid = r.get("id", "")
        label = _urn_label(urn) if urn else f"[magenta]{rtype}[/magenta]"
        node = tree.add(label)
        if rid:
            node.add(f"[dim]id:[/dim] [dim cyan]{rid}[/dim cyan]")

    console.print(tree)
    console.print(f"\n[dim]{len(resources)} resource(s)[/dim]")
