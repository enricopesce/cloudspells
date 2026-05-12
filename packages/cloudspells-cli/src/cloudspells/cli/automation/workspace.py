"""Pulumi Automation API workspace factory.

Provides `get_stack` and `get_workspace`, the entry points used by all
operation commands to obtain a configured, plugin-ready Pulumi `Stack` or
`LocalWorkspace` backed by a file-based program in `work_dir`.
"""

__all__ = ["get_stack", "get_workspace"]

from pathlib import Path
from typing import Any

from pulumi.automation import (
    CommandError,
    LocalWorkspace,
    LocalWorkspaceOptions,
    Stack,
    create_or_select_stack,
)

#: OCI Pulumi resource plugin version to install when not already present.
_OCI_PLUGIN_VERSION = "v3.9.0"


def get_workspace(
    work_dir: Path,
    env_vars: dict[str, str] | None = None,
) -> LocalWorkspace:
    """Return a bare `LocalWorkspace` for `work_dir` without selecting a stack.

    Useful for operations that operate at the workspace level rather than a
    specific stack, such as listing stacks (`workspace.list_stacks()`).

    Args:
        work_dir: Path to the project directory containing `Pulumi.yaml`.
        env_vars: Optional environment variables to inject into every Pulumi
            command executed by the workspace.

    Returns:
        Configured `LocalWorkspace` with the OCI plugin ensured.
    """
    ws = LocalWorkspace(work_dir=str(work_dir), env_vars=env_vars or {})
    _ensure_oci_plugin(ws)
    return ws


def get_stack(
    stack_name: str,
    work_dir: Path,
    env_vars: dict[str, str] | None = None,
) -> Stack:
    """Create or select a file-based Pulumi stack in `work_dir`.

    Args:
        stack_name: Pulumi stack name (e.g. `"dev"`, `"prod"`).
        work_dir: Path to the stack directory containing `Pulumi.yaml`.
        env_vars: Optional environment variables to inject into every Pulumi
            command executed by the workspace — typically the config
            passphrase returned by `resolve_passphrase()`.

    Returns:
        Pulumi `Stack` ready for `up`, `preview`, `destroy`, and `outputs`
        operations.

    Raises:
        automation.CommandError: If the Pulumi CLI fails to create or select
            the stack.
    """
    opts = LocalWorkspaceOptions(env_vars=env_vars or {})
    stack = create_or_select_stack(
        stack_name=stack_name,
        work_dir=str(work_dir),
        opts=opts,
    )
    _ensure_oci_plugin(stack.workspace)
    return stack


def _ensure_oci_plugin(workspace: Any) -> None:
    """Install the OCI Pulumi resource plugin when not already present.

    Best-effort: if plugin listing or installation fails (e.g. network error),
    the error is silently swallowed. The subsequent `stack.up()` call will
    attempt its own plugin resolution.

    Args:
        workspace: Pulumi `LocalWorkspace` instance attached to the stack.
    """
    try:
        installed_names = {p.name for p in workspace.list_plugins()}
        if "oci" not in installed_names:
            workspace.install_plugin("oci", _OCI_PLUGIN_VERSION)
    except CommandError:
        pass
