"""Tests for the cs destroy command."""

from unittest.mock import MagicMock, patch

from cloudspells.cli.main import app


def _make_stack(result="succeeded"):
    mock = MagicMock()
    mock.destroy.return_value = MagicMock(
        summary=MagicMock(result=result, resource_changes={"-": 2}),
    )
    mock.workspace.list_plugins.return_value = []
    return mock


@patch("cloudspells.cli.commands.destroy.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.destroy.get_stack")
def test_destroy_tears_down_stack(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["destroy", str(stack_dir), "--yes"])
    assert result.exit_code == 0, result.output
    mock_stack.destroy.assert_called_once()


@patch("cloudspells.cli.commands.destroy.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.destroy.get_stack")
def test_destroy_remove_calls_remove_stack(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["destroy", str(stack_dir), "--yes", "--remove"])
    assert result.exit_code == 0, result.output
    mock_stack.workspace.remove_stack.assert_called_once()


@patch("cloudspells.cli.commands.destroy.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.destroy.get_stack")
def test_destroy_remove_warns_on_remove_failure(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_stack.workspace.remove_stack.side_effect = Exception("locked")
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["destroy", str(stack_dir), "--yes", "--remove"])
    assert result.exit_code == 0, result.output
    assert "stack state" in result.output


def test_destroy_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["destroy", str(tmp_path), "--yes"])
    assert result.exit_code != 0
    assert "Pulumi.yaml" in result.output


@patch("cloudspells.cli.commands.destroy.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.destroy.get_stack")
def test_destroy_exits_nonzero_on_command_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_get_stack.side_effect = CommandError("init failed")
    result = runner.invoke(app, ["destroy", str(stack_dir), "--yes"])
    assert result.exit_code != 0


@patch("cloudspells.cli.commands.destroy.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.destroy.get_stack")
def test_destroy_exits_nonzero_on_destroy_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_stack = _make_stack()
    mock_stack.destroy.side_effect = CommandError("resource failed")
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["destroy", str(stack_dir), "--yes"])
    assert result.exit_code != 0
