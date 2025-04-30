import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from core.helper import Helper
from blocks.vcn.network import Vcn
from typing import Optional


class OkeCluster(BaseResource):
    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn,
        kubernetes_version: pulumi.Input[str],
        shape: pulumi.Input[str],
        min_nodes: pulumi.Input[int],
        ocpus: pulumi.Input[float],
        memory_in_gbs: pulumi.Input[float],
        display_name: pulumi.Input[str],
        stack_name: str,
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
        super().__init__("custom:oke:Cluster", name, compartment_id, stack_name, opts)

        h = Helper()

        self.display_name = display_name

        self.name = name
        self.vcn = vcn
        self.compartment_id = compartment_id
        self.kubernetes_version = kubernetes_version

        self._create_security_lists()

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
            vcn_id=self.vcn.id,
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
            image_id = c.apply(lambda images: h.get_oke_image(images, shape, kubernetes_version))
        else:
            image_id = image

        get_ad_names = oci.identity.get_availability_domains_output(compartment_id=self.compartment_id)
        ads = get_ad_names.availability_domains

        # Create a node pool
        self.node_pool = oci.containerengine.NodePool(
            "NodePool",
            name=f"NodePool-{self.display_name}",
            cluster_id=self.cluster.id,
            compartment_id=self.compartment_id,
            kubernetes_version=self.kubernetes_version,
            node_config_details=oci.containerengine.NodePoolNodeConfigDetailsArgs(
                placement_configs=ads.apply(lambda ads: h.get_ads(ads, vcn.private_subnet.id)),
                size=min_nodes,
                node_pool_pod_network_option_details=oci.containerengine.NodePoolNodeConfigDetailsNodePoolPodNetworkOptionDetailsArgs(
                    cni_type="OCI_VCN_IP_NATIVE", pod_subnet_ids=[vcn.private_subnet.id]
                ),
            ),
            node_shape=shape,
            node_shape_config=oci.containerengine.NodePoolNodeShapeConfigArgs(memory_in_gbs=memory_in_gbs, ocpus=ocpus),
            node_source_details=oci.containerengine.NodePoolNodeSourceDetailsArgs(
                image_id=image_id,
                source_type="IMAGE",
            ),
            ssh_public_key=ssh_public_key if ssh_public_key else None,
        )

        self.register_outputs({})

    def _create_security_lists(self):
        # Create a separate Security List for the Public Subnet
        public_security_list = oci.core.SecurityList(
            "PublicSecurityList",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name="PublicSecurityList",
            ingress_security_rules=[
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Kubernetes worker to Kubernetes API endpoint communication.",
                    protocol="6",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=6443,
                        min=6443,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Kubernetes worker to Kubernetes API endpoint communication.",
                    protocol="6",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=12250,
                        min=12250,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Path discovery",
                    icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                        code=4,
                        type=3,
                    ),
                    protocol="1",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Pod to Kubernetes API endpoint communication (when using VCN-native pod networking).",
                    protocol="6",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=6443,
                        min=6443,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Pod to Kubernetes API endpoint communication (when using VCN-native pod networking).",
                    protocol="6",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=12250,
                        min=12250,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="External access to Kubernetes API endpoint.",
                    protocol="6",
                    source="0.0.0.0/0",
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=6443,
                        min=6443,
                    ),
                ),
            ],
            egress_security_rules=[
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow Kubernetes API endpoint to communicate with OKE.",
                    protocol="6",
                    destination=oci.core.get_services().services[0].cidr_block,
                    destination_type="SERVICE_CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Path discovery",
                    icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                        code=4,
                        type=3,
                    ),
                    protocol="1",
                    destination=oci.core.get_services().services[0].cidr_block,
                    destination_type="SERVICE_CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow Kubernetes API endpoint to communicate with worker nodes.",
                    protocol="6",
                    destination=self.vcn.private_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=10250,
                        min=10250,
                    ),
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Path discovery",
                    icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                        code=4,
                        type=3,
                    ),
                    protocol="1",
                    destination=self.vcn.private_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow Kubernetes API endpoint to communicate with pods (when using VCN-native pod networking).",
                    protocol="all",
                    destination=self.vcn.private_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                ),
            ],
        )

        # Create a separate Security List for the Workers Subnet
        workers_security_list = oci.core.SecurityList(
            "WorkersSecurityList",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name="WorkersSecurityList",
            ingress_security_rules=[
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Allow Kubernetes API endpoint to communicate with worker nodes.",
                    protocol="6",
                    source=self.vcn.public_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        min=10250,
                        max=10250,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Path discovery",
                    icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                        code=4,
                        type=3,
                    ),
                    protocol="1",
                    source="0.0.0.0/0",
                    source_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Load balancer to worker nodes node ports.",
                    protocol="6",
                    source=self.vcn.public_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        min=30000,
                        max=32767,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Allow load balancer to communicate with kube-proxy on worker nodes.",
                    protocol="6",
                    source=self.vcn.public_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        min=10256,
                        max=12250,
                    ),
                ),
            ],
            egress_security_rules=[
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow worker nodes to access pods.",
                    protocol="6",
                    destination=self.vcn.private_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Path discovery",
                    icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                        code=4,
                        type=3,
                    ),
                    protocol="1",
                    destination="0.0.0.0/0",
                    destination_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow worker nodes to communicate with OKE.",
                    protocol="6",
                    destination=oci.core.get_services().services[0].cidr_block,
                    destination_type="SERVICE_CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Kubernetes worker to Kubernetes API endpoint communication.",
                    protocol="6",
                    destination=self.vcn.public_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=6443,
                        min=6443,
                    ),
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Kubernetes worker to Kubernetes API endpoint communication.",
                    protocol="6",
                    destination=self.vcn.public_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=12250,
                        min=12250,
                    ),
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Access to external (ex Dokcer) container registry",
                    protocol="6",
                    destination="0.0.0.0/0",
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=443,
                        min=443,
                    ),
                ),
            ],
        )

        # Create a separate Security List for the Pods Subnet
        pods_security_list = oci.core.SecurityList(
            "PodSecurityList",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name="PodSecurityList",
            ingress_security_rules=[
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Allow worker nodes to access pods.",
                    protocol="all",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Allow Kubernetes API endpoint to communicate with pods.",
                    protocol="all",
                    source=self.vcn.public_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Allow pods to communicate with other pods.",
                    protocol="all",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                ),
            ],
            egress_security_rules=[
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow pods to communicate with other pods.",
                    protocol="all",
                    destination=self.vcn.private_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Path discovery",
                    icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                        code=4,
                        type=3,
                    ),
                    protocol="1",
                    destination=oci.core.get_services().services[0].cidr_block,
                    destination_type="SERVICE_CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow pods to communicate with OCI services.",
                    protocol="6",
                    destination=oci.core.get_services().services[0].cidr_block,
                    destination_type="SERVICE_CIDR_BLOCK",
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="(optional) Allow pods to communicate with internet.",
                    protocol="6",
                    destination="0.0.0.0/0",
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=443,
                        min=443,
                    ),
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Pod to Kubernetes API endpoint communication (when using VCN-native pod networking).",
                    protocol="6",
                    destination=self.vcn.public_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=6443,
                        min=6443,
                    ),
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Pod to Kubernetes API endpoint communication (when using VCN-native pod networking).",
                    protocol="6",
                    destination=self.vcn.public_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=12250,
                        min=12250,
                    ),
                ),
            ],
        )

        # Create a separate Security List for the Public Subnet
        loadbalancers_security_list = oci.core.SecurityList(
            "LoadBalancersSecurityList",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name="LoadBalancersSecurityList",
            ingress_security_rules=[
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Load balancer listener protocol and port. Customize as required.",
                    protocol="6",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=443,
                        min=443,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Load balancer listener protocol and port. Customize as required.",
                    protocol="6",
                    source=self.vcn.private_subnet.cidr_block,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=80,
                        min=80,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Load balancer listener protocol and port. Customize as required.",
                    protocol="6",
                    source="0.0.0.0/0",
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=443,
                        min=443,
                    ),
                ),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description="Load balancer listener protocol and port. Customize as required.",
                    protocol="6",
                    source="0.0.0.0/0",
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        max=80,
                        min=80,
                    ),
                ),
            ],
            egress_security_rules=[
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Load balancer to worker nodes node ports.",
                    protocol="6",
                    destination=self.vcn.private_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        min=30000,
                        max=32767,
                    ),
                ),
                oci.core.SecurityListEgressSecurityRuleArgs(
                    description="Allow load balancer to communicate with kube-proxy on worker nodes.",
                    protocol="6",
                    destination=self.vcn.private_subnet.cidr_block,
                    destination_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                        max=10256,
                        min=10256,
                    ),
                ),
            ],
        )

    def create_kubeconfig(self, filename) -> None:
        cluster_kube_config = self.cluster.id.apply(
            lambda cid: oci.containerengine.get_cluster_kube_config(cluster_id=cid)
        )
        cluster_kube_config.content.apply(lambda cc: open(filename, "w+").write(cc))
