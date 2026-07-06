"""Tests for the cs wizard interactive command and supporting modules."""

from pathlib import Path
from unittest.mock import patch

from cloudspells.cli.main import app
from cloudspells.cli.theme import SPELL_LORE, fmt_changes

# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------


def test_fmt_changes_with_additions() -> None:
    assert "+3" in fmt_changes({"+": 3})


def test_fmt_changes_with_all_symbols() -> None:
    result = fmt_changes({"+": 1, "~": 2, "-": 1, "=": 5})
    assert "+1" in result
    assert "~2" in result
    assert "-1" in result


def test_fmt_changes_empty_returns_no_changes() -> None:
    assert fmt_changes({}) == "no changes"


def test_spell_lore_covers_all_canonical_spells() -> None:
    from cloudspells.cli.templates import list_spells

    for spell in list_spells():
        assert spell in SPELL_LORE, f"Missing lore for spell '{spell}'"


def test_spell_lore_has_required_fields() -> None:
    for key, lore in SPELL_LORE.items():
        assert "glyph" in lore, f"'{key}' missing glyph"
        assert "name" in lore, f"'{key}' missing name"
        assert "lore" in lore, f"'{key}' missing lore"


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def test_banner_markup_contains_cloudspells() -> None:
    from cloudspells.cli.banner import BANNER_MARKUP

    # Banner renders with spaced letters: "C L O U D S P E L L S"
    assert "C L O U D S P E L L S" in BANNER_MARKUP


def test_print_banner_does_not_raise(tmp_path, monkeypatch) -> None:
    from cloudspells.cli.banner import print_banner

    monkeypatch.chdir(tmp_path)
    print_banner()


# ---------------------------------------------------------------------------
# cs wizard — action menu
# ---------------------------------------------------------------------------


@patch("cloudspells.cli.commands.wizard.print_banner")
@patch("cloudspells.cli.commands.wizard.Confirm.ask", return_value=False)
@patch("cloudspells.cli.commands.wizard.Prompt.ask", side_effect=["1", "1", "my-vcn"])
def test_wizard_new_spell_creates_files(mock_prompt, mock_confirm, mock_banner, runner, tmp_path, monkeypatch) -> None:
    """Action 1 → spell 1 (vcn) → name 'my-vcn' → decline deploy."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["wizard", "--no-banner"])
    assert result.exit_code == 0, result.output
    assert Path("my-vcn/Pulumi.yaml").exists()
    assert Path("my-vcn/__main__.py").exists()


@patch("cloudspells.cli.commands.wizard.print_banner")
@patch("cloudspells.cli.commands.wizard.Prompt.ask", side_effect=["6"])
def test_wizard_project_reference_prints_commands(mock_prompt, mock_banner, runner, tmp_path, monkeypatch) -> None:
    """Action 6 → prints project command reference."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["wizard", "--no-banner"])
    assert result.exit_code == 0, result.output
    assert "cs project" in result.output


@patch("cloudspells.cli.commands.wizard.print_banner")
@patch("cloudspells.cli.commands.wizard.Confirm.ask", return_value=False)
@patch("cloudspells.cli.commands.wizard.Prompt.ask", side_effect=["5", ".", "dev"])
def test_wizard_destroy_cancel_prints_message(
    mock_prompt, mock_confirm, mock_banner, runner, tmp_path, monkeypatch
) -> None:
    """Action 5 → path='.' (CWD has Pulumi.yaml) → confirm=False → 'Wise restraint'."""
    monkeypatch.chdir(tmp_path)
    Path("Pulumi.yaml").write_text("name: test\nruntime:\n  name: python\n")
    result = runner.invoke(app, ["wizard", "--no-banner"])
    assert result.exit_code == 0, result.output
    assert "cancelled" in result.output.lower()


@patch("cloudspells.cli.commands.wizard.print_banner")
@patch("cloudspells.cli.commands.wizard.Prompt.ask", side_effect=["2", ".", "dev", "no"])
@patch("cloudspells.cli.commands.wizard.Confirm.ask", return_value=False)
def test_wizard_deploy_cancel_on_no_pulumi_yaml(
    mock_confirm, mock_prompt, mock_banner, runner, tmp_path, monkeypatch
) -> None:
    """Action 2 → missing Pulumi.yaml → graceful error, no crash."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["wizard", "--no-banner"])
    assert result.exit_code == 0, result.output
    assert "Pulumi.yaml" in result.output
