"""Tests for the cs config command group."""

from unittest.mock import MagicMock, patch

from cloudspells.cli.main import app


def _make_stack(config: dict | None = None):
    mock = MagicMock()
    mock.workspace.list_plugins.return_value = []

    config = config or {}

    def _get_config(key: str):
        if key not in config:
            from pulumi.automation.errors import CommandError

            raise CommandError(f"key not found: {key}")
        return config[key]

    mock.get_config.side_effect = _get_config
    mock.get_all_config.return_value = config
    return mock


@patch("cloudspells.cli.commands.config.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.config.get_stack")
def test_config_set_calls_set_config(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["config", "set", "compartment_ocid", "ocid1.xxx", str(stack_dir)])
    assert result.exit_code == 0, result.output
    mock_stack.set_config.assert_called_once()
    key, cv = mock_stack.set_config.call_args[0]
    assert key == "compartment_ocid"
    assert cv.value == "ocid1.xxx"
    assert cv.secret is False


@patch("cloudspells.cli.commands.config.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.config.get_stack")
def test_config_set_secret_flag(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack()
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["config", "set", "db_password", "s3cr3t", "--secret", str(stack_dir)])
    assert result.exit_code == 0, result.output
    mock_stack.set_config.assert_called_once()
    key, cv = mock_stack.set_config.call_args[0]
    assert key == "db_password"
    assert cv.value == "s3cr3t"
    assert cv.secret is True
    assert "secret" in result.output


@patch("cloudspells.cli.commands.config.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.config.get_stack")
def test_config_get_prints_value(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation import ConfigValue

    cv = ConfigValue(value="ocid1.compartment", secret=False)
    mock_stack = _make_stack(config={"compartment_ocid": cv})
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["config", "get", "compartment_ocid", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "ocid1.compartment" in result.output


@patch("cloudspells.cli.commands.config.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.config.get_stack")
def test_config_get_secret_shows_redacted(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation import ConfigValue

    cv = ConfigValue(value="topsecret", secret=True)
    mock_stack = _make_stack(config={"db_password": cv})
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["config", "get", "db_password", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "[secret]" in result.output


@patch("cloudspells.cli.commands.config.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.config.get_stack")
def test_config_list_shows_table(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation import ConfigValue

    cfg = {
        "compartment_ocid": ConfigValue(value="ocid1.xxx", secret=False),
        "db_password": ConfigValue(value="s3cr3t", secret=True),
    }
    mock_stack = _make_stack(config=cfg)
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["config", "list", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "compartment_ocid" in result.output
    assert "db_password" in result.output


@patch("cloudspells.cli.commands.config.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.config.get_stack")
def test_config_list_json(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    import json

    from pulumi.automation import ConfigValue

    cfg = {"key": ConfigValue(value="val", secret=False)}
    mock_stack = _make_stack(config=cfg)
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["config", "list", "--json", str(stack_dir)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["key"] == "val"


@patch("cloudspells.cli.commands.config.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.config.get_stack")
def test_config_list_empty(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_stack = _make_stack(config={})
    mock_get_stack.return_value = mock_stack
    result = runner.invoke(app, ["config", "list", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "No configuration" in result.output


def test_config_set_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["config", "set", "key", "val", str(tmp_path)])
    assert result.exit_code != 0


def test_config_get_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["config", "get", "key", str(tmp_path)])
    assert result.exit_code != 0


def test_config_list_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["config", "list", str(tmp_path)])
    assert result.exit_code != 0
