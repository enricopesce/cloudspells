"""Tests for the cs project command group and project model."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cloudspells.cli.main import app
from cloudspells.cli.project.model import ProjectConfig, SpellRef

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_project_config_save_and_load(tmp_path: Path) -> None:
    project = ProjectConfig(
        name="my-prod",
        description="Production env",
        spells=[SpellRef(spell="vcn", name="my-prod-vcn"), SpellRef(spell="oke", name="my-prod-oke")],
    )
    yaml_path = tmp_path / "project.yaml"
    project.save(yaml_path)
    loaded = ProjectConfig.load(yaml_path)
    assert loaded.name == "my-prod"
    assert loaded.description == "Production env"
    assert len(loaded.spells) == 2
    assert loaded.spells[0].spell == "vcn"
    assert loaded.spells[1].name == "my-prod-oke"


def test_project_config_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ProjectConfig.load(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# cs project new
# ---------------------------------------------------------------------------


def test_project_new_creates_project_yaml(runner, tmp_path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["project", "new", "my-prod", "vcn", "oke"])
        assert result.exit_code == 0, result.output
        assert Path("my-prod/project.yaml").exists()


def test_project_new_creates_spell_dirs(runner, tmp_path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["project", "new", "env", "vcn", "storage"])
        assert result.exit_code == 0, result.output
        assert Path("env/env-vcn/Pulumi.yaml").exists()
        assert Path("env/env-storage/Pulumi.yaml").exists()


def test_project_new_unknown_spell_exits_nonzero(runner, tmp_path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["project", "new", "env", "nonexistent"])
        assert result.exit_code != 0
        assert "Unknown" in result.output


def test_project_new_no_spells_exits_nonzero(runner, tmp_path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["project", "new", "env"])
        assert result.exit_code != 0


def test_project_new_existing_dir_blocked_without_force(runner, tmp_path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("env").mkdir()
        result = runner.invoke(app, ["project", "new", "env", "vcn"])
        assert result.exit_code != 0
        assert "already exists" in result.output


def test_project_new_existing_dir_overwritten_with_force(runner, tmp_path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("env").mkdir()
        result = runner.invoke(app, ["project", "new", "env", "vcn", "--force"])
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# cs project up
# ---------------------------------------------------------------------------


def _project_dir(tmp_path: Path, name: str = "my-prod", spells: list[str] | None = None) -> Path:
    """Create a minimal project directory with project.yaml."""
    spells = spells or ["vcn"]
    d = tmp_path / name
    d.mkdir()
    project = ProjectConfig(
        name=name,
        spells=[SpellRef(spell=s, name=f"{name}-{s}") for s in spells],
    )
    project.save(d / "project.yaml")
    return d


@patch("cloudspells.cli.commands.project.resolve_passphrase", return_value={})
@patch("cloudspells.cli.project.runner.get_stack")
def test_project_up_deploys_all_spells(mock_get_stack, mock_passphrase, runner, tmp_path) -> None:
    proj_dir = _project_dir(tmp_path, spells=["vcn", "storage"])
    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []
    mock_get_stack.return_value = mock_stack

    result = runner.invoke(app, ["project", "up", str(proj_dir), "--yes"])
    assert result.exit_code == 0, result.output
    assert mock_stack.up.call_count == 2


@patch("cloudspells.cli.commands.project.resolve_passphrase", return_value={})
@patch("cloudspells.cli.project.runner.get_stack")
def test_project_up_preview_calls_preview(mock_get_stack, mock_passphrase, runner, tmp_path) -> None:
    proj_dir = _project_dir(tmp_path, spells=["vcn"])
    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []
    mock_get_stack.return_value = mock_stack

    result = runner.invoke(app, ["project", "up", str(proj_dir), "--preview"])
    assert result.exit_code == 0, result.output
    mock_stack.preview.assert_called_once()
    mock_stack.up.assert_not_called()


def test_project_up_exits_nonzero_when_no_project_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["project", "up", str(tmp_path), "--yes"])
    assert result.exit_code != 0
    assert "project.yaml" in result.output


# ---------------------------------------------------------------------------
# cs project destroy
# ---------------------------------------------------------------------------


@patch("cloudspells.cli.commands.project.resolve_passphrase", return_value={})
@patch("cloudspells.cli.project.runner.get_stack")
def test_project_destroy_destroys_in_reverse_order(mock_get_stack, mock_passphrase, runner, tmp_path) -> None:
    proj_dir = _project_dir(tmp_path, spells=["vcn", "oke"])

    # scaffold both spell dirs so destroy doesn't skip them
    for spell in ["vcn", "oke"]:
        spell_dir = proj_dir / f"my-prod-{spell}"
        spell_dir.mkdir(exist_ok=True)
        (spell_dir / "Pulumi.yaml").write_text(f"name: my-prod-{spell}\nruntime:\n  name: python\n")

    call_order: list[str] = []
    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []

    def _side_effect(stack_name, work_dir, env_vars):
        call_order.append(Path(work_dir).name)
        return mock_stack

    mock_get_stack.side_effect = _side_effect
    result = runner.invoke(app, ["project", "destroy", str(proj_dir), "--yes"])
    assert result.exit_code == 0, result.output
    assert call_order == ["my-prod-oke", "my-prod-vcn"]


def test_project_destroy_exits_nonzero_when_no_project_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["project", "destroy", str(tmp_path), "--yes"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# cs project status
# ---------------------------------------------------------------------------


@patch("cloudspells.cli.commands.project.resolve_passphrase", return_value={})
@patch("cloudspells.cli.project.runner.get_stack")
def test_project_status_shows_table(mock_get_stack, mock_passphrase, runner, tmp_path) -> None:
    proj_dir = _project_dir(tmp_path, spells=["vcn"])
    spell_dir = proj_dir / "my-prod-vcn"
    spell_dir.mkdir(exist_ok=True)
    (spell_dir / "Pulumi.yaml").write_text("name: my-prod-vcn\nruntime:\n  name: python\n")

    mock_stack = MagicMock()
    mock_stack.workspace.list_plugins.return_value = []
    mock_stack.export_stack.return_value = MagicMock(
        deployment={"resources": [{"type": "oci:Core/vcn:Vcn"}, {"type": "pulumi:pulumi:Stack"}]}
    )
    mock_get_stack.return_value = mock_stack

    result = runner.invoke(app, ["project", "status", str(proj_dir)])
    assert result.exit_code == 0, result.output
    assert "my-prod-vcn" in result.output
    assert "deployed" in result.output


def test_project_status_exits_nonzero_when_no_project_yaml(runner, tmp_path) -> None:
    result = runner.invoke(app, ["project", "status", str(tmp_path)])
    assert result.exit_code != 0
