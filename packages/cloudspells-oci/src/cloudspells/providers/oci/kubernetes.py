"""OKE (Oracle Kubernetes Engine) cluster spell for CloudSpells.

Provides `OkeCluster` and `NodePoolConfig`. `OkeCluster` is a high-level
Pulumi component that creates a complete OKE cluster with one or more node
pools, all required OCI security list rules, and four Network Security Groups
(NSGs) that segment traffic by component role. `NodePoolConfig` is the
dataclass used to describe each node pool.

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
- Ingress: HTTPS (443) and HTTP (80) from internet (Load Balancer).
- Ingress: Kubernetes API (6443) from each CIDR in `kubectl_allowed_cidrs` (kubectl).
- Egress: OCI services (cluster management and telemetry).
- Egress: Kubelet (10250), NodePort (30000-32767), kube-proxy (10256) to private.
- Egress: All traffic to private subnet (webhooks, admission controllers).

Private subnet (Worker nodes + Pods):

- Ingress: Kubelet (10250), NodePort (30000-32767), kube-proxy (10256) from public.
- Ingress: All traffic from public subnet (control plane to pods: webhooks).
- Egress: OCI services (OCIR image pulls, monitoring, logging).
- Egress: Kubernetes API (6443) and control-plane port (12250) to public subnet.
- Egress: HTTPS (443) and HTTP (80) to internet (image pulls + pod external API calls).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.kubernetes import AbstractKubernetes
from cloudspells.core.base import BaseResource

from ._oci_utils import get_svc_cidr as _get_svc_cidr
from .helper import get_ads
from .network import Vcn, VcnRef
from .nsg import ALL, INTERNET, TCP, tcp_port, tcp_port_range


class _HasId(Protocol):
    """Structural protocol for objects that expose a read-only `.id` output.

    Used as the type annotation for `OkeCluster.oke_public_security_list` and
    `OkeCluster.oke_private_security_list`.  Both `oci.core.SecurityList` (live
    `Vcn`) and `_SecurityListRef` (cross-stack `VcnRef`) satisfy this protocol
    because each exposes `.id` as a `pulumi.Output[str]`.  `None` is permitted
    when the source stack did not export the corresponding security list ID.
    """

    @property
    def id(self) -> pulumi.Output[str]: ...


@dataclass
class NodePoolConfig:
    """Configuration for a single OKE node pool.

    Pass a list of `NodePoolConfig` instances to `OkeCluster(node_pools=[...])`
    to create one or more node pools on the same cluster.  Each entry produces
    one `oci.containerengine.NodePool` placed in the private subnet and spread
    across all availability domains.

    Attributes:
        name: Short identifier for this pool (e.g. `"system"`, `"app"`).
            Used as the Pulumi resource name suffix and OCI display name
            component.  Must be unique within the list.
        shape: Compute shape for worker node VMs
            (e.g. `"VM.Standard.E4.Flex"`).
        image: Boot image OCID for worker nodes.
        node_count: Number of worker nodes.  Spread evenly across all
            availability domains in the region.
        ocpus: Number of OCPUs per worker node.
        memory_in_gbs: RAM in GiB per worker node.
        ssh_public_key: Optional SSH public key installed on worker nodes.
            Enables direct SSH access for debugging.  Defaults to `None`.
        boot_volume_size_in_gbs: Boot volume size in GiB for each worker
            node.  When `None` (default) OCI uses the minimum size defined
            by the image.  Must be at least 50 GiB when specified.
        initial_node_labels: Kubernetes labels applied to every node at
            join time (e.g. `{"role": "app"}`).  Used by node selectors
            and affinity rules.  Defaults to `None`.
        node_metadata: OCI instance metadata key/value pairs propagated to
            every worker node.  Pass `{"user_data": "<base64>"}` to inject
            a cloud-init script.  Defaults to `None`.
        eviction_grace_duration: ISO 8601 duration OCI waits for workloads
            to drain before terminating a node (e.g. `"PT1H"`).  When
            `None` OCI uses its built-in default.
        force_delete_after_grace: When `True`, OCI force-deletes the node
            even if workloads remain after `eviction_grace_duration`.
            Defaults to `False`.
        cycling_enabled: Enable rolling node replacement on pool updates.
            When `True`, OCI replaces nodes in batches controlled by
            `cycling_max_surge` and `cycling_max_unavailable`.  Defaults
            to `False`.
        cycling_max_surge: Maximum extra nodes provisioned during cycling
            (e.g. `"1"` or `"10%"`).  Defaults to `None` (OCI default).
        cycling_max_unavailable: Maximum nodes unavailable during cycling
            (e.g. `"0"` or `"10%"`).  Defaults to `None` (OCI default).

    Example:
        ```python
        node_pools = [
            NodePoolConfig(
                name="system",
                shape="VM.Standard.E4.Flex",
                image="ocid1.image.oc1...",
                node_count=3,
                ocpus=2,
                memory_in_gbs=16,
            ),
            NodePoolConfig(
                name="app",
                shape="VM.Standard.E4.Flex",
                image="ocid1.image.oc1...",
                node_count=5,
                ocpus=8,
                memory_in_gbs=64,
            ),
        ]
        cluster = OkeCluster(name="k8s", node_pools=node_pools, ...)
        ```
    """

    name: str
    shape: pulumi.Input[str]
    image: pulumi.Input[str]
    node_count: int
    ocpus: pulumi.Input[float]
    memory_in_gbs: pulumi.Input[float]
    ssh_public_key: pulumi.Input[str] | None = None
    boot_volume_size_in_gbs: int | None = None
    initial_node_labels: dict[str, str] | None = None
    node_metadata: dict[str, str] | None = None
    eviction_grace_duration: str | None = None
    force_delete_after_grace: bool = False
    cycling_enabled: bool = False
    cycling_max_surge: str | None = None
    cycling_max_unavailable: str | None = None


class OkeCluster(BaseResource, AbstractKubernetes):
    """Oracle Kubernetes Engine cluster with one or more node pools, security configuration, and NSGs.

    By default deploys a `BASIC_CLUSTER`; pass `enhanced=True` to create an
    `ENHANCED_CLUSTER` with OCI Workload Identity and cluster add-on lifecycle
    management.  Both cluster types use OCI VCN-native pod networking
    (`OCI_VCN_IP_NATIVE` CNI) with each node pool spread across all availability
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
        kubectl_allowed_cidrs: List of CIDRs permitted to reach the Kubernetes
            API endpoint on port 6443.  An empty list means no external kubectl
            access.
        api_nsg: NSG attached to the Kubernetes API endpoint VNIC.
        lb_nsg: NSG for OCI Load Balancers; apply via service annotation.
        worker_nsg: NSG attached to every worker node VNIC.
        pod_nsg: NSG attached to every pod VNIC (OCI CNI).
        oke_public_security_list: Alias for the VCN's public security list
            (populated with OKE rules after initialisation), or `None` when
            using `VcnRef` and the source stack did not export
            `public_security_list_id`.
        oke_private_security_list: Alias for the VCN's private security list
            (populated with OKE rules after initialisation), or `None` when
            using `VcnRef` and the source stack did not export
            `private_security_list_id`.
        cluster: The underlying `oci.containerengine.Cluster` resource.
        node_pools: List of `oci.containerengine.NodePool` resources, one
            per `NodePoolConfig` passed at construction time.
        id: `pulumi.Output[str]` of the cluster OCID.

    Example:
        ```python
        vcn = Vcn(name="lab", compartment_id=comp_id, stack_name="prod")

        cluster = OkeCluster(
            name="k8s",
            compartment_id=comp_id,
            vcn=vcn,
            kubernetes_version="v1.30.1",
            kubectl_allowed_cidrs=["203.0.113.0/24"],
            node_pools=[
                NodePoolConfig(
                    name="default",
                    shape="VM.Standard.E4.Flex",
                    image="ocid1.image.oc1...",
                    node_count=3,
                    ocpus=2,
                    memory_in_gbs=32,
                ),
            ],
        )

        # Attach lb_nsg to Load Balancer services via annotation:
        # oci.oraclecloud.com/security-group-ids: "<cluster.lb_nsg.id>"
        cluster.create_kubeconfig("/tmp/kubeconfig")
        ```
    """

    vcn: Vcn | VcnRef
    kubernetes_version: pulumi.Input[str]
    kubectl_allowed_cidrs: list[str]
    api_nsg: oci.core.NetworkSecurityGroup
    lb_nsg: oci.core.NetworkSecurityGroup
    worker_nsg: oci.core.NetworkSecurityGroup
    pod_nsg: oci.core.NetworkSecurityGroup
    # Aliases pointing to the VCN security lists.
    # The value is oci.core.SecurityList (for Vcn) or the private
    # _SecurityListRef stub (for VcnRef), or None.  Both expose `.id` as
    # pulumi.Output[str], which is sufficient for all downstream consumers.
    oke_public_security_list: _HasId | None
    oke_private_security_list: _HasId | None
    cluster: oci.containerengine.Cluster
    node_pools: list[oci.containerengine.NodePool]
    id: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        kubernetes_version: pulumi.Input[str],
        node_pools: list[NodePoolConfig],
        stack_name: str | None = None,
        enhanced: bool = False,
        kubectl_allowed_cidrs: list[str] | None = None,
        pods_cidr: str = "172.16.0.0/16",
        services_cidr: str = "172.17.0.0/16",
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a complete OKE cluster infrastructure.

        Adds all required OKE security rules to the VCN, finalises the network,
        creates four NSGs (api, lb, worker, pod) with NSG-to-NSG rules, and
        then creates the Kubernetes control plane and node pool.

        Args:
            name: Logical name for the cluster resource (e.g. `"k8s"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` that provides the public and private subnets.
            kubernetes_version: Kubernetes version string
                (e.g. `"v1.32.1"`).
            node_pools: List of `NodePoolConfig` descriptors.  Each entry
                creates a separate node pool on the cluster, enabling mixed
                shapes (e.g. a small system pool and a large app pool).
                Pass an empty list to create a cluster with no node pools
                (useful when pools are managed separately).
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.
            enhanced: When `True`, creates an `ENHANCED_CLUSTER` instead of
                the default `BASIC_CLUSTER`.  Enhanced clusters support OCI
                Workload Identity (pod-level OCI API auth without embedded
                credentials), cluster add-on lifecycle management, and OCI
                DevOps integration.  Defaults to `False`.
            kubectl_allowed_cidrs: CIDRs permitted to reach the Kubernetes
                API endpoint on port 6443.  Pass `None` (default) to allow
                no external kubectl access; a `pulumi.warn()` is emitted to
                remind the caller to set this explicitly.  Pass `[]` to
                suppress the warning while still blocking all external access.
                Pass one or more CIDRs (e.g. `["203.0.113.0/24"]`) to allow
                kubectl from those addresses.
            pods_cidr: CIDR block assigned to Kubernetes pod IPs.  Override
                when `172.16.0.0/16` conflicts with an existing network (e.g.
                a corporate VPN or on-premises route).  Defaults to
                `"172.16.0.0/16"`.
            services_cidr: CIDR block assigned to Kubernetes service
                (ClusterIP) IPs.  Override when `172.17.0.0/16` conflicts
                with an existing network.  Defaults to `"172.17.0.0/16"`.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            RuntimeError: If `vcn.public_subnet` or `vcn.private_subnet` is
                `None` after `finalize_network()` completes.  This should not
                occur with a fully constructed `Vcn`; it can happen with a
                `VcnRef` that targets a stack that did not export the expected
                subnet resources.
        """
        super().__init__("custom:oke:Cluster", name, compartment_id, stack_name, opts)

        if kubectl_allowed_cidrs is None:
            pulumi.warn(
                "OkeCluster: kubectl_allowed_cidrs is not set — no external kubectl access "
                "is allowed. Set kubectl_allowed_cidrs to a list of CIDRs (e.g. your office "
                "IP) to enable kubectl access to port 6443."
            )
            self.kubectl_allowed_cidrs = []
        else:
            self.kubectl_allowed_cidrs = kubectl_allowed_cidrs

        self.vcn = vcn
        self.kubernetes_version = kubernetes_version
        self._pods_cidr = pods_cidr
        self._services_cidr = services_cidr

        # Layer 1: subnet-level security list rules
        self._add_oke_security_lists_rules()
        self.vcn.finalize_network()

        # Aliases pointing to the VCN security lists (None when using VcnRef)
        self.oke_public_security_list = self.vcn.public_security_list
        self.oke_private_security_list = self.vcn.private_security_list

        if self.vcn.public_subnet is None:
            raise RuntimeError("VCN public subnet must exist after finalize_network().")
        if self.vcn.private_subnet is None:
            raise RuntimeError("VCN private subnet must exist after finalize_network().")

        # Layer 2: VNIC-level NSGs — must be created before cluster/node pool
        self._create_oke_nsgs()

        child_opts = pulumi.ResourceOptions(parent=self)

        cluster_name = self.create_resource_name("cluster")
        self.cluster = oci.containerengine.Cluster(
            cluster_name,
            compartment_id=self.compartment_id,
            name=cluster_name,
            kubernetes_version=self.kubernetes_version,
            options=oci.containerengine.ClusterOptionsArgs(
                service_lb_subnet_ids=[self.vcn.public_subnet.id],
                kubernetes_network_config=oci.containerengine.ClusterOptionsKubernetesNetworkConfigArgs(
                    pods_cidr=self._pods_cidr,
                    services_cidr=self._services_cidr,
                ),
            ),
            cluster_pod_network_options=[
                oci.containerengine.ClusterClusterPodNetworkOptionArgs(
                    cni_type="OCI_VCN_IP_NATIVE",
                )
            ],
            type="ENHANCED_CLUSTER" if enhanced else "BASIC_CLUSTER",
            vcn_id=self.vcn.id,
            endpoint_config=oci.containerengine.ClusterEndpointConfigArgs(
                subnet_id=self.vcn.public_subnet.id,  # type: ignore[union-attr]  # narrowed by RuntimeError guard at lines 342–343
                is_public_ip_enabled=True,
                nsg_ids=[self.api_nsg.id],
            ),
            freeform_tags=self.create_freeform_tags(cluster_name, "oke-cluster"),
            opts=child_opts,
        )

        self.id = self.cluster.id

        get_ad_names = oci.identity.get_availability_domains_output(compartment_id=self.compartment_id)
        ads = get_ad_names.availability_domains

        self.node_pools = []
        for cfg in node_pools:
            pool_name = self.create_resource_name(f"pool-{cfg.name}")
            pool = oci.containerengine.NodePool(
                pool_name,
                name=pool_name,
                cluster_id=self.cluster.id,
                compartment_id=self.compartment_id,
                kubernetes_version=self.kubernetes_version,
                node_config_details=oci.containerengine.NodePoolNodeConfigDetailsArgs(
                    placement_configs=pulumi.Output.all(
                        ads,
                        self.vcn.private_subnet.id,  # type: ignore[union-attr]  # narrowed by RuntimeError guard at lines 344–345
                    ).apply(lambda args: get_ads(args[0], args[1])),
                    size=cfg.node_count,
                    nsg_ids=[self.worker_nsg.id],
                    node_pool_pod_network_option_details=oci.containerengine.NodePoolNodeConfigDetailsNodePoolPodNetworkOptionDetailsArgs(
                        cni_type="OCI_VCN_IP_NATIVE",
                        pod_subnet_ids=[self.vcn.private_subnet.id],  # type: ignore[union-attr]  # narrowed by RuntimeError guard at lines 344–345
                        pod_nsg_ids=[self.pod_nsg.id],
                    ),
                ),
                node_shape=cfg.shape,
                node_shape_config=oci.containerengine.NodePoolNodeShapeConfigArgs(
                    memory_in_gbs=cfg.memory_in_gbs,
                    ocpus=cfg.ocpus,
                ),
                node_source_details=oci.containerengine.NodePoolNodeSourceDetailsArgs(
                    image_id=cfg.image,
                    source_type="IMAGE",
                    boot_volume_size_in_gbs=(
                        str(cfg.boot_volume_size_in_gbs) if cfg.boot_volume_size_in_gbs is not None else None
                    ),
                ),
                initial_node_labels=[
                    oci.containerengine.NodePoolInitialNodeLabelArgs(key=k, value=v)
                    for k, v in cfg.initial_node_labels.items()
                ]
                if cfg.initial_node_labels
                else None,
                node_metadata=cfg.node_metadata,
                node_eviction_node_pool_settings=oci.containerengine.NodePoolNodeEvictionNodePoolSettingsArgs(
                    eviction_grace_duration=cfg.eviction_grace_duration,
                    is_force_delete_after_grace_duration=cfg.force_delete_after_grace,
                )
                if cfg.eviction_grace_duration is not None or cfg.force_delete_after_grace
                else None,
                node_pool_cycling_details=oci.containerengine.NodePoolNodePoolCyclingDetailsArgs(
                    is_node_cycling_enabled=cfg.cycling_enabled,
                    maximum_surge=cfg.cycling_max_surge,
                    maximum_unavailable=cfg.cycling_max_unavailable,
                )
                if cfg.cycling_enabled
                else None,
                ssh_public_key=cfg.ssh_public_key or None,
                freeform_tags=self.create_freeform_tags(pool_name, "oke-node-pool"),
                opts=child_opts,
            )
            self.node_pools.append(pool)

        self.register_outputs({
            "cluster_id": self.cluster.id,
            "api_nsg_id": self.api_nsg.id,
            "lb_nsg_id": self.lb_nsg.id,
            "worker_nsg_id": self.worker_nsg.id,
            "pod_nsg_id": self.pod_nsg.id,
        })

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
        (12250) from private subnet (workers + pods); HTTPS (443) and HTTP (80)
        from internet (Load Balancer); Kubernetes API (6443) from each CIDR in
        `self.kubectl_allowed_cidrs` (kubectl).

        Public subnet egress: OCI services (telemetry, management); kubelet
        (10250), NodePort (30000-32767), and kube-proxy (10256) to private;
        all traffic to private (webhooks, admission controllers).

        Private subnet ingress: kubelet (10250), NodePort (30000-32767), and
        kube-proxy (10256) from public; all traffic from public (control plane
        to pods for webhooks).

        Private subnet egress: OCI services (OCIR, monitoring, logging);
        Kubernetes API (6443) and control-plane port (12250) to public;
        HTTPS (443) and HTTP (80) to internet (image pulls and pod external
        API calls).
        """
        # ═══════════════════════════════════════════════════════════════
        # PUBLIC SUBNET – API Endpoint + Load Balancer
        # ═══════════════════════════════════════════════════════════════

        private_subnet_cidr: pulumi.Input[str] = self.vcn.get_private_subnet_cidr()
        public_subnet_cidr: pulumi.Input[str] = self.vcn.get_public_subnet_cidr()
        svc_cidr: pulumi.Output[str] = _get_svc_cidr()

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

        # External clients (kubectl) → API server — one rule per allowed CIDR.
        # An empty list means no external kubectl access is provisioned.
        for cidr in self.kubectl_allowed_cidrs:
            public_ingress_rules.append(
                oci.core.SecurityListIngressSecurityRuleArgs(
                    description=f"Allow kubectl access to Kubernetes API from {cidr}",
                    protocol="6",  # TCP
                    source=cidr,
                    source_type="CIDR_BLOCK",
                    tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(
                        min=6443,
                        max=6443,
                    ),
                )
            )

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
        api_nsg_name = self.create_resource_name("api-nsg")
        self.api_nsg = oci.core.NetworkSecurityGroup(
            api_nsg_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=api_nsg_name,
            freeform_tags=self.create_freeform_tags(api_nsg_name, "nsg"),
            opts=opts,
        )
        lb_nsg_name = self.create_resource_name("lb-nsg")
        self.lb_nsg = oci.core.NetworkSecurityGroup(
            lb_nsg_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=lb_nsg_name,
            freeform_tags=self.create_freeform_tags(lb_nsg_name, "nsg"),
            opts=opts,
        )
        worker_nsg_name = self.create_resource_name("worker-nsg")
        self.worker_nsg = oci.core.NetworkSecurityGroup(
            worker_nsg_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=worker_nsg_name,
            freeform_tags=self.create_freeform_tags(worker_nsg_name, "nsg"),
            opts=opts,
        )
        pod_nsg_name = self.create_resource_name("pod-nsg")
        self.pod_nsg = oci.core.NetworkSecurityGroup(
            pod_nsg_name,
            compartment_id=self.compartment_id,
            vcn_id=self.vcn.id,
            display_name=pod_nsg_name,
            freeform_tags=self.create_freeform_tags(pod_nsg_name, "nsg"),
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
            protocol: OCI protocol identifier — use the `TCP` or `ALL`
                constants imported from `nsg.py`.
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
        control-plane port (12250); one rule per CIDR in
        `self.kubectl_allowed_cidrs` permits external kubectl access on 6443.
        No kubectl rule is created when the list is empty.

        Egress: control plane reaches OCI services (telemetry), kubelet on
        workers (10250), and all ports on pods (webhooks, exec, metrics).

        Args:
            opts: Pulumi resource options applied to every rule resource.
        """
        nsg = self.api_nsg.id

        # ── INGRESS ────────────────────────────────────────────────────
        self._r(
            self.create_resource_name("api-nsg-ingress-worker-6443"),
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
            self.create_resource_name("api-nsg-ingress-worker-12250"),
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
            self.create_resource_name("api-nsg-ingress-pod-6443"),
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
            self.create_resource_name("api-nsg-ingress-pod-12250"),
            nsg,
            direction="INGRESS",
            protocol=TCP,
            source=self.pod_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            tcp_options=tcp_port(12250),
            description="Pods reach Kubernetes control-plane internal port",
            opts=opts,
        )
        # External clients (kubectl) → API server — one rule per allowed CIDR.
        # An empty list means no external kubectl access is provisioned.
        for i, cidr in enumerate(self.kubectl_allowed_cidrs):
            self._r(
                self.create_resource_name(f"api-nsg-ingress-kubectl-{i}"),
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=cidr,
                source_type="CIDR_BLOCK",
                tcp_options=tcp_port(6443),
                description=f"External kubectl and CI tooling reach the Kubernetes API from {cidr}",
                opts=opts,
            )

        # ── EGRESS ─────────────────────────────────────────────────────
        self._r(
            self.create_resource_name("api-nsg-egress-services"),
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=_get_svc_cidr(),
            destination_type="SERVICE_CIDR_BLOCK",
            description="Control plane sends telemetry and management traffic to OCI services",
            opts=opts,
        )
        self._r(
            self.create_resource_name("api-nsg-egress-worker-kubelet"),
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
            self.create_resource_name("api-nsg-egress-pod-all"),
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
            self.create_resource_name("lb-nsg-ingress-https"),
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
            self.create_resource_name("lb-nsg-ingress-http"),
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
            self.create_resource_name("lb-nsg-egress-nodeport"),
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
            self.create_resource_name("lb-nsg-egress-kubeproxy"),
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
        communication); nodes reach each other (pod traffic across nodes).

        Egress: workers reach the API server (6443, 12250); OCI services (OCIR,
        monitoring); pods (OCI CNI); other workers (node-to-node); internet on
        HTTPS (443) and HTTP (80) for image pulls.

        Args:
            opts: Pulumi resource options applied to every rule resource.
        """
        nsg = self.worker_nsg.id

        # ── INGRESS ────────────────────────────────────────────────────
        self._r(
            self.create_resource_name("worker-nsg-ingress-api-kubelet"),
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
            self.create_resource_name("worker-nsg-ingress-lb-nodeport"),
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
            self.create_resource_name("worker-nsg-ingress-lb-kubeproxy"),
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
            self.create_resource_name("worker-nsg-ingress-pod-all"),
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.pod_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Pods communicate with worker VNIC for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            self.create_resource_name("worker-nsg-ingress-worker-all"),
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.worker_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Node-to-node traffic for OCI CNI pod communication across availability domains",
            opts=opts,
        )
        # ── EGRESS ─────────────────────────────────────────────────────
        self._r(
            self.create_resource_name("worker-nsg-egress-api-6443"),
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
            self.create_resource_name("worker-nsg-egress-api-12250"),
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
            self.create_resource_name("worker-nsg-egress-services"),
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=_get_svc_cidr(),
            destination_type="SERVICE_CIDR_BLOCK",
            description="Workers pull images from OCIR and send metrics and logs to OCI services",
            opts=opts,
        )
        self._r(
            self.create_resource_name("worker-nsg-egress-pod-all"),
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.pod_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Workers reach pod VNICs for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            self.create_resource_name("worker-nsg-egress-worker-all"),
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Node-to-node traffic for OCI CNI pod communication across availability domains",
            opts=opts,
        )
        self._r(
            self.create_resource_name("worker-nsg-egress-inet-443"),
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
            self.create_resource_name("worker-nsg-egress-inet-80"),
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            tcp_options=tcp_port(80),
            description="Workers pull images from HTTP registries and access OCI pre-authenticated URLs",
            opts=opts,
        )

    def _add_pod_nsg_rules(self, opts: pulumi.ResourceOptions) -> None:
        """Add ingress and egress rules to `pod_nsg`.

        Ingress: API endpoint reaches pods on all ports (webhooks, exec,
        metrics); workers reach pod VNICs (OCI CNI); pods reach each other
        (pod-to-pod).

        Egress: pods reach each other; pods reach worker VNICs (OCI CNI);
        pods reach the API server (6443, 12250); OCI services (OCIR,
        monitoring); internet on HTTPS (443) and HTTP (80).

        Args:
            opts: Pulumi resource options applied to every rule resource.
        """
        nsg = self.pod_nsg.id

        # ── INGRESS ────────────────────────────────────────────────────
        self._r(
            self.create_resource_name("pod-nsg-ingress-api-all"),
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.api_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Control plane reaches pods on arbitrary ports for webhooks, exec, and metrics scraping",
            opts=opts,
        )
        self._r(
            self.create_resource_name("pod-nsg-ingress-worker-all"),
            nsg,
            direction="INGRESS",
            protocol=ALL,
            source=self.worker_nsg.id,
            source_type="NETWORK_SECURITY_GROUP",
            description="Worker nodes reach pod VNICs for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            self.create_resource_name("pod-nsg-ingress-pod-all"),
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
            self.create_resource_name("pod-nsg-egress-pod-all"),
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.pod_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Pod-to-pod communication (east-west traffic between workloads)",
            opts=opts,
        )
        self._r(
            self.create_resource_name("pod-nsg-egress-worker-all"),
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=self.worker_nsg.id,
            destination_type="NETWORK_SECURITY_GROUP",
            description="Pods reach worker VNICs for OCI CNI VNIC-native networking",
            opts=opts,
        )
        self._r(
            self.create_resource_name("pod-nsg-egress-api-6443"),
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
            self.create_resource_name("pod-nsg-egress-api-12250"),
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
            self.create_resource_name("pod-nsg-egress-services"),
            nsg,
            direction="EGRESS",
            protocol=ALL,
            destination=_get_svc_cidr(),
            destination_type="SERVICE_CIDR_BLOCK",
            description="Pods reach OCI services for object storage, monitoring, and logging",
            opts=opts,
        )
        self._r(
            self.create_resource_name("pod-nsg-egress-inet-443"),
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
            self.create_resource_name("pod-nsg-egress-inet-80"),
            nsg,
            direction="EGRESS",
            protocol=TCP,
            destination=INTERNET,
            destination_type="CIDR_BLOCK",
            tcp_options=tcp_port(80),
            description="Pods access HTTP endpoints and OCI pre-authenticated URLs",
            opts=opts,
        )

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def export(self) -> None:
        """Export standard OKE cluster stack outputs.

        Publishes outputs derived from the spell's logical name:

        - `{name}_cluster_id` — OCID of the OKE cluster.
        - `{name}_cluster_endpoint` — Kubernetes API server public endpoint URL.
        - `{name}_kubernetes_version` — Kubernetes version deployed.
        - `{name}_lb_nsg_id` — OCID of the load-balancer NSG.  Reference this
          value in the Kubernetes service annotation
          `oci.oraclecloud.com/security-group-ids` so that OCI attaches the
          correct NSG to every managed load balancer.
        - `{name}_kubeconfig` — kubectl-compatible kubeconfig (Pulumi secret).
          Not exported during `pulumi preview` — only available after a real
          `pulumi up` completes.

        Example:
            ```python
            oke = OkeCluster(name="okeinfra", ...)
            oke.export()
            # Exports: okeinfra_cluster_id, okeinfra_cluster_endpoint,
            #          okeinfra_kubernetes_version, okeinfra_lb_nsg_id,
            #          okeinfra_kubeconfig (secret)
            ```
        """
        prefix = self.name.replace("-", "_")
        pulumi.export(f"{prefix}_cluster_id", self.id)
        pulumi.export(f"{prefix}_cluster_endpoint", self.cluster.endpoints.public_endpoint)
        pulumi.export(f"{prefix}_kubernetes_version", self.kubernetes_version)
        pulumi.export(f"{prefix}_lb_nsg_id", self.lb_nsg.id)

        # Kubeconfig requires a real cluster OCID — skip during preview.
        if not pulumi.runtime.is_dry_run():
            kubeconfig = self.cluster.id.apply(
                lambda cid: oci.containerengine.get_cluster_kube_config(cluster_id=cid).content
            )
            pulumi.export(f"{prefix}_kubeconfig", pulumi.Output.secret(kubeconfig))

    def get_public_security_list_ids(self) -> list[pulumi.Output[str]]:
        """Return the OCIDs of the public security lists populated with OKE rules.

        Returns:
            Single-element list containing the VCN public security list OCID
            as a `pulumi.Output[str]`, or an empty list when using `VcnRef`
            without a security list export.

        Example:
            ```python
            cluster = OkeCluster(name="k8s", ...)
            sl_ids = cluster.get_public_security_list_ids()
            # sl_ids == [<pulumi.Output[str] of public security list OCID>]
            # sl_ids == []  when VcnRef does not export the security list
            ```
        """
        sl = self.vcn.public_security_list
        return [sl.id] if sl is not None else []

    def get_private_security_list_ids(self) -> list[pulumi.Output[str]]:
        """Return the OCIDs of the private security lists populated with OKE rules.

        Returns:
            Single-element list containing the VCN private security list OCID
            as a `pulumi.Output[str]`, or an empty list when using `VcnRef`
            without a security list export.

        Example:
            ```python
            cluster = OkeCluster(name="k8s", ...)
            sl_ids = cluster.get_private_security_list_ids()
            # sl_ids == [<pulumi.Output[str] of private security list OCID>]
            # sl_ids == []  when VcnRef does not export the security list
            ```
        """
        sl = self.vcn.private_security_list
        return [sl.id] if sl is not None else []

    def create_kubeconfig(self, filename: str) -> None:
        """Write a kubeconfig file for this OKE cluster during `pulumi up`.

        Schedules the kubeconfig fetch and file write as a Pulumi output
        callback: the OCI API call and file write execute only during
        `pulumi up`, after the cluster OCID is known.  Calling this during
        `pulumi preview` is safe but has no effect — the file is not written
        until a real deployment completes.  The file is created or overwritten
        if it already exists.

        Args:
            filename: Absolute or relative path where the kubeconfig file
                should be written (e.g. `"/tmp/kubeconfig"`).

        Raises:
            OSError: If `filename` cannot be created or written to (e.g.
                the parent directory does not exist or the process lacks
                write permission).

        Example:
            ```python
            cluster = OkeCluster(name="k8s", ...)
            cluster.create_kubeconfig("/tmp/k8s-kubeconfig")
            # The file is written after `pulumi up` completes successfully.
            # export KUBECONFIG=/tmp/k8s-kubeconfig
            ```
        """
        # Guard against dry-run: during `pulumi preview` the cluster OCID is
        # unknown and the OCI API call would fail or produce a misleading error.
        # The file write is a side-effect that must only happen on real deploys.
        if pulumi.runtime.is_dry_run():
            return

        # TODO: use get_cluster_kube_config_output form once the downstream
        # .content.apply(_write) chain can be rewritten to handle a nested
        # pulumi.Output without double-wrapping.
        cluster_kube_config = self.cluster.id.apply(
            lambda cid: oci.containerengine.get_cluster_kube_config(cluster_id=cid)
        )

        def _write(cc: str) -> None:
            with open(filename, "w") as f:
                f.write(cc)

        cluster_kube_config.content.apply(_write)  # type: ignore[union-attr]  # content is Optional[str] in stubs but never None for a live cluster


__all__ = ["NodePoolConfig", "OkeCluster"]
