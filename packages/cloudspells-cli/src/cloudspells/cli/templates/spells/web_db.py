"""Web-DB spell template — VCN + 3 NSG roles + ComputeInstances (3-tier)."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a 3-tier web+DB stack with role-based NSG scaffold.

    Creates a VCN with three NSG roles (`INTERNET_EDGE`, `APP_SERVER`,
    `DATABASE`), one web and one database `ComputeInstance`, and the
    bilateral security rules that govern traffic between tiers.

    Args:
        name: Stack directory name and Pulumi project name.
        stack: Pulumi stack name (reserved for future use).

    Returns:
        Dict with `"Pulumi.yaml"` and `"__main__.py"` file contents.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells 3-tier web+DB stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("image_ocid", "string", "Boot image OCID"),
            ConfigKey("cidr_block", "string", "VCN CIDR block", default="10.0.0.0/18"),
            ConfigKey("ssh_key", "string", "SSH public key installed on all VMs"),
            ConfigKey("app_port", "string", "Application backend TCP port", default="8080"),
            ConfigKey("db_port", "string", "Database TCP port", default="5432"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells 3-tier web+DB stack — {name}."""

        from cloudspells.core import Config
        from cloudspells.providers.oci.compute import ComputeInstance
        from cloudspells.providers.oci.network import Vcn
        from cloudspells.providers.oci.nsg import Nsg
        from cloudspells.providers.oci.roles import APP_SERVER, DATABASE, INTERNET_EDGE

        config = Config()
        compartment_id = config.require("compartment_ocid")
        image_id = config.require("image_ocid")
        cidr_block = config.get("cidr_block") or "10.0.0.0/18"
        ssh_key = config.get("ssh_key")
        app_port = config.get_int("app_port") or 8080
        db_port = config.get_int("db_port") or 5432

        vcn = Vcn(
            name="{name}",
            compartment_id=compartment_id,
            cidr_block=cidr_block,
        )

        lb_nsg = Nsg("{name}-lb", role=INTERNET_EDGE, ports=[80, 443, 22], vcn=vcn, compartment_id=compartment_id)
        web_nsg = Nsg("{name}-web", role=APP_SERVER, vcn=vcn, compartment_id=compartment_id)
        db_nsg = Nsg("{name}-db", role=DATABASE, vcn=vcn, compartment_id=compartment_id)

        lb_nsg.serves(web_nsg, port=app_port)
        web_nsg.serves(db_nsg, port=db_port)

        web = ComputeInstance(
            name="{name}-web",
            compartment_id=compartment_id,
            vcn=vcn,
            image_id=image_id,
            ssh_public_key=ssh_key,
            nsg=web_nsg,
        )

        db = ComputeInstance(
            name="{name}-db",
            compartment_id=compartment_id,
            vcn=vcn,
            image_id=image_id,
            ssh_public_key=ssh_key,
            nsg=db_nsg,
        )

        vcn.export()
        web.export()
        db.export()
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
