"""Autoscale spell template — VCN + ScalableWorkload."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a VCN + ScalableWorkload stack scaffold.

    Args:
        name: Stack directory name and Pulumi project name.
        stack: Pulumi stack name (reserved for future use).

    Returns:
        Dict with `"Pulumi.yaml"` and `"__main__.py"` file contents.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells ScalableWorkload stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("image_ocid", "string", "Boot image OCID for pool instances"),
            ConfigKey("cidr_block", "string", "VCN CIDR block", default="10.0.0.0/18"),
            ConfigKey("ssh_key", "string", "SSH public key installed on pool instances"),
            ConfigKey("max_instances", "string", "Maximum pool size for autoscaling", default="5"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells ScalableWorkload stack — {name}."""

        from cloudspells.core import Config
        from cloudspells.providers.oci.autoscale import ScalableWorkload
        from cloudspells.providers.oci.network import Vcn

        config = Config()
        compartment_id = config.require("compartment_ocid")
        image_id = config.require("image_ocid")
        cidr_block = config.get("cidr_block") or "10.0.0.0/18"
        ssh_key = config.get("ssh_key")
        max_instances = config.get_int("max_instances") or 5

        vcn = Vcn(
            name="{name}",
            compartment_id=compartment_id,
            cidr_block=cidr_block,
        )

        workload = ScalableWorkload(
            name="{name}",
            compartment_id=compartment_id,
            vcn=vcn,
            image_id=image_id,
            ssh_public_key=ssh_key,
            max_instances=max_instances,
        )

        vcn.export()
        workload.export()
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
