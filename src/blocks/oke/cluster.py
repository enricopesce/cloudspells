import pulumi
import pulumi_oci as oci
from core.helper import Helper
from blocks.vcn.network import Vcn
from typing import Optional


class OkeCluster(pulumi.ComponentResource):
    def __init__(
        self,
        resource_name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn,
        kubernetes_version: pulumi.Input[str],
        shape: pulumi.Input[str],
        min_nodes: pulumi.Input[int],
        ocpus: pulumi.Input[float],
        memory_in_gbs: pulumi.Input[float],
        display_name: pulumi.Input[str],
        # optional parameters
        ssh_public_key: Optional[pulumi.Input[str]] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
        image: Optional[pulumi.Input[str]] = None,
    ):
        """
        This resource provides a complete OKE cluster infrastructure with all depending resources

        :param str resource_name: The name of the resource
        :param pulumi.ResourceOptions opts: Options for the resource.
        :param pulumi.Input[str] compartment_id: (Updatable) The [OCID](https://docs.cloud.oracle.com/iaas/Content/General/Concepts/identifiers.htm) of the compartment
        :param pulumi.Input[Mapping[str, Any]] defined_tags: (Updatable) Defined tags for this resource. Each key is predefined and scoped to a namespace. For more information, see [Resource Tags](https://docs.cloud.oracle.com/iaas/Content/General/Concepts/resourcetags.htm).  Example: `{"Operations.CostCenter": "42"}`
        :param pulumi.Input[str] oke_image: (Updatable) The [OCID](https://docs.cloud.oracle.com/iaas/Content/General/Concepts/identifiers.htm) of the image to use in the default cluster pool.
        :param pulumi.Input[str] display_name: (Updatable) A user-friendly name. Does not have to be unique, and it's changeable. Avoid entering confidential information.
        """
        super().__init__("oci:containerengine:Cluster", resource_name, {}, opts)
        h = Helper()

        self.display_name = display_name

        self.resource_name = resource_name
        self.compartment_id = compartment_id
        self.kubernetes_version = kubernetes_version

        # Create the OKE cluster
        self.cluster = oci.containerengine.Cluster(
            "Cluster",
            compartment_id=self.compartment_id,
            name=f"Cluster-{self.display_name}",
            kubernetes_version=self.kubernetes_version,
            options=oci.containerengine.ClusterOptionsArgs(
                service_lb_subnet_ids=[vcn.public_subnet.id],
                kubernetes_network_config=oci.containerengine.ClusterOptionsKubernetesNetworkConfigArgs(
                    pods_cidr="10.2.0.0/16",
                    services_cidr="10.3.0.0/16",
                ),
            ),
            cluster_pod_network_options=[
                oci.containerengine.ClusterClusterPodNetworkOptionArgs(
                    cni_type="OCI_VCN_IP_NATIVE",
                )
            ],
            type="BASIC_CLUSTER",
            vcn_id=vcn.id,
            endpoint_config=oci.containerengine.ClusterEndpointConfigArgs(
                subnet_id=vcn.public_subnet.id, is_public_ip_enabled=True
            ),
        )

        self.id = self.cluster.id

        if image is None:
            test_node_pool_option = oci.containerengine.get_node_pool_option_output(
                node_pool_option_id=self.cluster.id, compartment_id=self.compartment_id
            )

            c = test_node_pool_option.sources
            image_id = c.apply(
                lambda images: h.get_oke_image(images, shape, kubernetes_version)
            )
        else:
            image_id = image

        get_ad_names = oci.identity.get_availability_domains_output(
            compartment_id=self.compartment_id
        )
        ads = get_ad_names.availability_domains

        # Create a node pool
        self.node_pool = oci.containerengine.NodePool(
            "NodePool",
            name=f"NodePool-{self.display_name}",
            cluster_id=self.cluster.id,
            compartment_id=self.compartment_id,
            kubernetes_version=self.kubernetes_version,
            node_config_details=oci.containerengine.NodePoolNodeConfigDetailsArgs(
                placement_configs=ads.apply(
                    lambda ads: h.get_ads(ads, vcn.private_subnet.id)
                ),
                size=min_nodes,
                node_pool_pod_network_option_details=oci.containerengine.NodePoolNodeConfigDetailsNodePoolPodNetworkOptionDetailsArgs(
                    cni_type="OCI_VCN_IP_NATIVE", pod_subnet_ids=[vcn.private_subnet.id]
                ),
            ),
            node_shape=shape,
            node_shape_config=oci.containerengine.NodePoolNodeShapeConfigArgs(
                memory_in_gbs=memory_in_gbs, ocpus=ocpus
            ),
            node_source_details=oci.containerengine.NodePoolNodeSourceDetailsArgs(
                image_id=image_id,
                source_type="IMAGE",
            ),
            ssh_public_key=ssh_public_key if ssh_public_key else None,
        )

        self.register_outputs({})

    def create_kubeconfig(self, filename) -> None:
        cluster_kube_config = self.cluster.id.apply(
            lambda cid: oci.containerengine.get_cluster_kube_config(cluster_id=cid)
        )
        cluster_kube_config.content.apply(lambda cc: open(filename, "w+").write(cc))



