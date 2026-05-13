"""Compute spell template — VCN + single ComputeInstance."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a VCN + ComputeInstance stack scaffold.

    Args:
        name: Stack directory name and Pulumi project name.
        stack: Pulumi stack name (reserved for future use).

    Returns:
        Dict with `"Pulumi.yaml"` and `"__main__.py"` file contents.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells ComputeInstance stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("image_ocid", "string", "Boot image OCID"),
            ConfigKey("cidr_block", "string", "VCN CIDR block", default="10.0.0.0/18"),
            ConfigKey("ssh_key", "string", "SSH public key (auto-generated if omitted)"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells ComputeInstance stack — {name}."""

        from cloudspells.core import Config
        from cloudspells.providers.oci.compute import ComputeInstance
        from cloudspells.providers.oci.network import Vcn
        from cloudspells.providers.oci.nsg import Nsg
        from cloudspells.providers.oci.roles import APP_SERVER

        config = Config()
        compartment_id = config.require("compartment_ocid")
        image_id = config.require("image_ocid")
        cidr_block = config.get("cidr_block") or "10.0.0.0/18"
        ssh_key = config.get("ssh_key")

        vcn = Vcn(
            name="{name}",
            compartment_id=compartment_id,
            cidr_block=cidr_block,
        )
        app_nsg = Nsg("{name}-app", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)

        instance = ComputeInstance(
            name="{name}",
            compartment_id=compartment_id,
            image_id=image_id,
            nsg=app_nsg,
            ssh_public_key=ssh_key,
        )

        vcn.export()
        instance.export()
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
