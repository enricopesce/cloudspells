"""CloudSpells spell template registry.

Provides the `SPELL_REGISTRY` dispatch table mapping spell identifiers to their
`render()` functions, plus `list_spells()` and the top-level `render()` helper
used by `cs new`.
"""

__all__ = ["SPELL_REGISTRY", "list_spells", "render"]

from collections.abc import Callable

from cloudspells.cli.templates.spells import (
    autoscale,
    bastion,
    compute,
    iam,
    loadbalancer,
    oke,
    storage,
    vcn,
    web_db,
)

#: Maps spell identifiers (including aliases) to their render functions.
SPELL_REGISTRY: dict[str, Callable[[str, str], dict[str, str]]] = {
    "vcn": vcn.render,
    "compute": compute.render,
    "oke": oke.render,
    "autoscale": autoscale.render,
    "lb": loadbalancer.render,
    "loadbalancer": loadbalancer.render,
    "bastion": bastion.render,
    "storage": storage.render,
    "iam": iam.render,
    "web-db": web_db.render,
}

#: Canonical names only (no aliases).
_CANONICAL: frozenset[str] = frozenset({
    "vcn",
    "compute",
    "oke",
    "autoscale",
    "lb",
    "bastion",
    "storage",
    "iam",
    "web-db",
})


def list_spells() -> list[str]:
    """Return the sorted canonical spell names (no aliases).

    Returns:
        Alphabetically sorted list of unique spell identifiers.
    """
    return sorted(_CANONICAL)


def render(spell: str, name: str, stack: str) -> dict[str, str]:
    """Dispatch a render call to the appropriate spell template.

    Args:
        spell: Spell identifier (e.g. `"vcn"`, `"oke"`, `"lb"`).
        name: Stack directory name used as the Pulumi project name.
        stack: Pulumi stack name (e.g. `"dev"`, `"prod"`).

    Returns:
        Dict with keys `"Pulumi.yaml"` and `"__main__.py"`, each mapping to
        the full generated file content as a string.

    Raises:
        KeyError: If `spell` is not a recognised spell identifier.
    """
    return SPELL_REGISTRY[spell](name, stack)
