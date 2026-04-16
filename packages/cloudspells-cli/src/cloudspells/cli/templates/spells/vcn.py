"""VCN spell template — standalone Virtual Cloud Network."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a VCN stack scaffold.

    Args:
        name: Stack directory name used as the Pulumi project name and the
            `Vcn` resource name in the generated program.
        stack: Pulumi stack name (unused in generated content; reserved for
            future use in comments or init steps).

    Returns:
        Dict with keys `"Pulumi.yaml"` and `"__main__.py"`, each mapping to
        the generated file content as a string.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells VCN stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("cidr_block", "string", "VCN CIDR block", default="10.0.0.0/18"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells VCN stack — {name}."""

        from cloudspells.core import Config
        from cloudspells.providers.oci.network import Vcn

        config = Config()
        compartment_id = config.require("compartment_ocid")
        cidr_block = config.get("cidr_block") or "10.0.0.0/18"

        vcn = Vcn(
            name="{name}",
            compartment_id=compartment_id,
            cidr_block=cidr_block,
        )
        vcn.export()
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
