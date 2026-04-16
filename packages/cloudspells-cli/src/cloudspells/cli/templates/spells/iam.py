"""IAM spell template — ComputeInstancePrincipal + CompartmentAdminGroup."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a ComputeInstancePrincipal + CompartmentAdminGroup stack scaffold.

    Args:
        name: Stack directory name and Pulumi project name.
        stack: Pulumi stack name (reserved for future use).

    Returns:
        Dict with `"Pulumi.yaml"` and `"__main__.py"` file contents.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells IAM stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("tenancy_ocid", "string", "OCI tenancy OCID"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells IAM stack — {name}."""

        from cloudspells.core import Config
        from cloudspells.providers.oci.iam import CompartmentAdminGroup, ComputeInstancePrincipal

        config = Config()
        compartment_id = config.require("compartment_ocid")
        tenancy_id = config.require("tenancy_ocid")

        app_principal = ComputeInstancePrincipal(
            name="{name}-app",
            compartment_id=compartment_id,
            tenancy_id=tenancy_id,
            grants=[
                "read secret-family",
                "read object-family",
            ],
        )

        ops_group = CompartmentAdminGroup(
            name="{name}-ops",
            compartment_id=compartment_id,
            tenancy_id=tenancy_id,
        )

        app_principal.export()
        ops_group.export()
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
