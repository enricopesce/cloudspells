"""OKE (Oracle Kubernetes Engine) cluster spell for CloudSpells.

Provides `OkeCluster`, a high-level Pulumi component that creates a complete
OKE cluster with a node pool and all required OCI security list rules.

Subnet mapping:

OKE resources are placed across two of the four VCN tiers:

- **Public subnet** — API endpoint (public IP for kubectl) + OCI Load Balancers
  created by `LoadBalancer` services.
- **Private subnet** — Worker node VNICs and pod IPs (`OCI_VCN_IP_NATIVE`).
  Both workers and pods share this subnet so pods can reach the internet via
  NAT Gateway, which is required for calling external services and APIs.
  Pod-to-pod security is enforced by Kubernetes `NetworkPolicy`, not by
  subnet routing — security lists cannot distinguish worker IPs from pod IPs
  within the same CIDR, and intra-subnet traffic bypasses security list rules
  entirely.
- **Secure subnet** — Not used by OKE; reserved for databases and secrets
  managers that must not initiate any internet connection.
- **Management subnet** — Not used by OKE directly; reserved for bastion hosts,
  monitoring agents, and VPN/FastConnect endpoints.

Security list strategy:

Rather than creating separate OKE security lists (which would consume the
OCI-imposed 5-list-per-subnet quota), `OkeCluster` adds its rules directly to
the VCN's shared security lists via `Vcn.add_security_list_rules`.  This uses
only 1 list per subnet, leaving 4 slots free for additional services.

Rules added by this spell:

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
- Egress: HTTPS (443) to internet (image pulls + pod external API calls).
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


class OkeCluster(BaseResource, AbstractKubernetes):
    """Oracle Kubernetes Engine cluster with node pool and security configuration.

    Deploys a `BASIC_CLUSTER` OKE cluster with OCI VCN-native pod networking
    (`OCI_VCN_IP_NATIVE` CNI) and a node pool spread across all availability
    domains in the region.

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
    image: pulumi.Input[str] | None
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
        kubernetes_version: pulumi.Input[str],
        shape: pulumi.Input[str],
        min_nodes: pulumi.Input[int],
        ocpus: pulumi.Input[float],
        memory_in_gbs: pulumi.Input[float],
        display_name: pulumi.Input[str],
        stack_name: str | None = None,
        ssh_public_key: pulumi.Input[str] | None = None,
        opts: pulumi.ResourceOptions | None = None,
        image: pulumi.Input[str] | None = None,
    ) -> None:
        """Create a complete OKE cluster infrastructure.

        Adds all required OKE security rules to the VCN, finalises the network,
        and then creates the Kubernetes control plane and node pool.

        Args:
            name: Logical name for the cluster resource (e.g. `"k8s"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` instance that provides the public and private subnets.
            kubernetes_version: Kubernetes version string
                (e.g. `"v1.30.1"`).
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
            image: Optional explicit boot image OCID for worker nodes.  When
                `None`, no image is pre-selected and OKE uses its default.
        """
        super().__init__("custom:oke:Cluster", name, compartment_id, stack_name, opts)

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

        # Add OKE security rules before finalising the network
        self._add_oke_security_lists_rules()
        self.vcn.finalize_network()

        # Aliases pointing to the VCN security lists (None when using VcnRef)
        self.oke_public_security_list = self.vcn.public_security_list  # type: ignore[assignment]
        self.oke_private_security_list = self.vcn.private_security_list  # type: ignore[assignment]

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

        image_id: pulumi.Input[str] | None = image

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
                node_pool_pod_network_option_details=oci.containerengine.NodePoolNodeConfigDetailsNodePoolPodNetworkOptionDetailsArgs(
                    cni_type="OCI_VCN_IP_NATIVE",
                    pod_subnet_ids=[self.vcn.private_subnet.id],  # type: ignore[union-attr]
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
        HTTPS (443) to internet (image pulls and pod external API calls);
        ICMP to internet.
        """
        # ═══════════════════════════════════════════════════════════════
        # PUBLIC SUBNET – API Endpoint + Load Balancer
        # ═══════════════════════════════════════════════════════════════

        private_subnet_cidr: pulumi.Input[str] = self.vcn.get_private_subnet_cidr()
        public_subnet_cidr: pulumi.Input[str] = self.vcn.get_public_subnet_cidr()

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
                destination=oci.core.get_services().services[0].cidr_block,
                destination_type="SERVICE_CIDR_BLOCK",
            ),
            # ICMP path-MTU to OCI services
            oci.core.SecurityListEgressSecurityRuleArgs(
                description="ICMP path discovery to OCI services for optimal network performance",
                protocol="1",  # ICMP
                destination=oci.core.get_services().services[0].cidr_block,
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
                destination=oci.core.get_services().services[0].cidr_block,
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
    # Public accessors
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export standard OKE cluster stack outputs.

        Publishes the cluster OCID under a key derived from the spell's
        logical name (e.g. `okeinfra_cluster_id` for name `"okeinfra"`).

        Example:
            ```python
            oke = OkeCluster(name="okeinfra", ...)
            oke.export()
            # Exports: okeinfra_cluster_id
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_cluster_id", self.id)

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
