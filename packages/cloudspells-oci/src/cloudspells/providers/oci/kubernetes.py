"""OKE (Oracle Kubernetes Engine) cluster spell for CloudSpells.

Provides `OkeCluster`, a high-level Pulumi component that creates a complete
OKE cluster with a node pool, all required OCI security list rules, and four
Network Security Groups (NSGs) that segment traffic by component role.

Subnet mapping:

OKE resources are placed across two of the four VCN tiers:

- **Public subnet** — API endpoint (public IP for kubectl) + OCI Load Balancers
  created by `LoadBalancer` services.
- **Private subnet** — Worker node VNICs and pod VNICs (`OCI_VCN_IP_NATIVE`).
  Workers and pods share this subnet's CIDR.  NSGs discriminate between them
  at the VNIC level so the control plane, load balancer, and pods each see
  only the resources they are permitted to reach.  Intra-subnet (pod-to-pod,
  node-to-node) traffic that stays within the same CIDR bypasses security list
  rules and is governed exclusively by NSGs.
- **Secure subnet** — Not used by OKE; reserved for databases and secrets
  managers that must not initiate any internet connection.
- **Management subnet** — Not used by OKE directly; reserved for bastion hosts,
  monitoring agents, and VPN/FastConnect endpoints.

Security strategy — two complementary layers:

1. **Security lists** (subnet-level): enforce coarse-grained, subnet-to-subnet
   routing policy.  `OkeCluster` adds its rules directly to the VCN's shared
   security lists via `Vcn.add_security_list_rules`, consuming only 1 list per
   subnet and leaving 4 slots free for additional services.

2. **Network Security Groups** (VNIC-level): enforce fine-grained,
   component-to-component rules.  Four NSGs are created and assigned to OKE
   resources:

   - `api_nsg` → attached to the Kubernetes API endpoint.
   - `lb_nsg` → intended for OCI Load Balancers created by `Service type:
     LoadBalancer`.  Reference `cluster.lb_nsg.id` in the Kubernetes service
     annotation `oci.oraclecloud.com/security-group-ids` to activate it.
   - `worker_nsg` → attached to all worker node VNICs.
   - `pod_nsg` → attached to all pod VNICs (OCI CNI VNIC-native pods).

   Because workers and pods carry different NSGs, the API endpoint can reach
   pods on arbitrary ports (webhooks) while the load balancer is restricted to
   NodePort and kube-proxy health-check ports on workers only — even though
   both share the same private subnet CIDR.

Security list rules added by this spell:

Public subnet (API endpoint + Load Balancer):

- Ingress: Kubernetes API (6443) and control-plane port (12250) from private.
- Ingress: ICMP path-MTU discovery from private subnet.
- Ingress: HTTPS (443) and HTTP (80) from internet (Load Balancer).
- Ingress: Kubernetes API (6443) from internet (kubectl).
- Egress: OCI services (cluster management and telemetry).
- Egress: Kubelet (10250), NodePort (30000-32767), kube-proxy (10256) to private.
- Egress: All traffic to private subnet (webhooks, admission controllers).

Private subnet (Worker nodes + Pods):

- Ingress: Kubelet (10250), NodePort (30000-32767), kube-proxy (10256) from public.
- Ingress: All traffic from public subnet (control plane to pods: webhooks).
- Ingress: ICMP path-MTU discovery from anywhere.
- Egress: OCI services (OCIR image pulls, monitoring, logging).
- Egress: Kubernetes API (6443) and control-plane port (12250) to public subnet.
- Egress: HTTPS (443) and HTTP (80) to internet (image pulls + pod external API calls).
- Egress: ICMP to internet (path-MTU discovery).
"""

from __future__ import annotations

from typing import Any

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.kubernetes import AbstractKubernetes
from cloudspells.core.base import BaseResource

from .helper import OciHelper
from .network import Vcn, VcnRef
from .nsg import ALL, ICMP, INTERNET, SVC_CIDR, TCP, icmp_opts, tcp_port, tcp_port_range


