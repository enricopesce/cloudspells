"""Exercise the wizard through the CLI with a mocked Pulumi backend."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cloudspells.cli.main import app
from pulumi.automation.errors import CommandError
from typer.testing import CliRunner


@pytest.fixture
def wizard_backend(mock_stack: MagicMock) -> Iterator[MagicMock]:
    """Intercept automation calls for all wizard actions."""
    with (
        patch("cloudspells.cli.automation.passphrase.resolve_passphrase", return_value={}),
        patch("cloudspells.cli.automation.workspace.get_stack", return_value=mock_stack) as get_stack,
    ):
        yield get_stack


@pytest.mark.parametrize(
    ("answers", "operation", "message"),
    [
        ("y\n", "preview", "Changes: +3"),
        ("n\ny\n", "up", "Deploy succeeded"),
        ("n\nn\n", "", "Cancelled. No changes applied."),
    ],
)
def test_deploy_modes(
    runner: CliRunner, stack_dir: Path, wizard_backend: MagicMock, answers: str, operation: str, message: str
) -> None:
    """Preview, deploy and cancellation dispatch to the expected operation."""
    result = runner.invoke(app, ["wizard"], input=f"2\n{stack_dir}\ndev\n{answers}")
    assert result.exit_code == 0, result.output
    assert message in result.output
    if operation:
        wizard_backend.assert_called_once_with("dev", stack_dir, {})
    else:
        wizard_backend.assert_not_called()
    assert wizard_backend.return_value.preview.call_count == (operation == "preview")
    assert wizard_backend.return_value.up.call_count == (operation == "up")


@pytest.mark.parametrize(
    ("failing_call", "message"),
    [
        ("init", "Failed to initialise stack"),
        ("up", "Deploy failed"),
    ],
)
def test_deploy_reports_backend_errors(
    runner: CliRunner, stack_dir: Path, wizard_backend: MagicMock, failing_call: str, message: str
) -> None:
    """Expose initialization and deployment failures in the wizard output."""
    failing_mock = wizard_backend if failing_call == "init" else wizard_backend.return_value.up
    failing_mock.side_effect = CommandError("backend unavailable")
    result = runner.invoke(app, ["wizard", "--no-banner"], input=f"2\n{stack_dir}\ndev\nn\ny\n")
    assert result.exit_code == 0, result.output
    assert message in result.output
    assert "backend unavailable" in result.output
    assert "Deploy succeeded" not in result.output


@pytest.mark.parametrize(
    ("deployment", "message"),
    [
        (None, "Stack has no state yet"),
        ({"resources": [{"type": "pulumi:pulumi:Stack"}]}, "No resources in stack state"),
    ],
)
def test_status_reports_empty_state(
    runner: CliRunner, stack_dir: Path, wizard_backend: MagicMock, deployment: dict | None, message: str
) -> None:
    """Distinguish undeployed stacks from empty deployed stacks."""
    wizard_backend.return_value.export_stack.return_value = SimpleNamespace(deployment=deployment)
    result = runner.invoke(app, ["wizard", "--no-banner"], input=f"3\n{stack_dir}\ndev\n")
    assert result.exit_code == 0, result.output
    assert message in result.output
    wizard_backend.assert_called_once_with("dev", stack_dir, {})


def test_status_lists_live_state_entries(runner: CliRunner, stack_dir: Path, wizard_backend: MagicMock) -> None:
    """Show resource names and IDs, with a type fallback for entries without a URN."""
    wizard_backend.return_value.export_stack.return_value = SimpleNamespace(
        deployment={
            "resources": [
                {"type": "pulumi:pulumi:Stack"},
                {"urn": "urn:pulumi:dev::lab::oci:Core/vcn:Vcn::lab-vcn", "id": "ocid1.vcn.test"},
                {"type": "oci:Core/subnet:Subnet"},
                {"urn": "legacy-resource"},
            ]
        },
    )
    result = runner.invoke(app, ["wizard", "--no-banner"], input=f"3\n{stack_dir}\ndev\n")
    assert result.exit_code == 0, result.output
    for marker in ("lab-vcn", "ocid1.vcn.test", "oci:Core/subnet:Subnet", "legacy-resource", "3 resource(s)"):
        assert marker in result.output
    assert "pulumi:pulumi:Stack" not in result.output


@pytest.mark.parametrize(("action", "operation", "confirmation"), [("4", "refresh", ""), ("5", "destroy", "y\n")])
@pytest.mark.parametrize("fails", [False, True])
def test_refresh_and_destroy_report_results(
    runner: CliRunner,
    stack_dir: Path,
    wizard_backend: MagicMock,
    action: str,
    operation: str,
    confirmation: str,
    fails: bool,
) -> None:
    """Stream progress and report the provider outcome for confirmed operations."""
    invoke = getattr(wizard_backend.return_value, operation)

    def run(*, on_output):
        on_output("Pulumi operation started\n")
        if fails:
            raise CommandError("backend unavailable")
        return SimpleNamespace(summary=SimpleNamespace(result="succeeded"))

    invoke.side_effect = run
    result = runner.invoke(app, ["wizard", "--no-banner"], input=f"{action}\n{stack_dir}\ndev\n{confirmation}")
    assert result.exit_code == 0, result.output
    assert "Pulumi operation started" in result.output
    assert f"{operation.title()} {'failed' if fails else 'complete'}" in result.output
    wizard_backend.assert_called_once_with("dev", stack_dir, {})
    invoke.assert_called_once()


@pytest.mark.parametrize("action", ["3", "4", "5"])
def test_existing_stack_actions_require_manifest(
    runner: CliRunner, tmp_path: Path, wizard_backend: MagicMock, action: str
) -> None:
    """Reject a folder without a stack manifest before connecting to Pulumi."""
    result = runner.invoke(app, ["wizard", "--no-banner"], input=f"{action}\n{tmp_path}\ndev\n")
    assert result.exit_code == 0, result.output
    assert "No Pulumi.yaml found" in result.output
    wizard_backend.assert_not_called()


@pytest.mark.parametrize("replace", [False, True])
def test_scaffold_existing_directory(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wizard_backend: MagicMock, replace: bool
) -> None:
    """Require overwrite confirmation and support previewing the regenerated project."""
    project = tmp_path / "lab"
    project.mkdir()
    manifest = project / "Pulumi.yaml"
    manifest.write_text("original\n")
    monkeypatch.chdir(tmp_path)
    responses = "y\ny\ndev\ny\n" if replace else "n\n"
    result = runner.invoke(app, ["wizard", "--no-banner"], input=f"1\n1\nlab\n{responses}")
    assert result.exit_code == 0, result.output
    if replace:
        assert "Stack scaffolded" in result.output
        assert "name: lab" in manifest.read_text()
        assert (project / "__main__.py").is_file()
        wizard_backend.return_value.preview.assert_called_once()
    else:
        assert "Cancelled." in result.output
        assert manifest.read_text() == "original\n"
        assert not (project / "__main__.py").exists()
        wizard_backend.assert_not_called()
