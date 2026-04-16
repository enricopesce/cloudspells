"""OKE spell template — VCN + OkeCluster."""

__all__ = ["render"]

import textwrap

from cloudspells.cli.templates.base import ConfigKey, pulumi_yaml


def render(name: str, _stack: str) -> dict[str, str]:
    """Render a VCN + OkeCluster stack scaffold.

    Args:
        name: Stack directory name and Pulumi project name.
        stack: Pulumi stack name (reserved for future use).

    Returns:
        Dict with `"Pulumi.yaml"` and `"__main__.py"` file contents.
    """
    yaml = pulumi_yaml(
        project_name=name,
        description="CloudSpells OkeCluster stack",
        config_keys=[
            ConfigKey("compartment_ocid", "string", "OCI compartment OCID"),
            ConfigKey("kubernetes_version", "string", 'Kubernetes version (e.g. "v1.32.1")'),
            ConfigKey("node_image_id", "string", "Boot image OCID for node pool instances"),
            ConfigKey("node_shape", "string", "Node compute shape", default="VM.Standard.A1.Flex"),
            ConfigKey("node_count", "string", "Number of nodes in the pool", default="2"),
            ConfigKey("ocpus", "string", "OCPUs per node", default="2"),
            ConfigKey("memory_in_gbs", "string", "Memory GiB per node", default="12"),
        ],
    )
    main = textwrap.dedent(f'''\
        """CloudSpells OkeCluster stack — {name}."""

        from cloudspells.core import Config
        from cloudspells.providers.oci.kubernetes import NodePoolConfig, OkeCluster
        from cloudspells.providers.oci.network import Vcn

        config = Config()
        compartment_id = config.require("compartment_ocid")
        kubernetes_version = config.require("kubernetes_version")
        node_image_id = config.require("node_image_id")
        node_shape = config.get("node_shape") or "VM.Standard.A1.Flex"
        node_count = config.get_int("node_count") or 2
        ocpus = config.get_int("ocpus") or 2
        memory_in_gbs = config.get_int("memory_in_gbs") or 12

        vcn = Vcn(
            name="{name}",
            compartment_id=compartment_id,
        )

        cluster = OkeCluster(
            name="{name}",
            compartment_id=compartment_id,
            vcn=vcn,
            kubernetes_version=kubernetes_version,
            node_pools=[
                NodePoolConfig(
                    name="workers",
                    shape=node_shape,
                    image=node_image_id,
                    node_count=node_count,
                    ocpus=ocpus,
                    memory_in_gbs=memory_in_gbs,
                )
            ],
        )

        vcn.export()
        cluster.export()
    ''')
    return {"Pulumi.yaml": yaml, "__main__.py": main}
