"""Tests for the passphrase resolution module."""

import os
from unittest.mock import patch

from cloudspells.cli.automation.passphrase import resolve_passphrase


def test_returns_empty_when_passphrase_env_set() -> None:
    with patch.dict(os.environ, {"PULUMI_CONFIG_PASSPHRASE": "secret"}):
        result = resolve_passphrase()
    assert result == {}


def test_returns_empty_when_passphrase_file_env_set() -> None:
    clean_env = {k: v for k, v in os.environ.items() if k != "PULUMI_CONFIG_PASSPHRASE"}
    clean_env["PULUMI_CONFIG_PASSPHRASE_FILE"] = "/run/secret"
    with patch.dict(os.environ, clean_env, clear=True):
        result = resolve_passphrase()
    assert result == {}


def test_prompts_and_returns_dict_when_no_env() -> None:
    clean_env = {
        k: v for k, v in os.environ.items() if k not in ("PULUMI_CONFIG_PASSPHRASE", "PULUMI_CONFIG_PASSPHRASE_FILE")
    }
    with (
        patch.dict(os.environ, clean_env, clear=True),
        patch("cloudspells.cli.automation.passphrase.typer.prompt", return_value="mypass") as mock_prompt,
    ):
        result = resolve_passphrase()
    assert result == {"PULUMI_CONFIG_PASSPHRASE": "mypass"}
    mock_prompt.assert_called_once()
