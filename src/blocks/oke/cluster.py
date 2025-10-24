from __future__ import annotations

import pulumi
import pulumi_oci as oci
from core.base import BaseResource
from core.helper import Helper
from blocks.vcn.network import Vcn


class OkeCluster(BaseResource):
    """Oracle Kubernetes Engine (OKE) cluster with node pool and security configurations.

    This class adds OKE-specific rules to the VCN's security lists using the
    vcn.add_security_list_rules() method. This approach is SCALABLE as it uses
    only 1 security list per subnet instead of creating separate OKE security lists.

    Security List Strategy:
    -----------------------
    - Uses VCN's existing security lists (banana-lab-sl-public, banana-lab-sl-private)
    - Adds OKE rules directly to them via vcn.add_security_list_rules()
    - Only 1 security list per subnet (leaves 4 slots free for other services)
    - Scalable: Can add more services later (databases, etc.) without hitting the 5-list limit

    What Gets Added:
    ----------------
    Public Security List (banana-lab-sl-public):
    - API endpoint ingress/egress rules
    - Load Balancer ingress/egress rules

    Private Security List (banana-lab-sl-private):
    - Worker nodes ingress/egress rules
    - Pods ingress/egress rules

    Usage Example:
    -------------
    ```python
    # Create VCN (creates empty security lists)
    vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="banana")

    # Create OKE cluster (adds OKE rules to VCN security lists)
    cluster = OkeCluster(
        name="okeinfra",
        vcn=vcn,
        compartment_id=comp_id,
        kubernetes_version="v1.28.2",
        ...
    )

    # Now banana-lab-sl-public and banana-lab-sl-private contain OKE rules
    # Still have 4 free slots per subnet for future services
    ```
    """

    vcn: Vcn
    kubernetes_version: pulumi.Input[str]
    display_name: str
    shape: pulumi.Input[str]
    min_nodes: pulumi.Input[int]
    ocpus: pulumi.Input[float]
    memory_in_gbs: pulumi.Input[float]
    ssh_public_key: pulumi.Input[str] | None
    image: pulumi.Input[str] | None
    # Backward compatibility aliases (point to updated VCN security lists)
    oke_public_security_list: oci.core.SecurityList
    oke_private_security_list: oci.core.SecurityList
    cluster: oci.containerengine.Cluster
    node_pool: oci.containerengine.NodePool
    id: pulumi.Output[str]

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
        ssh_public_key: pulumi.Input[str] | None = None,
        opts: pulumi.ResourceOptions | None = None,
        image: pulumi.Input[str] | None = None,
    ) -> None:
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

        # Store display_name as string (extracting from pulumi.Input if needed)
        self.display_name = str(display_name) if not isinstance(display_name, str) else display_name
        self.name = name
        self.vcn = vcn
        self.compartment_id = compartment_id
        self.kubernetes_version = kubernetes_version
        self.shape = shape
        self.min_nodes = min_nodes
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs
        self.ssh_public_key = ssh_public_key
        self.image = image

        # Add OKE rules to VCN security lists
        self._add_oke_security_lists_rules()

        # Finalize the VCN network (create security lists and subnets with all collected rules)
        self.vcn.finalize_network()

        # Set backward compatibility aliases (after security lists are created)
        self.oke_public_security_list = self.vcn.public_security_list
        self.oke_private_security_list = self.vcn.private_security_list

        # Create the OKE cluster
        # At this point, finalize_network() has been called, so subnets exist
        assert self.vcn.public_subnet is not None, "VCN public subnet must exist after finalization"
        assert self.vcn.private_subnet is not None, "VCN private subnet must exist after finalization"

        self.cluster = oci.containerengine.Cluster(
            "Cluster",
            compartment_id=self.compartment_id,
            name=f"Cluster-{self.display_name}",
            kubernetes_version=self.kubernetes_version,
            options=oci.containerengine.ClusterOptionsArgs(
                service_lb_subnet_ids=[self.vcn.public_subnet.id],
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
                subnet_id=self.vcn.public_subnet.id, is_public_ip_enabled=True
            ),
        )

        self.id = self.cluster.id

        # if image is None:
        #     test_node_pool_option = oci.containerengine.get_node_pool_option_output(
        #         node_pool_option_id=self.cluster.id, compartment_id=self.compartment_id
        #     )

        #     c = test_node_pool_option.sources
        #     image_id = c.apply(lambda images: h.get_oke_image(images, shape, kubernetes_version))
        # else:
        #     image_id = image
        image_id: pulumi.Input[str] | None = image

        # Initialize helper for node pool configuration
        h: Helper = Helper()

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
                placement_configs=ads.apply(lambda ads_list: h.get_ads(ads_list, self.vcn.private_subnet.id)),  # type: ignore[arg-type, union-attr, return-value]
                size=min_nodes,
                node_pool_pod_network_option_details=oci.containerengine.NodePoolNodeConfigDetailsNodePoolPodNetworkOptionDetailsArgs(
                    cni_type="OCI_VCN_IP_NATIVE", pod_subnet_ids=[self.vcn.private_subnet.id]
                ),
            ),
            node_shape=shape,
            node_shape_config=oci.containerengine.NodePoolNodeShapeConfigArgs(memory_in_gbs=memory_in_gbs, ocpus=ocpus),
            node_source_details=oci.containerengine.NodePoolNodeSourceDetailsArgs(
                image_id=image_id if image_id is not None else "",
                source_type="IMAGE",
            ),
            ssh_public_key=ssh_public_key if ssh_public_key else None,
        )

        self.register_outputs({})

    def _add_oke_security_lists_rules(self) -> None:
        """Add OKE-specific rules to VCN security lists.

        Calls vcn.add_security_list_rules() to add OKE rules to the existing
        VCN security lists. This is scalable - only uses 1 security list per subnet
        instead of creating separate OKE security lists.

        Rules Added:
        - Public: API endpoint + Load Balancer rules
        - Private: Worker nodes + Pods rules
        """

        # ===== RULES TO ADD TO PUBLIC SECURITY LIST =====

        # Get subnet CIDRs (available before finalization)
        private_subnet_cidr: str = self.vcn.get_private_subnet_cidr()
        public_subnet_cidr: str = self.vcn.get_public_subnet_cidr()

        # 1. OKE API Endpoint (Control Plane) Security List
        oke_api_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Kubernetes worker to Kubernetes API endpoint communication.",
                protocol="6",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=6443, max=6443,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Kubernetes worker to control plane communication.",
                protocol="6",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=12250, max=12250,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Path discovery.",
                protocol="1",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                    type=3, code=4,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Pod to Kubernetes API endpoint (VCN-native pod networking).",
                protocol="6",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=6443, max=6443,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Pod to control plane (VCN-native pod networking).",
                protocol="6",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=12250, max=12250,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="External access to Kubernetes API endpoint.",
                protocol="6",
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=6443, max=6443,
                ),
            ),
        ]

        oke_api_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="API endpoint to OKE service.",
                protocol="6",
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Path discovery to OKE service.",
                protocol="1",
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                    type=3, code=4,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="API endpoint to worker nodes kubelet.",
                protocol="6",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=10250, max=10250,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Path discovery to worker nodes.",
                protocol="1",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                    type=3, code=4,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="API endpoint to pods (VCN-native pod networking).",
                protocol="all",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
            ),
        ]

        # 2. Load Balancers Ingress/Egress Rules (also for public subnet)
        oke_lb_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="LB from private subnet - HTTPS.",
                protocol="6",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=443, max=443,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="LB from private subnet - HTTP.",
                protocol="6",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=80, max=80,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="LB from internet - HTTPS.",
                protocol="6",
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=443, max=443,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="LB from internet - HTTP.",
                protocol="6",
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=80, max=80,
                ),
            ),
        ]

        oke_lb_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="LB to worker nodes NodePort range.",
                protocol="6",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=30000, max=32767,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="LB to kube-proxy health check.",
                protocol="6",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=10256, max=10256,
                ),
            ),
        ]

        # ===== RULES FOR PRIVATE SECURITY LIST =====

        # 3. Workers Ingress/Egress Rules
        oke_workers_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="API endpoint to worker nodes kubelet.",
                protocol="6",
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=10250, max=10250,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Path discovery from anywhere.",
                protocol="1",
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                    type=3, code=4,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="LB to worker nodes NodePort range.",
                protocol="6",
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=30000, max=32767,
                ),
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="LB to kube-proxy health check.",
                protocol="6",
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=10256, max=10256,
                ),
            ),
        ]

        oke_workers_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Worker nodes to pods.",
                protocol="all",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Path discovery to internet.",
                protocol="1",
                destination="0.0.0.0/0",
                destination_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                    type=3, code=4,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Worker nodes to OKE service.",
                protocol="6",
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Worker nodes to API endpoint.",
                protocol="6",
                destination=public_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=6443, max=6443,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Worker nodes to control plane.",
                protocol="6",
                destination=public_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=12250, max=12250,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Worker nodes to external container registries.",
                protocol="6",
                destination="0.0.0.0/0",
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=443, max=443,
                ),
            ),
        ]

        # 4. Pods Ingress/Egress Rules
        oke_pods_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Worker nodes to pods.",
                protocol="all",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="API endpoint to pods.",
                protocol="all",
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
            ),
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Pods to pods communication.",
                protocol="all",
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
            ),
        ]

        oke_pods_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Pods to pods communication.",
                protocol="all",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Path discovery to OKE service.",
                protocol="1",
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
                icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                    type=3, code=4,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Pods to OCI services.",
                protocol="6",
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Pods to internet (optional).",
                protocol="6",
                destination="0.0.0.0/0",
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=443, max=443,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Pods to API endpoint.",
                protocol="6",
                destination=public_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=6443, max=6443,
                ),
            ),
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Pods to control plane.",
                protocol="6",
                destination=public_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=12250, max=12250,
                ),
            ),
        ]

        # Add all OKE rules to VCN security lists
        self.vcn.add_security_list_rules(
            public_ingress=oke_api_ingress_rules + oke_lb_ingress_rules,
            public_egress=oke_api_egress_rules + oke_lb_egress_rules,
            private_ingress=oke_workers_ingress_rules + oke_pods_ingress_rules,
            private_egress=oke_workers_egress_rules + oke_pods_egress_rules,
        )

    def get_public_security_list_ids(self) -> list[pulumi.Output[str]]:
        """Get security list IDs for the public subnet (VCN list with OKE rules added).

        Returns:
            List with the updated VCN public security list ID.
            The security list now contains OKE API endpoint + Load Balancer rules.

        Example:
            cluster = OkeCluster(...)
            # Security list already updated, just reference it
            public_sl_id = cluster.get_public_security_list_ids()[0]
        """
        return [self.vcn.public_security_list.id]

    def get_private_security_list_ids(self) -> list[pulumi.Output[str]]:
        """Get security list IDs for the private subnet (VCN list with OKE rules added).

        Returns:
            List with the updated VCN private security list ID.
            The security list now contains OKE Worker nodes + Pods rules.

        Example:
            cluster = OkeCluster(...)
            # Security list already updated, just reference it
            private_sl_id = cluster.get_private_security_list_ids()[0]
        """
        return [self.vcn.private_security_list.id]

    def create_kubeconfig(self, filename: str) -> None:
        """Create a kubeconfig file for the OKE cluster.

        Args:
            filename: Path where the kubeconfig file should be written.
        """
        cluster_kube_config = self.cluster.id.apply(
            lambda cid: oci.containerengine.get_cluster_kube_config(cluster_id=cid)
        )
        cluster_kube_config.content.apply(lambda cc: open(filename, "w+").write(cc))  # type: ignore[union-attr]