class OkeCluster(BaseResource, AbstractKubernetes):
    """Oracle Kubernetes Engine cluster with node pool, security configuration, and NSGs.

    Deploys a `BASIC_CLUSTER` OKE cluster with OCI VCN-native pod networking
    (`OCI_VCN_IP_NATIVE` CNI) and a node pool spread across all availability
    domains in the region.

    Workers and pods share the private subnet CIDR. Four NSGs provide
    VNIC-level segmentation:

    - `api_nsg` controls who may reach the Kubernetes API endpoint.
    - `lb_nsg` is intended for OCI Load Balancers (attach via service
      annotation `oci.oraclecloud.com/security-group-ids`).
    - `worker_nsg` is assigned to every worker node VNIC.
    - `pod_nsg` is assigned to every pod VNIC (OCI CNI VCN-native).

    Attributes:
        vcn: The `Vcn` this cluster is deployed into.
        kubernetes_version: Kubernetes version string (e.g. `"v1.30.1"`).
        display_name: Human-readable cluster display name.
        shape: Compute shape for the node pool VMs.
        min_nodes: Minimum (and initial) number of worker nodes.
        ocpus: Number of OCPUs per worker node.
        memory_in_gbs: RAM in GiB per worker node.
        ssh_public_key: Optional SSH public key installed on worker nodes.
        image: Optional explicit image OCID for worker nodes.
        api_nsg: NSG attached to the Kubernetes API endpoint VNIC.
        lb_nsg: NSG for OCI Load Balancers; apply via service annotation.
        worker_nsg: NSG attached to every worker node VNIC.
        pod_nsg: NSG attached to every pod VNIC (OCI CNI).
        oke_public_security_list: Alias for the VCN's public security list
            (populated with OKE rules after initialisation).
        oke_private_security_list: Alias for the VCN's private security list
            (populated with OKE rules after initialisation).
        cluster: The underlying `oci.containerengine.Cluster` resource.
        node_pool: The `oci.containerengine.NodePool` resource.
        id: `pulumi.Output[str]` of the cluster OCID.

    Example:
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")

        cluster = OkeCluster(
            name="k8s",
            compartment_id=comp_id,
            vcn=vcn,
            kubernetes_version="v1.30.1",
            shape="VM.Standard.E4.Flex",
            min_nodes=3,
            ocpus=2,
            memory_in_gbs=32,
            display_name="prod-k8s",
        )

        # Attach lb_nsg to Load Balancer services via annotation:
        # oci.oraclecloud.com/security-group-ids: "<cluster.lb_nsg.id>"
        cluster.create_kubeconfig("/tmp/kubeconfig")
        ```
    """

    vcn: Vcn | VcnRef
    kubernetes_version: pulumi.Input[str]
    display_name: str
    shape: pulumi.Input[str]
    min_nodes: pulumi.Input[int]
    ocpus: pulumi.Input[float]
    memory_in_gbs: pulumi.Input[float]
    ssh_public_key: pulumi.Input[str] | None
    image: pulumi.Input[str]
    api_nsg: oci.core.NetworkSecurityGroup
    lb_nsg: oci.core.NetworkSecurityGroup
    worker_nsg: oci.core.NetworkSecurityGroup
    pod_nsg: oci.core.NetworkSecurityGroup
    # Aliases pointing to the VCN security lists (Any to cover Vcn and VcnRef)
    oke_public_security_list: Any
    oke_private_security_list: Any
    cluster: oci.containerengine.Cluster
    node_pool: oci.containerengine.NodePool
    id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        shape: pulumi.Input[str],
        kubernetes_version: pulumi.Input[str],
        image: pulumi.Input[str],
        min_nodes: pulumi.Input[int],
        ocpus: pulumi.Input[float],
        memory_in_gbs: pulumi.Input[float],
        display_name: pulumi.Input[str],
        stack_name: str | None = None,
        ssh_public_key: pulumi.Input[str] | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a complete OKE cluster infrastructure.

        Adds all required OKE security rules to the VCN, finalises the network,
        creates four NSGs (api, lb, worker, pod) with NSG-to-NSG rules, and
        then creates the Kubernetes control plane and node pool.

        Args:
            name: Logical name for the cluster resource (e.g. `"k8s"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` instance that provides the public and private subnets.
            kubernetes_version: Kubernetes version string
                (e.g. `"v1.32.1"`).
            image: Boot image OCID for worker nodes.
            shape: Compute shape for worker node VMs
                (e.g. `"VM.Standard.E4.Flex"`).
            min_nodes: Number of worker nodes in the node pool.  The pool
                is spread evenly across all availability domains.
            ocpus: Number of OCPUs per worker node.
            memory_in_gbs: RAM in GiB per worker node.
            display_name: Human-readable name used for the cluster and node
                pool OCI resources.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            ssh_public_key: Optional SSH public key to install on worker
                nodes (enables direct SSH for debugging).
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:oke:Cluster", name, compartment_id, stack_name, opts)

        self.display_name = str(display_name) if not isinstance(display_name, str) else display_name
        self.name = name
        self.vcn = vcn
        self.compartment_id = compartment_id

        self.shape = shape
        self.min_nodes = min_nodes
        self.ocpus = ocpus
        self.memory_in_gbs = memory_in_gbs
        self.ssh_public_key = ssh_public_key
        self.image = image
        self.kubernetes_version = kubernetes_version

        # Layer 1: subnet-level security list rules
        self._add_oke_security_lists_rules()
        self.vcn.finalize_network()

        # Aliases pointing to the VCN security lists (None when using VcnRef)
        self.oke_public_security_list = self.vcn.public_security_list  # type: ignore[assignment]
        self.oke_private_security_list = self.vcn.private_security_list  # type: ignore[assignment]

        assert self.vcn.public_subnet is not None, "VCN public subnet must exist after finalization"
        assert self.vcn.private_subnet is not None, "VCN private subnet must exist after finalization"

        # Layer 2: VNIC-level NSGs — must be created before cluster/node pool
        self._create_oke_nsgs()

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
                subnet_id=self.vcn.public_subnet.id,
                is_public_ip_enabled=True,
                nsg_ids=[self.api_nsg.id],
            ),
        )

        self.id = self.cluster.id

        h: OciHelper = OciHelper()
        get_ad_names = oci.identity.get_availability_domains_output(compartment_id=self.compartment_id)
        ads = get_ad_names.availability_domains

        self.node_pool = oci.containerengine.NodePool(
            "NodePool",
            name=f"NodePool-{self.display_name}",
            cluster_id=self.cluster.id,
            compartment_id=self.compartment_id,
            kubernetes_version=self.kubernetes_version,
            node_config_details=oci.containerengine.NodePoolNodeConfigDetailsArgs(
                placement_configs=ads.apply(lambda ads_list: h.get_ads(ads_list, self.vcn.private_subnet.id)),  # type: ignore[arg-type, union-attr, return-value]
                size=min_nodes,
                nsg_ids=[self.worker_nsg.id],
                node_pool_pod_network_option_details=oci.containerengine.NodePoolNodeConfigDetailsNodePoolPodNetworkOptionDetailsArgs(
                    cni_type="OCI_VCN_IP_NATIVE",
                    pod_subnet_ids=[self.vcn.private_subnet.id],  # type: ignore[union-attr]
                    pod_nsg_ids=[self.pod_nsg.id],
                ),
            ),
            node_shape=shape,
            node_shape_config=oci.containerengine.NodePoolNodeShapeConfigArgs(memory_in_gbs=memory_in_gbs, ocpus=ocpus),
            node_source_details=oci.containerengine.NodePoolNodeSourceDetailsArgs(
                image_id=self.image,
                source_type="IMAGE",
            ),
            ssh_public_key=ssh_public_key if ssh_public_key else None,
        )

        self.register_outputs({})

    # ------------------------------------------------------------------
    # Private: security list rules (subnet-level, Layer 1)
    # ------------------------------------------------------------------

    def _add_oke_security_lists_rules(self) -> None:
        """Add all OKE-required security rules to the VCN security lists.

        Calls `Vcn.add_security_list_rules` once with the complete set of
        ingress and egress rules for the public (API endpoint + Load Balancer)
        and private (worker nodes + pods) subnets.

        Must be called before `Vcn.finalize_network`.

        Rules added:

        Public subnet ingress: Kubernetes API (6443) and control-plane port
        (12250) from private subnet (workers + pods); ICMP path-MTU from
        private; HTTPS (443) and HTTP (80) from internet (Load Balancer);
        Kubernetes API (6443) from internet (kubectl).

        Public subnet egress: OCI services (telemetry, management); kubelet
        (10250), ICMP, NodePort (30000-32767), and kube-proxy (10256) to
        private; all traffic to private (webhooks, admission controllers).

        Private subnet ingress: kubelet (10250), NodePort (30000-32767), and
        kube-proxy (10256) from public; all traffic from public (control plane
        to pods for webhooks); ICMP from anywhere.

        Private subnet egress: OCI services (OCIR, monitoring, logging);
        Kubernetes API (6443) and control-plane port (12250) to public;
        HTTPS (443) and HTTP (80) to internet (image pulls and pod external
        API calls); ICMP to internet.
        """
        # ═══════════════════════════════════════════════════════════════
        # PUBLIC SUBNET – API Endpoint + Load Balancer
        # ═══════════════════════════════════════════════════════════════

        private_subnet_cidr: pulumi.Input[str] = self.vcn.get_private_subnet_cidr()
        public_subnet_cidr: pulumi.Input[str] = self.vcn.get_public_subnet_cidr()
        svc_cidr: pulumi.Output[str] = self.vcn._svc_cidr_block

        # ───────────────────────────────────────────────────────────────
        # PUBLIC – INGRESS
        # ───────────────────────────────────────────────────────────────
        public_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            # Workers + pods → API server
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Workers and pods communicate with Kubernetes API server for cluster operations and service discovery",  # noqa: E501
                protocol="6",  # TCP
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=6443,
                    max=6443,
                ),
            ),
            # Workers + pods → control plane internal port
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Workers and pods communicate with Kubernetes control plane for internal cluster operations",  # noqa: E501
                protocol="6",  # TCP
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=12250,
                    max=12250,
                ),
            ),
            # ICMP path-MTU from private subnet
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="ICMP path discovery from private subnet to optimize network packet size",
                protocol="1",  # ICMP
                source=private_subnet_cidr,
                source_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                    type=3,
                    code=4,
                ),
            ),
            # External clients (kubectl) → API server
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Allow external access to Kubernetes API for kubectl and cluster management tools",
                protocol="6",  # TCP
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=6443,
                    max=6443,
                ),
            ),
            # Internet → Load Balancer HTTPS
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Load Balancer receives HTTPS traffic from internet for public web applications and APIs",
                protocol="6",  # TCP
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=443,
                    max=443,
                ),
            ),
            # Internet → Load Balancer HTTP
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Load Balancer receives HTTP traffic from internet for public applications (consider HTTPS redirect)",  # noqa: E501
                protocol="6",  # TCP
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=80,
                    max=80,
                ),
            ),
        ]

        # ───────────────────────────────────────────────────────────────
        # PUBLIC – EGRESS
        # ───────────────────────────────────────────────────────────────
        public_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            # Control plane → OCI services (telemetry, management)
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Control plane communicates with OCI services for cluster management and telemetry",
                protocol="6",  # TCP
                destination=svc_cidr,
                destination_type="SERVICE_CIDR_BLOCK",
            ),
            # ICMP path-MTU to OCI services
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="ICMP path discovery to OCI services for optimal network performance",
                protocol="1",  # ICMP
                destination=svc_cidr,
                destination_type="SERVICE_CIDR_BLOCK",
                icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                    type=3,
                    code=4,
                ),
            ),
            # Control plane → kubelet API on worker nodes
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Control plane manages worker nodes via kubelet for pod operations and health monitoring",
                protocol="6",  # TCP
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=10250,
                    max=10250,
                ),
            ),
            # ICMP path-MTU to private subnet
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="ICMP path discovery to private subnet for network optimization",
                protocol="1",  # ICMP
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                    type=3,
                    code=4,
                ),
            ),
            # LB → NodePort range on worker nodes
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Load Balancer forwards traffic to worker nodes via NodePort for Kubernetes service routing",  # noqa: E501
                protocol="6",  # TCP
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=30000,
                    max=32767,
                ),
            ),
            # LB → kube-proxy health check
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Load Balancer checks worker node health via kube-proxy to ensure traffic routing availability",  # noqa: E501
                protocol="6",  # TCP
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=10256,
                    max=10256,
                ),
            ),
            # Control plane → pods (webhooks, admission controllers, metrics)
            # Admission controller webhook ports are arbitrary; allow all protocols.
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Control plane reaches pods on arbitrary ports for webhooks, admission controllers, and metrics",  # noqa: E501
                protocol="all",
                destination=private_subnet_cidr,
                destination_type="CIDR_BLOCK",
            ),
        ]

        # ═══════════════════════════════════════════════════════════════
        # PRIVATE SUBNET – Worker Nodes + Pods
        # ═══════════════════════════════════════════════════════════════

        # ───────────────────────────────────────────────────────────────
        # PRIVATE – INGRESS
        # ───────────────────────────────────────────────────────────────
        private_ingress_rules: list[oci.core.SecurityListIngressSecurityRuleArgs] = [
            # Control plane → kubelet API
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Control plane manages pods on worker nodes via kubelet for commands, logs, and health monitoring",  # noqa: E501
                protocol="6",  # TCP
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=10250,
                    max=10250,
                ),
            ),
            # LB → NodePort range
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Load Balancer forwards traffic to worker nodes via NodePort to reach Kubernetes services",
                protocol="6",  # TCP
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=30000,
                    max=32767,
                ),
            ),
            # LB → kube-proxy health check
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Load Balancer verifies worker node health via kube-proxy endpoint before routing traffic",
                protocol="6",  # TCP
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                    min=10256,
                    max=10256,
                ),
            ),
            # Control plane → pods (webhooks, admission controllers)
            # Ports are arbitrary per admission controller; allow all from public.
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="Control plane reaches pods on arbitrary ports for webhooks and admission controllers",
                protocol="all",
                source=public_subnet_cidr,
                source_type="CIDR_BLOCK",
            ),
            # ICMP path-MTU from anywhere
            oci.core.SecurityListIngressSecurityRuleArgs(
                description="ICMP path discovery to private subnet for optimal network packet size from any source",
                protocol="1",  # ICMP
                source="0.0.0.0/0",
                source_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(
                    type=3,
                    code=4,
                ),
            ),
        ]

        # ───────────────────────────────────────────────────────────────
        # PRIVATE – EGRESS
        # ───────────────────────────────────────────────────────────────
        private_egress_rules: list[oci.core.SecurityListEgressSecurityRuleArgs] = [
            # Workers + pods → OCI services (OCIR, monitoring, logging)
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Workers and pods communicate with OCI services for container images, logging, and monitoring",  # noqa: E501
                protocol="6",  # TCP
                destination=svc_cidr,
                destination_type="SERVICE_CIDR_BLOCK",
            ),
            # Workers + pods → Kubernetes API server
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Workers and pods communicate with Kubernetes API to register, report status, and access resources",  # noqa: E501
                protocol="6",  # TCP
                destination=public_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=6443,
                    max=6443,
                ),
            ),
            # Workers + pods → control plane internal port
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Workers and pods communicate with control plane for internal cluster operations",
                protocol="6",  # TCP
                destination=public_subnet_cidr,
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=12250,
                    max=12250,
                ),
            ),
            # Workers + pods → internet via HTTPS (image pulls, external APIs)
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Workers pull container images and pods call external APIs via HTTPS",
                protocol="6",  # TCP
                destination="0.0.0.0/0",
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=443,
                    max=443,
                ),
            ),
            # Workers + pods → internet via HTTP (some registries, OCI pre-auth URLs)
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="Workers pull container images from HTTP registries and access OCI pre-authenticated URLs",
                protocol="6",  # TCP
                destination="0.0.0.0/0",
                destination_type="CIDR_BLOCK",
                tcp_options=oci.core.SecurityListEgressSecurityRuleTcpOptionsArgs(
                    min=80,
                    max=80,
                ),
            ),
            # ICMP path-MTU to internet
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="ICMP path discovery from private subnet to internet for network optimization",
                protocol="1",  # ICMP
                destination="0.0.0.0/0",
                destination_type="CIDR_BLOCK",
                icmp_options=oci.core.SecurityListEgressSecurityRuleIcmpOptionsArgs(
                    type=3,
                    code=4,
                ),
            ),
        ]

        # Add all collected rules to the VCN security lists in a single call
        self.vcn.add_security_list_rules(
            public_ingress=public_ingress_rules,
            public_egress=public_egress_rules,
            private_ingress=private_ingress_rules,
            private_egress=private_egress_rules,
        )

    # ------------------------------------------------------------------
    # Private: NSG creation and rules (VNIC-level, Layer 2)
    # ------------------------------------------------------------------

    def _create_oke_nsgs(self) -> None:
        """Create the four OKE NSGs and wire all NSG-to-NSG rules.

        Creates `api_nsg`, `lb_nsg`, `worker_nsg`, and `pod_nsg` as child
        resources of this component, then adds all necessary stateful ingress
        and egress rules using NSG OCIDs as source/destination so that
        workers and pods — which share the same private subnet CIDR — are
        independently reachable only by the components that are authorised
        to reach them.

        Must be called after `Vcn.finalize_network` and before cluster/node
        pool creation so that NSG IDs are available for `endpoint_config.nsg_ids`
        and `node_config_details.nsg_ids`.
        """
        opts = pulumi.ResourceOptions(parent=self)

        # ── Create the four NSG objects ────────────────────────────────
        self.api_nsg = oci.core.NetworkSecurityGroup(
            "OkeApiNsg",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=f"{self.display_name}-api-nsg",
            opts=opts,
        )
        self.lb_nsg = oci.core.NetworkSecurityGroup(
            "OkeLbNsg",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=f"{self.display_name}-lb-nsg",
            opts=opts,
        )
        self.worker_nsg = oci.core.NetworkSecurityGroup(
            "OkeWorkerNsg",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=f"{self.display_name}-worker-nsg",
            opts=opts,
        )
        self.pod_nsg = oci.core.NetworkSecurityGroup(
            "OkePodNsg",
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=f"{self.display_name}-pod-nsg",
            opts=opts,
        )

        # ── Wire rules — all four NSGs must exist before any rules ────
        self._add_api_nsg_rules(opts)
        self._add_lb_nsg_rules(opts)
        self._add_worker_nsg_rules(opts)
        self._add_pod_nsg_rules(opts)

    def _r(
        self,
        name: str,
        nsg_id: pulumi.Input[str],
        *,
        direction: str,
        protocol: str,
        source: pulumi.Input[str] | None = None,
        source_type: str | None = None,
        destination: pulumi.Input[str] | None = None,
        destination_type: str | None = None,
        tcp_options: oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs | None = None,
        icmp_options: oci.core.NetworkSecurityGroupSecurityRuleIcmpOptionsArgs | None = None,
        description: str = "",
        opts: pulumi.ResourceOptions | None = None,
    ) -> oci.core.NetworkSecurityGroupSecurityRule:
        """Create a single stateful NSG security rule.

        Private shorthand used by `_add_*_nsg_rules` helpers to reduce
        boilerplate.  `name` must be unique within this `OkeCluster` component.

        Args:
            name: Pulumi resource name, unique within this component.
            nsg_id: OCID of the NSG that owns this rule.
            direction: `"INGRESS"` or `"EGRESS"`.
            protocol: OCI protocol string — `TCP`, `ICMP`, or `ALL`.
            source: Source CIDR or NSG OCID (ingress rules).
            source_type: `"CIDR_BLOCK"` or `"NETWORK_SECURITY_GROUP"`.
            destination: Destination CIDR or NSG OCID (egress rules).
            destination_type: `"CIDR_BLOCK"`, `"NETWORK_SECURITY_GROUP"`,
                or `"SERVICE_CIDR_BLOCK"`.
            tcp_options: TCP port restriction — build with `tcp_port` or
                `tcp_port_range`.
            icmp_options: ICMP type/code — build with `icmp_opts`.
            description: Human-readable description shown in the OCI Console.
            opts: Pulumi resource options forwarded to the rule resource.

        Returns:
            The created `oci.core.NetworkSecurityGroupSecurityRule` resource.
        """
        return oci.core.NetworkSecurityGroupSecurityRule(
            name,
            network_security_group_id=nsg_id,
            direction=direction,
            protocol=protocol,
            source=source,
            source_type=source_type,
            destination=destination,
            destination_type=destination_type,
            tcp_options=tcp_options,
            icmp_options=icmp_options,
            stateless=False,
            description=description or name,
            opts=opts,
        )

    def _add_api_nsg_rules(self, opts: pulumi.ResourceOptions) -> None:
        """Add ingress and egress rules to `api_nsg`.

        Ingress: workers and pods reach the API server (6443) and internal
        control-plane port (12250); workers send path-MTU ICMP; external
        clients (kubectl) reach the API on 6443.

        Egress: control plane reaches OCI services (telemetry), kubelet on
        workers (10250), and all ports on pods (webhooks, exec, metrics).

        Args:
            opts: Pulumi resource options applied to every rule resource.
        """
        nsg = self.api_nsg.id

        # ── INGRESS ────────────────────────────────────────────────────
        self._r(
            "OkeApiNsgIngress-worker-6443",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.worker_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(6443),
            description="Worker nodes reach Kubernetes API server",
            opts=opts,
        )
        self._r(
            "OkeApiNsgIngress-worker-12250",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.worker_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(12250),
            description="Worker nodes reach Kubernetes control-plane internal port",
            opts=opts,
        )
        self._r(
            "OkeApiNsgIngress-pod-6443",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.pod_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(6443),
            description="Pods reach Kubernetes API server for service discovery and RBAC",
            opts=opts,
        )
        self._r(
            "OkeApiNsgIngress-pod-12250",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.pod_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(12250),
            description="Pods reach Kubernetes control-plane internal port",
            opts=opts,
        )
        self._r(
            "OkeApiNsgIngress-worker-icmp",
            nsg,
            direction="INGRESS",
            protocol=ICMP,
            source=self.worker_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            icmp_options=icmp_opts(3, 4),
            description="Path-MTU discovery from worker nodes",
            opts=opts,
        )
        self._r(
            "OkeApiNsgIngress-kubectl",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=INTERNET,
            source_type="CIDR_BLOCK",
            tcp_options=tcp_port(6443),
            description="External kubectl and CI tooling reach the Kubernetes API",
            opts=opts,
        )

        # ── EGRESS ─────────────────────────────────────────────────────
        self._r(
            "OkeApiNsgEgress-services",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=SVC_CIDR,
            destination_type="SERVICE_CIDR_BLOCK",
            description="Control plane sends telemetry and management traffic to OCI services",
            opts=opts,
        )
        self._r(
            "OkeApiNsgEgress-services-icmp",
            nsg,
            direction="EGRESS",
            protocol=ICMP,
            destination=SVC_CIDR,
            destination_type="SERVICE_CIDR_BLOCK",
            icmp_options=icmp_opts(3, 4),
            description="Path-MTU discovery to OCI services",
            opts=opts,
        )
        self._r(
            "OkeApiNsgEgress-worker-kubelet",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(10250),
            description="Control plane calls kubelet on worker nodes for pod lifecycle operations",
            opts=opts,
        )
        self._r(
            "OkeApiNsgEgress-worker-icmp",
            nsg,
            direction="EGRESS",
            protocol=ICMP,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            icmp_options=icmp_opts(3, 4),
            description="Path-MTU discovery to worker nodes",
            opts=opts,
        )
        self._r(
            "OkeApiNsgEgress-pod-all",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.pod_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Control plane reaches pods on arbitrary ports for webhooks, exec, and metrics",
            opts=opts,
        )

    def _add_lb_nsg_rules(self, opts: pulumi.ResourceOptions) -> None:
        """Add ingress and egress rules to `lb_nsg`.

        Ingress: internet reaches the load balancer on HTTPS (443) and HTTP (80).

        Egress: load balancer forwards traffic to worker nodes on the NodePort
        range (30000-32767) and queries kube-proxy health (10256).

        Args:
            opts: Pulumi resource options applied to every rule resource.
        """
        nsg = self.lb_nsg.id

        # ── INGRESS ────────────────────────────────────────────────────
        self._r(
            "OkeLbNsgIngress-https",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=INTERNET,
            source_type="CIDR_BLOCK",
            tcp_options=tcp_port(443),
            description="Internet reaches the load balancer on HTTPS",
            opts=opts,
        )
        self._r(
            "OkeLbNsgIngress-http",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=INTERNET,
            source_type="CIDR_BLOCK",
            tcp_options=tcp_port(80),
            description="Internet reaches the load balancer on HTTP",
            opts=opts,
        )

        # ── EGRESS ─────────────────────────────────────────────────────
        self._r(
            "OkeLbNsgEgress-nodeport",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port_range(30000, 32767),
            description="Load balancer forwards requests to worker nodes via NodePort",
            opts=opts,
        )
        self._r(
            "OkeLbNsgEgress-kubeproxy",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(10256),
            description="Load balancer queries kube-proxy health check before routing",
            opts=opts,
        )

    def _add_worker_nsg_rules(self, opts: pulumi.ResourceOptions) -> None:
        """Add ingress and egress rules to `worker_nsg`.

        Ingress: API endpoint reaches kubelet (10250); load balancer reaches
        NodePort range and kube-proxy health; pods reach workers (OCI CNI VNIC
        communication); nodes reach each other (pod traffic across nodes);
        ICMP path-MTU from anywhere.

        Egress: workers reach the API server (6443, 12250); OCI services (OCIR,
        monitoring); pods (OCI CNI); other workers (node-to-node); internet on
        HTTPS (443) and HTTP (80) for image pulls; ICMP path-MTU.

        Args:
            opts: Pulumi resource options applied to every rule resource.
        """
        nsg = self.worker_nsg.id

        # ── INGRESS ────────────────────────────────────────────────────
        self._r(
            "OkeWorkerNsgIngress-api-kubelet",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.api_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(10250),
            description="Control plane calls kubelet for pod lifecycle, logs, and exec",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgIngress-api-icmp",
            nsg,
            direction="INGRESS",
            protocol=ICMP,
            source=self.api_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            icmp_options=icmp_opts(3, 4),
            description="Path-MTU discovery from control plane",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgIngress-lb-nodeport",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.lb_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port_range(30000, 32767),
            description="Load balancer forwards requests to workers via NodePort",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgIngress-lb-kubeproxy",
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.lb_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(10256),
            description="Load balancer health-checks worker via kube-proxy",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgIngress-pod-all",
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.pod_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Pods communicate with worker VNIC for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgIngress-worker-all",
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.worker_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Node-to-node traffic for OCI CNI pod communication across availability domains",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgIngress-icmp",
            nsg,
            direction="INGRESS",
            protocol=ICMP,
            source=INTERNET,
            source_type="CIDR_BLOCK",
            icmp_options=icmp_opts(3, 4),
            description="Path-MTU discovery from any source",
            opts=opts,
        )

        # ── EGRESS ─────────────────────────────────────────────────────
        self._r(
            "OkeWorkerNsgEgress-api-6443",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=self.api_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(6443),
            description="Workers register with and query the Kubernetes API server",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgEgress-api-12250",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=self.api_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(12250),
            description="Workers communicate with control plane on internal port",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgEgress-services",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=SVC_CIDR,
            destination_type="SERVICE_CIDR_BLOCK",
            description="Workers pull images from OCIR and send metrics and logs to OCI services",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgEgress-pod-all",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.pod_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Workers reach pod VNICs for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgEgress-worker-all",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Node-to-node traffic for OCI CNI pod communication across availability domains",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgEgress-inet-443",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            tcp_options=tcp_port(443),
            description="Workers pull container images and call external APIs via HTTPS",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgEgress-inet-80",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            tcp_options=tcp_port(80),
            description="Workers pull images from HTTP registries and access OCI pre-authenticated URLs",
            opts=opts,
        )
        self._r(
            "OkeWorkerNsgEgress-icmp",
            nsg,
            direction="EGRESS",
            protocol=ICMP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            icmp_options=icmp_opts(3, 4),
            description="Path-MTU discovery to internet",
            opts=opts,
        )

    def _add_pod_nsg_rules(self, opts: pulumi.ResourceOptions) -> None:
        """Add ingress and egress rules to `pod_nsg`.

        Ingress: API endpoint reaches pods on all ports (webhooks, exec,
        metrics); workers reach pod VNICs (OCI CNI); pods reach each other
        (pod-to-pod).

        Egress: pods reach each other; pods reach worker VNICs (OCI CNI);
        pods reach the API server (6443, 12250); OCI services (OCIR,
        monitoring); internet on HTTPS (443) and HTTP (80); ICMP path-MTU.

        Args:
            opts: Pulumi resource options applied to every rule resource.
        """
        nsg = self.pod_nsg.id

        # ── INGRESS ────────────────────────────────────────────────────
        self._r(
            "OkePodNsgIngress-api-all",
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.api_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Control plane reaches pods on arbitrary ports for webhooks, exec, and metrics scraping",
            opts=opts,
        )
        self._r(
            "OkePodNsgIngress-worker-all",
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.worker_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Worker nodes reach pod VNICs for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            "OkePodNsgIngress-pod-all",
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.pod_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Pod-to-pod communication (east-west traffic between workloads)",
            opts=opts,
        )

        # ── EGRESS ─────────────────────────────────────────────────────
        self._r(
            "OkePodNsgEgress-pod-all",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.pod_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Pod-to-pod communication (east-west traffic between workloads)",
            opts=opts,
        )
        self._r(
            "OkePodNsgEgress-worker-all",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Pods reach worker VNICs for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            "OkePodNsgEgress-api-6443",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=self.api_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(6443),
            description="Pods reach Kubernetes API server for service discovery and RBAC",
            opts=opts,
        )
        self._r(
            "OkePodNsgEgress-api-12250",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=self.api_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(12250),
            description="Pods reach control-plane internal port",
            opts=opts,
        )
        self._r(
            "OkePodNsgEgress-services",
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=SVC_CIDR,
            destination_type="SERVICE_CIDR_BLOCK",
            description="Pods reach OCI services for object storage, monitoring, and logging",
            opts=opts,
        )
        self._r(
            "OkePodNsgEgress-inet-443",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            tcp_options=tcp_port(443),
            description="Pods call external APIs and download dependencies via HTTPS",
            opts=opts,
        )
        self._r(
            "OkePodNsgEgress-inet-80",
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            tcp_options=tcp_port(80),
            description="Pods access HTTP endpoints and OCI pre-authenticated URLs",
            opts=opts,
        )
        self._r(
            "OkePodNsgEgress-icmp",
            nsg,
            direction="EGRESS",
            protocol=ICMP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            icmp_options=icmp_opts(3, 4),
            description="Path-MTU discovery to internet",
            opts=opts,
        )

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export standard OKE cluster stack outputs.

        Publishes outputs derived from the spell's logical name:

        - `{name}_cluster_id` — OCID of the OKE cluster.
        - `{name}_kubernetes_version` — Kubernetes version deployed.
        - `{name}_lb_nsg_id` — OCID of the load-balancer NSG.  Reference this
          value in the Kubernetes service annotation
          `oci.oraclecloud.com/security-group-ids` so that OCI attaches the
          correct NSG to every managed load balancer.

        Example:
            ```python
            oke = OkeCluster(name="okeinfra", ...)
            oke.export()
            # Exports: okeinfra_cluster_id, okeinfra_lb_nsg_id
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_cluster_id", self.id)
        pulumi.export(f"{prefix}_kubernetes_version", self.kubernetes_version)
        pulumi.export(f"{prefix}_lb_nsg_id", self.lb_nsg.id)

    def get_public_security_list_ids(self) -> list[pulumi.Output[str]]:
        """Return the ID of the public security list (populated with OKE rules).

        Returns:
            Single-element list containing the VCN public security list OCID
            as a `pulumi.Output[str]`, or an empty list when using `VcnRef`
            without a security list export.
        """
        sl = self.vcn.public_security_list
        return [sl.id] if sl is not None else []

    def get_private_security_list_ids(self) -> list[pulumi.Output[str]]:
        """Return the ID of the private security list (populated with OKE rules).

        Returns:
            Single-element list containing the VCN private security list OCID
            as a `pulumi.Output[str]`, or an empty list when using `VcnRef`
            without a security list export.
        """
        sl = self.vcn.private_security_list
        return [sl.id] if sl is not None else []

    def create_kubeconfig(self, filename: str) -> None:
        """Write a kubeconfig file for this OKE cluster.

        Fetches the cluster's kubeconfig content from the OCI API and writes
        it to `filename`.  The file is created or overwritten if it already
        exists.

        Args:
            filename: Absolute or relative path where the kubeconfig file
                should be written (e.g. `"/tmp/kubeconfig"`).
        """
        cluster_kube_config = self.cluster.id.apply(
            lambda cid: oci.containerengine.get_cluster_kube_config(cluster_id=cid)
        )
        cluster_kube_config.content.apply(lambda cc: open(filename, "w+").write(cc))  # type: ignore[union-attr]  # noqa: SIM115


__all__ = ["OkeCluster"]
