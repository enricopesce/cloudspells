"""Shared Pulumi.yaml generator for CloudSpells spell templates.

Provides the `ConfigKey` dataclass and `pulumi_yaml()` helper used by every
spell template module to produce a consistently structured `Pulumi.yaml`.
"""

__all__ = ["ConfigKey", "pulumi_yaml"]

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfigKey:
    """Definition of a single Pulumi stack config key.

    Attributes:
        name: Config key identifier (e.g. `"compartment_ocid"`).
        type: Pulumi config value type — `"string"`, `"int"`, or `"boolean"`.
        description: Short description shown in `Pulumi.yaml` comments and
            `pulumi config` output.
        default: Optional default value emitted as `default:` in the YAML.
            `None` omits the field entirely (key is required at deploy time).
    """

    name: str
    type: str
    description: str
    default: Any = field(default=None)


def pulumi_yaml(project_name: str, description: str, config_keys: list[ConfigKey]) -> str:
    """Generate a `Pulumi.yaml` string for a CloudSpells stack.

    Produces the standard project header (`name`, `runtime`, `description`)
    followed by a `config:` block with one entry per key.

    Args:
        project_name: Pulumi project name — typically the stack directory name
            (kebab-case).
        description: One-line project description embedded in the YAML.
        config_keys: Ordered list of config key definitions.  Keys without a
            `default` are treated as required by the Pulumi CLI.

    Returns:
        Formatted `Pulumi.yaml` content as a string, terminated by a newline.

    Example:
        ```python
        yaml = pulumi_yaml(
            "my-vcn",
            "CloudSpells VCN stack",
            [ConfigKey("compartment_ocid", "string", "OCI compartment OCID")],
        )
        ```
    """
    lines = [
        f"name: {project_name}",
        "runtime:",
        "  name: python",
        f"description: {description}",
    ]
    if config_keys:
        lines.append("config:")
        for key in config_keys:
            lines.append(f"  {key.name}:")
            lines.append(f"    type: {key.type}")
            lines.append(f"    description: {key.description}")
            if key.default is not None:
                if isinstance(key.default, str):
                    lines.append(f'    default: "{key.default}"')
                else:
                    lines.append(f"    default: {key.default}")
    return "\n".join(lines) + "\n"
