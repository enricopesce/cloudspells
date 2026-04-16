"""Storage spell template — BackupBucket + DataLakeBucket."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a BackupBucket + DataLakeBucket stack scaffold.

    Args:
        name: Stack directory name and Pulumi project name.
        stack: Pulumi stack name (reserved for future use).

    Returns:
        Dict with `"Pulumi.yaml"` and `"__main__.py"` file contents.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells Object Storage stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("namespace", "string", "OCI tenancy object storage namespace"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells Object Storage stack — {name}."""

        import pulumi

        from cloudspells.core import Config
        from cloudspells.providers.oci.storage import BackupBucket, DataLakeBucket

        config = Config()
        compartment_id = config.require("compartment_ocid")
        namespace = config.require("namespace")

        backup = BackupBucket(
            name="{name}-backups",
            compartment_id=compartment_id,
            namespace=namespace,
        )

        lake = DataLakeBucket(
            name="{name}-lake",
            compartment_id=compartment_id,
            namespace=namespace,
        )

        pulumi.export("backup_bucket_name", backup.bucket_name)
        pulumi.export("lake_bucket_name", lake.bucket_name)
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
