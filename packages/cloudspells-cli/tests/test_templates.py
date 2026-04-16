"""Tests for the spell template system."""

import yaml
from cloudspells.cli.templates import SPELL_REGISTRY, list_spells, render


def test_list_spells_returns_sorted_unique_names() -> None:
    spells = list_spells()
    assert "vcn" in spells
    assert "oke" in spells
    assert "compute" in spells
    assert spells == sorted(spells)
    assert len(spells) == len(set(spells))


def test_all_canonical_spells_have_registry_entry() -> None:
    for s in list_spells():
        assert s in SPELL_REGISTRY, f"Spell '{s}' missing from SPELL_REGISTRY"


def test_render_unknown_spell_raises_key_error() -> None:
    try:
        render("nonexistent-spell", "test", "dev")
        raise AssertionError("Expected KeyError")
    except KeyError:
        pass


def _assert_valid_render(spell: str) -> None:
    """Assert generated files are valid YAML / Python."""
    files = render(spell, f"test-{spell}", "dev")
    assert "Pulumi.yaml" in files
    assert "__main__.py" in files
    # Pulumi.yaml must be valid YAML with required keys.
    parsed = yaml.safe_load(files["Pulumi.yaml"])
    assert "name" in parsed
    assert "runtime" in parsed
    # __main__.py must be syntactically valid Python.
    compile(files["__main__.py"], "<string>", "exec")


def test_vcn_template() -> None:
    _assert_valid_render("vcn")


def test_compute_template() -> None:
    _assert_valid_render("compute")


def test_oke_template() -> None:
    _assert_valid_render("oke")


def test_autoscale_template() -> None:
    _assert_valid_render("autoscale")


def test_loadbalancer_template() -> None:
    _assert_valid_render("lb")


def test_bastion_template() -> None:
    _assert_valid_render("bastion")


def test_storage_template() -> None:
    _assert_valid_render("storage")


def test_iam_template() -> None:
    _assert_valid_render("iam")


def test_web_db_template() -> None:
    _assert_valid_render("web-db")


def test_vcn_template_embeds_name() -> None:
    files = render("vcn", "my-network", "dev")
    assert '"my-network"' in files["__main__.py"]


def test_vcn_template_has_compartment_key() -> None:
    files = render("vcn", "my-network", "dev")
    parsed = yaml.safe_load(files["Pulumi.yaml"])
    assert "compartment_ocid" in parsed["config"]


def test_oke_template_has_required_keys() -> None:
    files = render("oke", "my-cluster", "dev")
    parsed = yaml.safe_load(files["Pulumi.yaml"])
    config = parsed["config"]
    assert "compartment_ocid" in config
    assert "kubernetes_version" in config
    assert "node_image_id" in config


def test_storage_template_uses_pulumi_export() -> None:
    files = render("storage", "my-storage", "dev")
    assert "pulumi.export" in files["__main__.py"]


def test_iam_template_embeds_name_in_resources() -> None:
    files = render("iam", "my-iam", "dev")
    assert '"my-iam-app"' in files["__main__.py"]
    assert '"my-iam-ops"' in files["__main__.py"]


def test_web_db_template_has_nsg_roles() -> None:
    files = render("web-db", "my-app", "dev")
    assert "INTERNET_EDGE" in files["__main__.py"]
    assert "APP_SERVER" in files["__main__.py"]
    assert "DATABASE" in files["__main__.py"]


def test_loadbalancer_alias_works() -> None:
    files_lb = render("lb", "my-lb", "dev")
    files_loadbalancer = render("loadbalancer", "my-lb", "dev")
    assert files_lb == files_loadbalancer
