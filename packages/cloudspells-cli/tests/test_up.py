"""Tests for the cs up command."""

from unittest.mock import MagicMock, patch

from cloudspells.cli.main import app


def _make_stack(result="succeeded", changes=None, preview_changes=None):
    mock = MagicMock()
    mock.up.return_value = MagicMock(
        summary=MagicMock(result=result, resource_changes=changes or {"+": 2}),
    )
    mock.preview.return_value = MagicMock(change_summary=preview_changes or {"+": 2})
    mock.workspace.list_plugins.return_value = []
    return mock


@patch("cloudspells.cli.commands.up.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.up.get_stack")
def test_up_deploys_stack(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["up", str(stack_dir), "--yes"])
    assert result.exit_code == 0, result.output
    mock_stack.up.assert_called_once()


@patch("cloudspells.cli.commands.up.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.up.get_stack")
def test_up_preview_calls_preview(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["up", str(stack_dir), "--preview"])
    assert result.exit_code == 0, result.output
    mock_stack.preview.assert_called_once()
    mock_stack.up.assert_not_called()


@patch("cloudspells.cli.commands.up.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.up.get_stack")
def test_up_shows_changes_in_output(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack(changes={"+": 3, "-": 1})
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["up", str(stack_dir), "--yes"])
    assert result.exit_code == 0, result.output
    assert "+3" in result.output
    assert "-1" in result.output


def test_up_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["up", str(tmp_path)])
    assert result.exit_code != 0
    assert "Pulumi.yaml" in result.output


@patch("cloudspells.cli.commands.up.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.up.get_stack")
def test_up_exits_nonzero_on_command_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_get_stack.side_effect = CommandError("stack init failed")
    result = runner.invoke(app, ["up", str(stack_dir), "--yes"])
    assert result.exit_code != 0


@patch("cloudspells.cli.commands.up.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.up.get_stack")
def test_up_exits_nonzero_on_up_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_stack = _make_stack()
    mock_stack.up.side_effect = CommandError("resource failed")
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["up", str(stack_dir), "--yes"])
    assert result.exit_code != 0


@patch("cloudspells.cli.commands.up.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.up.get_stack")
def test_up_preview_exits_nonzero_on_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_stack = _make_stack()
    mock_stack.preview.side_effect = CommandError("preview failed")
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["up", str(stack_dir), "--preview"])
    assert result.exit_code != 0
