"""Pulumi config passphrase detection and interactive prompt.

Pulumi local state backends encrypt the state file with a passphrase.
This module resolves the passphrase from the environment (the standard
`PULUMI_CONFIG_PASSPHRASE` / `PULUMI_CONFIG_PASSPHRASE_FILE` variables) and
prompts the user interactively when neither is set.
"""

__all__ = ["resolve_passphrase"]

import os

import typer


def resolve_passphrase() -> dict[str, str]:
    """Return env-var dict with passphrase set, prompting if necessary.

    Checks for `PULUMI_CONFIG_PASSPHRASE` or `PULUMI_CONFIG_PASSPHRASE_FILE`
    environment variables. If neither is present, prompts the user via a
    hidden-input TTY prompt and returns the value as an env-var dict to inject
    into the Pulumi workspace.

    Returns:
        Empty dict when the passphrase is already available in the environment,
        or `{"PULUMI_CONFIG_PASSPHRASE": value}` when obtained interactively.
    """
    if os.environ.get("PULUMI_CONFIG_PASSPHRASE"):
        return {}
    if os.environ.get("PULUMI_CONFIG_PASSPHRASE_FILE"):
        return {}
    passphrase: str = typer.prompt(
        "Pulumi config passphrase (set PULUMI_CONFIG_PASSPHRASE to skip)",
        hide_input=True,
    )
    return {"PULUMI_CONFIG_PASSPHRASE": passphrase}
