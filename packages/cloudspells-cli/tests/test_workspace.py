"""Tests for the workspace factory module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from cloudspells.cli.automation import workspace as ws_mod
from cloudspells.cli.automation.workspace import get_stack


def test_get_stack_creates_stack_and_ensures_plugin(tmp_path: Path) -> None:
    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []
    with patch("cloudspells.cli.automation.workspace.create_or_select_stack", return_value=mock_stack) as mock_create:
        result = get_stack("dev", tmp_path, {"PULUMI_CONFIG_PASSPHRASE": "x"})
    assert result is mock_stack
    mock_create.assert_called_once()


def test_get_stack_uses_empty_env_vars_when_none(tmp_path: Path) -> None:
    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []
    with patch("cloudspells.cli.automation.workspace.create_or_select_stack", return_value=mock_stack) as mock_create:
        get_stack("dev", tmp_path)
    call_opts = mock_create.call_args[1]["opts"]
    assert call_opts.env_vars == {}


def test_ensure_oci_plugin_installs_when_missing() -> None:
    ws = MagicMock()
    ws.list_plugins.return_value = []
    ws_mod._ensure_oci_plugin(ws)
    ws.install_plugin.assert_called_once_with("oci", "v3.9.0")


def test_ensure_oci_plugin_skips_when_already_present() -> None:
    ws = MagicMock()
    existing = MagicMock()
    existing.name = "oci"
    ws.list_plugins.return_value = [existing]
    ws_mod._ensure_oci_plugin(ws)
    ws.install_plugin.assert_not_called()


def test_ensure_oci_plugin_swallows_command_error() -> None:
    from pulumi.automation import CommandError

    ws = MagicMock()
    ws.list_plugins.side_effect = CommandError.__new__(CommandError)
    ws_mod._ensure_oci_plugin(ws)  # Must not raise
