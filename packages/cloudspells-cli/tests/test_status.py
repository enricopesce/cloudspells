"""Tests for the cs status command."""

from unittest.mock import MagicMock, patch

from cloudspells.cli.main import app


def _make_stack(resources: list | None = None, empty: bool = False):
    mock = MagicMock()
    mock.workspace.list_plugins.return_value = []

    if empty:
        mock.export_stack.return_value = MagicMock(deployment=None)
    else:
        all_resources = (
            resources
            if resources is not None
            else [
                {
                    "urn": "urn:pulumi:dev::my-vcn::oci:Core/vcn:Vcn::my-vcn-vcn",
                    "type": "oci:Core/vcn:Vcn",
                    "id": "ocid1.vcn.xxx",
                },
                {
                    "urn": "urn:pulumi:dev::my-vcn::oci:Core/subnet:Subnet::my-vcn-subnet",
                    "type": "oci:Core/subnet:Subnet",
                    "id": "ocid1.subnet.xxx",
                },
                {
                    "urn": "urn:pulumi:dev::my-vcn::pulumi:pulumi:Stack::my-vcn-dev",
                    "type": "pulumi:pulumi:Stack",
                    "id": "",
                },
            ]
        )
        mock.export_stack.return_value = MagicMock(deployment={"resources": all_resources})
    return mock


@patch("cloudspells.cli.commands.status.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.status.get_stack")
def test_status_shows_resources(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_get_stack.return_value = _make_stack()
    result = runner.invoke(app, ["status", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "oci:Core/vcn:Vcn" in result.output
    assert "ocid1.vcn.xxx" in result.output


@patch("cloudspells.cli.commands.status.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.status.get_stack")
def test_status_filters_pulumi_stack_resource(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_get_stack.return_value = _make_stack()
    result = runner.invoke(app, ["status", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "2 resource" in result.output


@patch("cloudspells.cli.commands.status.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.status.get_stack")
def test_status_empty_deployment(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_get_stack.return_value = _make_stack(empty=True)
    result = runner.invoke(app, ["status", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "no state" in result.output.lower() or "cs up" in result.output


@patch("cloudspells.cli.commands.status.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.status.get_stack")
def test_status_no_resources(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    mock_get_stack.return_value = _make_stack(resources=[])
    result = runner.invoke(app, ["status", str(stack_dir)])
    assert result.exit_code == 0, result.output
    assert "No resources" in result.output


def test_status_exits_nonzero_when_no_pulumi_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["status", str(tmp_path)])
    assert result.exit_code != 0
    assert "Pulumi.yaml" in result.output


@patch("cloudspells.cli.commands.status.resolve_passphrase", return_value={})
@patch("cloudspells.cli.commands.status.get_stack")
def test_status_exits_nonzero_on_error(mock_get_stack, mock_passphrase, runner, stack_dir) -> None:
    from pulumi.automation.errors import CommandError

    mock_get_stack.side_effect = CommandError("init failed")
    result = runner.invoke(app, ["status", str(stack_dir)])
    assert result.exit_code != 0
