"""LoadBalancer spell template — VCN + internet-facing HTTPS load balancer."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a VCN + LoadBalancer stack scaffold.

    Args:
        name: Stack directory name and Pulumi project name.
        stack: Pulumi stack name (reserved for future use).

    Returns:
        Dict with `"Pulumi.yaml"` and `"__main__.py"` file contents.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells LoadBalancer stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("certificate_name", "string", "TLS certificate name pre-uploaded to OCI"),
            ConfigKey("cidr_block", "string", "VCN CIDR block", default="10.0.0.0/18"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells LoadBalancer stack — {name}."""

        from cloudspells.core import Config
        from cloudspells.providers.oci.loadbalancer import LoadBalancer
        from cloudspells.providers.oci.network import Vcn

        config = Config()
        compartment_id = config.require("compartment_ocid")
        certificate_name = config.require("certificate_name")
        cidr_block = config.get("cidr_block") or "10.0.0.0/18"

        vcn = Vcn(
            name="{name}",
            compartment_id=compartment_id,
            cidr_block=cidr_block,
        )

        lb = LoadBalancer(
            name="{name}",
            compartment_id=compartment_id,
            vcn=vcn,
            certificate_name=certificate_name,
        )

        vcn.export()
        lb.export()
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
