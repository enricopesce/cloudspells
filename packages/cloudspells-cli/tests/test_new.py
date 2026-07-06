"""Tests for the cs new command."""

from pathlib import Path

from cloudspells.cli.main import app
from cloudspells.cli.templates import list_spells


def test_new_vcn_creates_files(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "vcn", "test-vcn"])
    assert result.exit_code == 0, result.output
    assert Path("test-vcn/Pulumi.yaml").exists()
    assert Path("test-vcn/__main__.py").exists()


def test_new_list_flag_exits_zero_and_shows_spells(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "--list"])
    assert result.exit_code == 0
    assert "vcn" in result.output
    assert "oke" in result.output


def test_new_unknown_spell_exits_nonzero(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "nonexistent", "my-stack"])
    assert result.exit_code != 0
    assert "Unknown spell" in result.output


def test_new_missing_args_exits_nonzero(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new"])
    assert result.exit_code != 0


def test_new_existing_dir_blocked_without_force(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("test-vcn").mkdir()
    result = runner.invoke(app, ["new", "vcn", "test-vcn"])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_new_existing_dir_overwritten_with_force(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("test-vcn").mkdir()
    result = runner.invoke(app, ["new", "vcn", "test-vcn", "--force"])
    assert result.exit_code == 0
    assert Path("test-vcn/Pulumi.yaml").exists()


def test_new_prints_next_steps(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "vcn", "my-net"])
    assert result.exit_code == 0
    assert "cs up" in result.output


def test_new_all_spell_types(runner, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for spell in list_spells():
        safe_name = f"test-{spell.replace('-', '_')}"
        result = runner.invoke(app, ["new", spell, safe_name])
        assert result.exit_code == 0, f"Spell '{spell}' failed: {result.output}"
        assert Path(safe_name, "Pulumi.yaml").exists()
        assert Path(safe_name, "__main__.py").exists()


def test_new_backend_injects_backend_url(runner, tmp_path, monkeypatch) -> None:
    backend_url = "s3://my-bucket?endpoint=https://ns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com"
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "vcn", "test-vcn", "--backend", backend_url])
    assert result.exit_code == 0, result.output
    yaml_text = Path("test-vcn/Pulumi.yaml").read_text()
    assert "backend:" in yaml_text
    assert backend_url in yaml_text
