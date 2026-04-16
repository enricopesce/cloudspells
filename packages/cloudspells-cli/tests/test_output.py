"""Tests for the cs output command."""

from unittest.mock import MagicMock, patch

from cloudspells.cli.main import app


def _make_outputs(data=None):
    """Build a mock outputs dict from plain {key: value} pairs."""
    result = {}
    for k, v in (data or {"endpoint": "https://example.com", "vcn_id": "ocid1.vcn.oc1.."}).items():
        out = MagicMock()
        out.value = v
        out.secret = False
        result[k] = out
    return result


@patch("cloudspells.cli.commands.output.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.output.get_stack")
def test_output_prints_table_for_all_outputs(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = MagicMock()
    mock_stack.outputs.return_value = _make_outputs()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["output", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "endpoint" in result.output
    assert "vcn_id" in result.output


@patch("cloudspells.cli.commands.output.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.output.get_stack")
def test_output_key_prints_raw_value(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = MagicMock()
    mock_stack.outputs.return_value = _make_outputs({"endpoint": "https://example.com"})
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["output", str(stack_dir), "--key", "endpoint"])
    assert result.exit_code == 0, result.output
    assert "https://example.com" in result.output


@patch("cloudspells.cli.commands.output.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.output.get_stack")
def test_output_key_missing_exits_nonzero(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = MagicMock()
    mock_stack.outputs.return_value = _make_outputs({"endpoint": "https://example.com"})
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["output", str(stack_dir), "--key", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("cloudspells.cli.commands.output.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.output.get_stack")
def test_output_json_emits_json(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    import json

    mock_stack = MagicMock()
    mock_stack.outputs.return_value = _make_outputs({"k": "v"})
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["output", str(stack_dir), "--json"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed == {"k": "v"}


@patch("cloudspells.cli.commands.output.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.output.get_stack")
def test_output_json_masks_secrets(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    import json

    secret_out = MagicMock()
    secret_out.value = "topsecret"
    secret_out.secret = True
    mock_stack = MagicMock()
    mock_stack.outputs.return_value = {"token": secret_out}
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["output", str(stack_dir), "--json"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["token"] == "[secret]"


@patch("cloudspells.cli.commands.output.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.output.get_stack")
def test_output_no_outputs_prints_message(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = MagicMock()
    mock_stack.outputs.return_value = {}
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["output", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "No outputs" in result.output


def test_output_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["output", str(tmp_path)])
    assert result.exit_code != 0
    assert "Pulumi.yaml" in result.output


@patch("cloudspells.cli.commands.output.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.output.get_stack")
def test_output_exits_nonzero_on_command_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_stack = MagicMock()
    mock_stack.outputs.side_effect = CommandError("no state")
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["output", str(stack_dir)])
    assert result.exit_code != 0
