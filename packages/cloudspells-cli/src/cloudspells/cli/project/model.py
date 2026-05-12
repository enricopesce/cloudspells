"""CloudSpells project model — data classes for multi-spell projects.

A project is a named collection of spells deployed in declaration order.
The project manifest is stored as `project.yaml` in the project root directory.
"""

__all__ = ["ProjectConfig", "SpellRef"]

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SpellRef:
    """Reference to a single spell within a project.

    Attributes:
        spell: Spell type identifier (e.g. `"vcn"`, `"oke"`).
        name: Stack directory name for this spell instance.
    """

    spell: str
    name: str


@dataclass
class ProjectConfig:
    """Top-level project manifest loaded from `project.yaml`.

    Attributes:
        name: Project name (used as a label; not a Pulumi project name).
        description: Optional human-readable description.
        spells: Ordered list of spell references to deploy.

    Example:
        ```yaml
        name: my-production
        description: Production OCI environment
        spells:
          - spell: vcn
            name: prod-vcn
          - spell: oke
            name: prod-cluster
        ```
    """

    name: str
    description: str = ""
    spells: list[SpellRef] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        """Load a `ProjectConfig` from a `project.yaml` file.

        Args:
            path: Path to the `project.yaml` file.

        Returns:
            Populated `ProjectConfig` instance.

        Raises:
            FileNotFoundError: If `path` does not exist.
            yaml.YAMLError: If the file is not valid YAML.
            KeyError: If required top-level keys are missing.
        """
        data: dict[str, Any] = yaml.safe_load(path.read_text())
        spells = [SpellRef(spell=s["spell"], name=s["name"]) for s in data.get("spells", [])]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            spells=spells,
        )

    def save(self, path: Path) -> None:
        """Serialise this `ProjectConfig` to a `project.yaml` file.

        Args:
            path: Destination file path (created or overwritten).
        """
        data = {
            "name": self.name,
            "description": self.description,
            "spells": [{"spell": s.spell, "name": s.name} for s in self.spells],
        }
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
