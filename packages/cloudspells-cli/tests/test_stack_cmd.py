"""Tests for the cs stack command group."""

from unittest.mock import MagicMock, patch

from cloudspells.cli.main import app


def _make_workspace(stacks: list | None = None):
    mock = MagicMock()
    mock.list_stacks.return_value = stacks or []
    mock.list_plugins.return_value = []
    return mock


def _make_stack_summary(name: str, resources: int = 3):
    s = MagicMock()
    s.name = name
    s.resource_count = resources
    s.last_update = "2025-01-01"
    s.update_in_progress = False
    return s


@patch("cloudspells.cli.commands.stack.get_workspace")
def test_stack_list_shows_stacks(mock_get_workspace, runner, stack_dir) -> None:
    ws = _make_workspace([
        _make_stack_summary("dev", 5),
        _make_stack_summary("prod", 12),
    ])
    mock_get_workspace.return_value = ws
    result = runner.invoke(app, ["stack", "list", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "dev" in result.output
    assert "prod" in result.output


@patch("cloudspells.cli.commands.stack.get_workspace")
def test_stack_list_empty(mock_get_workspace, runner, stack_dir) -> None:
    mock_get_workspace.return_value = _make_workspace([])
    result = runner.invoke(app, ["stack", "list", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "No stacks" in result.output


def test_stack_list_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["stack", "list", str(tmp_path)])
    assert result.exit_code != 0
    assert "Pulumi.yaml" in result.output


@patch("cloudspells.cli.commands.stack.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.stack.get_stack")
def test_stack_rm_removes_stack(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["stack", "rm", "dev", str(stack_dir), "--yes"])
    assert result.exit_code == 0, result.output
    mock_stack.workspace.remove_stack.assert_called_once_with("dev", force=False)


@patch("cloudspells.cli.commands.stack.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.stack.get_stack")
def test_stack_rm_force_flag(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["stack", "rm", "dev", str(stack_dir), "--yes", "--force"])
    assert result.exit_code == 0, result.output
    mock_stack.workspace.remove_stack.assert_called_once_with("dev", force=True)


@patch("cloudspells.cli.commands.stack.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.stack.get_stack")
def test_stack_rm_exits_nonzero_on_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_get_stack.side_effect = CommandError("not found")
    result = runner.invoke(app, ["stack", "rm", "dev", str(stack_dir), "--yes"])
    assert result.exit_code != 0


def test_stack_rm_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["stack", "rm", "dev", str(tmp_path), "--yes"])
    assert result.exit_code != 0
