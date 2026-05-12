"""Tests for the cs refresh command."""

from unittest.mock import MagicMock, patch

from cloudspells.cli.main import app


def _make_stack(result: str = "succeeded"):
    mock = MagicMock()
    mock.refresh.return_value = MagicMock(summary=MagicMock(result=result))
    mock.workspace.list_plugins.return_value = []
    return mock


@patch("cloudspells.cli.commands.refresh.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.refresh.get_stack")
def test_refresh_calls_refresh(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["refresh", str(stack_dir), "--yes"])
    assert result.exit_code == 0, result.output
    mock_stack.refresh.assert_called_once()


@patch("cloudspells.cli.commands.refresh.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.refresh.get_stack")
def test_refresh_shows_result(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack(result="succeeded")
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["refresh", str(stack_dir), "--yes"])
    assert result.exit_code == 0, result.output
    assert "succeeded" in result.output


def test_refresh_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["refresh", str(tmp_path), "--yes"])
    assert result.exit_code != 0
    assert "Pulumi.yaml" in result.output


@patch("cloudspells.cli.commands.refresh.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.refresh.get_stack")
def test_refresh_exits_nonzero_on_init_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_get_stack.side_effect = CommandError("init failed")
    result = runner.invoke(app, ["refresh", str(stack_dir), "--yes"])
    assert result.exit_code != 0


@patch("cloudspells.cli.commands.refresh.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.refresh.get_stack")
def test_refresh_exits_nonzero_on_refresh_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_stack = _make_stack()
    mock_stack.refresh.side_effect = CommandError("network error")
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["refresh", str(stack_dir), "--yes"])
    assert result.exit_code != 0
