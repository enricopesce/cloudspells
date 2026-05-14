"""OKE (Oracle Kubernetes Engine) cluster spells for CloudSpells.

Provides two cluster spells and a node-pool descriptor:

- `OkeCluster` — `BASIC_CLUSTER` with flannel-style OCI VCN-native pod
  networking.  Lean, fast to provision, suitable for standard workloads.
- `OkeClusterEnhanced` — `ENHANCED_CLUSTER` with OCI Workload Identity, cluster
  add-on lifecycle management, and OCI DevOps integration.  Use when pods need
  to authenticate to OCI APIs without embedded credentials.
- `NodePoolConfig` — dataclass describing each node pool.

Both cluster spells share identical networking, NSG, and node-pool logic via
the private `_OkeClusterMixin` (CS-011); they differ only in the OCI `type=`
setting passed to `oci.containerengine.Cluster`.

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
   routing policy.  Live `Vcn` instances install the CloudSpells OKE network
   profile before subnet creation, while `VcnRef` instances verify that the
   source stack already exported the exact profile.  The underlying rules
   still consume only 1 list per subnet and leave 4 slots free for additional
   services.

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

Pods and services CIDR blocks are hard-coded as opinionated internal defaults
(`10.244.0.0/16` for pods, `10.96.0.0/16` for services).  These match common
upstream Kubernetes defaults and are intentionally not exposed as constructor
parameters (CS-001, CS-003).

Security list rules installed by the OKE network profile:

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
from pathlib import Path
from typing import Protocol

import pulumi
import pulumi_oci as oci
from cloudspells.core.abstractions.kubernetes import AbstractKubernetes
from cloudspells.core.base import BaseResource

from ._naming import ordinal_suffix
from ._network_profiles import oke_profile_id
from ._oci_utils import get_svc_cidr as _get_svc_cidr
from .helper import get_ads
from .network import Vcn, VcnRef
from .nsg import ALL, INTERNET, TCP

# Opinionated internal defaults for pod and service CIDRs.  Match common
# upstream Kubernetes defaults and stay out of OCI's `10.0.0.0/16` VCN range.
# Not exposed as constructor parameters (CS-001, CS-003).
_PODS_CIDR = "10.244.0.0/16"
_SERVICES_CIDR = "10.96.0.0/16"


def _nsg_tcp_port(port: int) -> oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs:
    return oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsDestinationPortRangeArgs(
            min=port,
            max=port,
        )
    )


def _nsg_tcp_port_range(min_port: int, max_port: int) -> oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs:
    return oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsArgs(
        destination_port_range=oci.core.NetworkSecurityGroupSecurityRuleTcpOptionsDestinationPortRangeArgs(
            min=min_port,
            max=max_port,
        )
    )


class _HasId(Protocol):
    """Structural protocol for objects that expose a read-only `.id` output.

    Used as the type annotation for `oke_public_security_list` and
    `oke_private_security_list`.  Both `oci.core.SecurityList` (live
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
    or `OkeClusterEnhanced(node_pools=[...])` to create one or more node pools
    on the same cluster.  Each entry produces one
    `oci.containerengine.NodePool` placed in the private subnet and spread
    across all availability domains.

    Attributes:
        name: Short identifier for this pool (e.g. `"system"`, `"app"`).
            Used as a semantic label in tags and examples.  CloudSpells owns
            the Pulumi resource-name suffix for each pool.
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


class _OkeClusterMixin:
    """Shared implementation for `OkeCluster` and `OkeClusterEnhanced`.

    Not exported. Holds the network-setup, NSG construction, node-pool
    wiring, kubeconfig, and public-accessor logic that is identical between
    the basic and enhanced cluster spells. The concrete spells differ only
    in the OCI `type=` setting passed to `oci.containerengine.Cluster`.

    Concrete spells must inherit `(_OkeClusterMixin, BaseResource)` (CS-011)
    and set `_CLUSTER_TYPE` to `"BASIC_CLUSTER"` or `"ENHANCED_CLUSTER"` as
    a class attribute.
    """

    # Concrete subclasses override this.
    _CLUSTER_TYPE: str = "BASIC_CLUSTER"

    # Typed attributes set during __init__.  Duplicated in the concrete
    # class attribute declarations for mkdocstrings visibility.
    vcn: Vcn | VcnRef
    kubernetes_version: pulumi.Input[str]
    kubectl_allowed_cidrs: list[str]
    api_nsg: oci.core.NetworkSecurityGroup
    lb_nsg: oci.core.NetworkSecurityGroup
    worker_nsg: oci.core.NetworkSecurityGroup
    pod_nsg: oci.core.NetworkSecurityGroup
    oke_public_security_list: _HasId | None
    oke_private_security_list: _HasId | None
    cluster: oci.containerengine.Cluster
    node_pools: list[oci.containerengine.NodePool]
    id: pulumi.Output[str]
    _api_nsg_rules: list[oci.core.NetworkSecurityGroupSecurityRule]
    _lb_nsg_rules: list[oci.core.NetworkSecurityGroupSecurityRule]
    _worker_nsg_rules: list[oci.core.NetworkSecurityGroupSecurityRule]
    _pod_nsg_rules: list[oci.core.NetworkSecurityGroupSecurityRule]

    def _build_cluster(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        vcn: Vcn | VcnRef,
        kubernetes_version: pulumi.Input[str],
        node_pools: list[NodePoolConfig],
        kubectl_allowed_cidrs: list[str] | None,
    ) -> None:
        """Construct the cluster, NSGs, and node pools.

        Called by the concrete `__init__` after `super().__init__()` has run.
        Implements the full provisioning workflow and materialises every
        attribute exposed by this mixin.

        Args:
            name: Logical name for the cluster resource.
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` that provides the public and private subnets.
            kubernetes_version: Kubernetes version string.
            node_pools: List of `NodePoolConfig` descriptors.
            kubectl_allowed_cidrs: CIDRs permitted to reach the Kubernetes API,
                or `None` to disable external kubectl access (emits a warning).

        Raises:
            RuntimeError: If `vcn.public_subnet` or `vcn.private_subnet` is
                `None` after `finalize_network()` completes.
        """
        # Initialise mutable attributes first so partially-constructed
        # instances expose a consistent shape even if a later step raises.
        self.node_pools = []
        self._api_nsg_rules = []
        self._lb_nsg_rules = []
        self._worker_nsg_rules = []
        self._pod_nsg_rules = []

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

        # Layer 1: subnet-level security profile
        network_profile_check: str | pulumi.Output[str] | None = None
        if isinstance(self.vcn, Vcn):
            self.vcn.enable_oke_profile(self.kubectl_allowed_cidrs)
        else:
            network_profile_check = self.vcn.require_network_profile(oke_profile_id(self.kubectl_allowed_cidrs))
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

        # Collect every NSG rule so cluster and node pools can declare an
        # explicit depends_on. This guarantees the rules exist before any
        # node tries to reach the API, the load balancer, or another node.
        nsg_rules: list[pulumi.Resource] = [
            *self._api_nsg_rules,
            *self._worker_nsg_rules,
            *self._pod_nsg_rules,
            *self._lb_nsg_rules,
        ]

        child_opts = pulumi.ResourceOptions(parent=self)  # type: ignore[arg-type]
        cluster_opts = pulumi.ResourceOptions(parent=self, depends_on=nsg_rules)  # type: ignore[arg-type]

        cluster_name = self.create_resource_name("cluster")  # type: ignore[attr-defined]
        self.cluster = oci.containerengine.Cluster(
            cluster_name,
            compartment_id=compartment_id,
            name=cluster_name,
            kubernetes_version=kubernetes_version,
            options=oci.containerengine.ClusterOptionsArgs(
                service_lb_subnet_ids=[self.vcn.public_subnet.id],
                kubernetes_network_config=oci.containerengine.ClusterOptionsKubernetesNetworkConfigArgs(
                    pods_cidr=_PODS_CIDR,
                    services_cidr=_SERVICES_CIDR,
                ),
            ),
            cluster_pod_network_options=[
                oci.containerengine.ClusterClusterPodNetworkOptionArgs(
                    cni_type="OCI_VCN_IP_NATIVE",
                )
            ],
            type=self._CLUSTER_TYPE,
            vcn_id=self.vcn.id,
            endpoint_config=oci.containerengine.ClusterEndpointConfigArgs(
                subnet_id=self.vcn.public_subnet.id,  # type: ignore[union-attr]  # narrowed by subnet-None guard above
                is_public_ip_enabled=True,
                nsg_ids=[self.api_nsg.id],
            ),
            freeform_tags=self.create_freeform_tags(cluster_name, "oke-cluster"),  # type: ignore[attr-defined]
            opts=cluster_opts,
        )

        self.id = self.cluster.id

        get_ad_names = oci.identity.get_availability_domains_output(compartment_id=compartment_id)
        ads = get_ad_names.availability_domains

        for index, cfg in enumerate(node_pools):
            legacy_pool_name = f"{self.stack_name}-{self.name}-pool-{cfg.name}"  # type: ignore[attr-defined]
            pool_name = self.create_resource_name(ordinal_suffix("pool", index))  # type: ignore[attr-defined]
            pool = oci.containerengine.NodePool(
                pool_name,
                name=pool_name,
                cluster_id=self.cluster.id,
                compartment_id=compartment_id,
                kubernetes_version=kubernetes_version,
                node_config_details=oci.containerengine.NodePoolNodeConfigDetailsArgs(
                    placement_configs=pulumi.Output.all(
                        ads,
                        self.vcn.private_subnet.id,  # type: ignore[union-attr]  # narrowed by subnet-None guard above
                    ).apply(lambda args: get_ads(args[0], args[1])),
                    size=cfg.node_count,
                    nsg_ids=[self.worker_nsg.id],
                    node_pool_pod_network_option_details=oci.containerengine.NodePoolNodeConfigDetailsNodePoolPodNetworkOptionDetailsArgs(
                        cni_type="OCI_VCN_IP_NATIVE",
                        pod_subnet_ids=[self.vcn.private_subnet.id],  # type: ignore[union-attr]  # narrowed by subnet-None guard above
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
                freeform_tags=self.create_freeform_tags(  # type: ignore[attr-defined]
                    pool_name,
                    "oke-node-pool",
                    {"PoolLabel": cfg.name},
                ),
                opts=pulumi.ResourceOptions(
                    parent=self,  # type: ignore[arg-type]
                    depends_on=nsg_rules,
                    aliases=[pulumi.Alias(name=legacy_pool_name)],
                ),
            )
            self.node_pools.append(pool)

        # Silence unused in static analysis when no rules are added.
        _ = child_opts

        outputs: dict[str, pulumi.Output[str] | str] = {
            "cluster_id": self.cluster.id,
            "api_nsg_id": self.api_nsg.id,
            "lb_nsg_id": self.lb_nsg.id,
            "worker_nsg_id": self.worker_nsg.id,
            "pod_nsg_id": self.pod_nsg.id,
        }
        if network_profile_check is not None:
            outputs["network_profile_check"] = network_profile_check

        self.register_outputs(outputs)  # type: ignore[attr-defined]

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
        opts = pulumi.ResourceOptions(parent=self)  # type: ignore[arg-type]

        # ── Create the four NSG objects ────────────────────────────────
        api_nsg_name = self.create_resource_name("api-nsg")  # type: ignore[attr-defined]
        self.api_nsg = oci.core.NetworkSecurityGroup(
            api_nsg_name,
            compartment_id=self.compartment_id,  # type: ignore[attr-defined]
            vcn_id=self.vcn.id,
            display_name=api_nsg_name,
            freeform_tags=self.create_freeform_tags(api_nsg_name, "nsg"),  # type: ignore[attr-defined]
            opts=opts,
        )
        lb_nsg_name = self.create_resource_name("lb-nsg")  # type: ignore[attr-defined]
        self.lb_nsg = oci.core.NetworkSecurityGroup(
            lb_nsg_name,
            compartment_id=self.compartment_id,  # type: ignore[attr-defined]
            vcn_id=self.vcn.id,
            display_name=lb_nsg_name,
            freeform_tags=self.create_freeform_tags(lb_nsg_name, "nsg"),  # type: ignore[attr-defined]
            opts=opts,
        )
        worker_nsg_name = self.create_resource_name("worker-nsg")  # type: ignore[attr-defined]
        self.worker_nsg = oci.core.NetworkSecurityGroup(
            worker_nsg_name,
            compartment_id=self.compartment_id,  # type: ignore[attr-defined]
            vcn_id=self.vcn.id,
            display_name=worker_nsg_name,
            freeform_tags=self.create_freeform_tags(worker_nsg_name, "nsg"),  # type: ignore[attr-defined]
            opts=opts,
        )
        pod_nsg_name = self.create_resource_name("pod-nsg")  # type: ignore[attr-defined]
        self.pod_nsg = oci.core.NetworkSecurityGroup(
            pod_nsg_name,
            compartment_id=self.compartment_id,  # type: ignore[attr-defined]
            vcn_id=self.vcn.id,
            display_name=pod_nsg_name,
            freeform_tags=self.create_freeform_tags(pod_nsg_name, "nsg"),  # type: ignore[attr-defined]
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
        boilerplate.  `name` must be unique within this component.

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
            tcp_options: TCP port restriction built internally.
            icmp_options: ICMP type/code options built internally.
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
        rules = self._api_nsg_rules

        # ── INGRESS ────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("api-nsg-ingress-worker-6443"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=self.worker_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(6443),
                description="Worker nodes reach Kubernetes API server",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("api-nsg-ingress-worker-12250"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=self.worker_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(12250),
                description="Worker nodes reach Kubernetes control-plane internal port",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("api-nsg-ingress-pod-6443"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=self.pod_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(6443),
                description="Pods reach Kubernetes API server for service discovery and RBAC",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("api-nsg-ingress-pod-12250"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=self.pod_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(12250),
                description="Pods reach Kubernetes control-plane internal port",
                opts=opts,
            )
        )
        # External clients (kubectl) → API server — one rule per allowed CIDR.
        # An empty list means no external kubectl access is provisioned.
        for index, cidr in enumerate(self.kubectl_allowed_cidrs):
            legacy_rule_name = f"{self.stack_name}-{self.name}-api-nsg-ingress-kubectl-{index}"  # type: ignore[attr-defined]
            rules.append(
                self._r(
                    self.create_resource_name(ordinal_suffix("api-nsg-ingress-kubectl", index)),  # type: ignore[attr-defined]
                    nsg,
                    direction="INGRESS",
                    protocol=TCP,
                    source=cidr,
                    source_type="CIDR_BLOCK",
                    tcp_options=_nsg_tcp_port(6443),
                    description=f"External kubectl and CI tooling reach the Kubernetes API from {cidr}",
                    opts=pulumi.ResourceOptions(
                        parent=self,  # type: ignore[arg-type]
                        aliases=[pulumi.Alias(name=legacy_rule_name)],
                    ),
                )
            )

        # ── EGRESS ─────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("api-nsg-egress-services"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=_get_svc_cidr(),
                destination_type="SERVICE_CIDR_BLOCK",
                description="Control plane sends telemetry and management traffic to OCI services",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("api-nsg-egress-worker-kubelet"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=self.worker_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(10250),
                description="Control plane calls kubelet on worker nodes for pod lifecycle operations",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("api-nsg-egress-pod-all"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=self.pod_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                description="Control plane reaches pods on arbitrary ports for webhooks, exec, and metrics",
                opts=opts,
            )
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
        rules = self._lb_nsg_rules

        # ── INGRESS ────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("lb-nsg-ingress-https"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=INTERNET,
                source_type="CIDR_BLOCK",
                tcp_options=_nsg_tcp_port(443),
                description="Internet reaches the load balancer on HTTPS",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("lb-nsg-ingress-http"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=INTERNET,
                source_type="CIDR_BLOCK",
                tcp_options=_nsg_tcp_port(80),
                description="Internet reaches the load balancer on HTTP",
                opts=opts,
            )
        )

        # ── EGRESS ─────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("lb-nsg-egress-nodeport"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=self.worker_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port_range(30000, 32767),
                description="Load balancer forwards requests to worker nodes via NodePort",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("lb-nsg-egress-kubeproxy"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=self.worker_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(10256),
                description="Load balancer queries kube-proxy health check before routing",
                opts=opts,
            )
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
        rules = self._worker_nsg_rules

        # ── INGRESS ────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-ingress-api-kubelet"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=self.api_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(10250),
                description="Control plane calls kubelet for pod lifecycle, logs, and exec",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-ingress-lb-nodeport"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=self.lb_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port_range(30000, 32767),
                description="Load balancer forwards requests to workers via NodePort",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-ingress-lb-kubeproxy"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=TCP,
                source=self.lb_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(10256),
                description="Load balancer health-checks worker via kube-proxy",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-ingress-pod-all"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=ALL,
                source=self.pod_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                description="Pods communicate with worker VNIC for OCI CNI VNIC-native networking",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-ingress-worker-all"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=ALL,
                source=self.worker_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                description="Node-to-node traffic for OCI CNI pod communication across availability domains",
                opts=opts,
            )
        )
        # ── EGRESS ─────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-egress-api-6443"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=self.api_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(6443),
                description="Workers register with and query the Kubernetes API server",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-egress-api-12250"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=self.api_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(12250),
                description="Workers communicate with control plane on internal port",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-egress-services"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=_get_svc_cidr(),
                destination_type="SERVICE_CIDR_BLOCK",
                description="Workers pull images from OCIR and send metrics and logs to OCI services",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-egress-pod-all"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=self.pod_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                description="Workers reach pod VNICs for OCI CNI VNIC-native networking",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-egress-worker-all"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=self.worker_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                description="Node-to-node traffic for OCI CNI pod communication across availability domains",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-egress-inet-443"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=INTERNET,
                destination_type="CIDR_BLOCK",
                tcp_options=_nsg_tcp_port(443),
                description="Workers pull container images and call external APIs via HTTPS",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("worker-nsg-egress-inet-80"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=INTERNET,
                destination_type="CIDR_BLOCK",
                tcp_options=_nsg_tcp_port(80),
                description="Workers pull images from HTTP registries and access OCI pre-authenticated URLs",
                opts=opts,
            )
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
        rules = self._pod_nsg_rules

        # ── INGRESS ────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-ingress-api-all"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=ALL,
                source=self.api_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                description="Control plane reaches pods on arbitrary ports for webhooks, exec, and metrics scraping",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-ingress-worker-all"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=ALL,
                source=self.worker_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                description="Worker nodes reach pod VNICs for OCI CNI VNIC-native networking",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-ingress-pod-all"),  # type: ignore[attr-defined]
                nsg,
                direction="INGRESS",
                protocol=ALL,
                source=self.pod_nsg.id,
                source_type="NETWORK_SECURITY_GROUP",
                description="Pod-to-pod communication (east-west traffic between workloads)",
                opts=opts,
            )
        )

        # ── EGRESS ─────────────────────────────────────────────────────
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-egress-pod-all"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=self.pod_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                description="Pod-to-pod communication (east-west traffic between workloads)",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-egress-worker-all"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=self.worker_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                description="Pods reach worker VNICs for OCI CNI VNIC-native networking",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-egress-api-6443"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=self.api_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(6443),
                description="Pods reach Kubernetes API server for service discovery and RBAC",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-egress-api-12250"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=self.api_nsg.id,
                destination_type="NETWORK_SECURITY_GROUP",
                tcp_options=_nsg_tcp_port(12250),
                description="Pods reach control-plane internal port",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-egress-services"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=ALL,
                destination=_get_svc_cidr(),
                destination_type="SERVICE_CIDR_BLOCK",
                description="Pods reach OCI services for object storage, monitoring, and logging",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-egress-inet-443"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=INTERNET,
                destination_type="CIDR_BLOCK",
                tcp_options=_nsg_tcp_port(443),
                description="Pods call external APIs and download dependencies via HTTPS",
                opts=opts,
            )
        )
        rules.append(
            self._r(
                self.create_resource_name("pod-nsg-egress-inet-80"),  # type: ignore[attr-defined]
                nsg,
                direction="EGRESS",
                protocol=TCP,
                destination=INTERNET,
                destination_type="CIDR_BLOCK",
                tcp_options=_nsg_tcp_port(80),
                description="Pods access HTTP endpoints and OCI pre-authenticated URLs",
                opts=opts,
            )
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
        prefix = self.name.replace("-", "_")  # type: ignore[attr-defined]
        pulumi.export(f"{prefix}_cluster_id", self.id)
        pulumi.export(f"{prefix}_cluster_endpoint", self.cluster.endpoints.public_endpoint)
        pulumi.export(f"{prefix}_kubernetes_version", self.kubernetes_version)
        pulumi.export(f"{prefix}_lb_nsg_id", self.lb_nsg.id)

        # Kubeconfig requires a real cluster OCID — skip during preview.
        if not pulumi.runtime.is_dry_run():
            kubeconfig = oci.containerengine.get_cluster_kube_config_output(cluster_id=self.cluster.id).content
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

        Uses `oci.containerengine.get_cluster_kube_config_output` (async) to
        fetch kubeconfig content and schedules a `pathlib.Path.write_text`
        call inside the resulting Output's `.apply`. The OCI API call and file
        write execute only during `pulumi up`, after the cluster OCID is known.
        Calling this during `pulumi preview` is safe but has no effect — the
        file is not written until a real deployment completes. The file is
        created or overwritten if it already exists.

        Args:
            filename: Absolute or relative path where the kubeconfig file
                should be written (e.g. `"/tmp/kubeconfig"`).

        Raises:
            OSError: If `filename` cannot be created or written to (e.g.
                the parent directory does not exist or the process lacks
                write permission).
            oci.exceptions.ServiceError: If the OCI Container Engine API
                call fails (e.g. the cluster is deleted, permissions are
                missing, or the region is unreachable).

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

        # Use the async `_output` form so the call is represented as a
        # pulumi.Output that composes cleanly with `.apply`.  No TODO needed —
        # .content is a plain pulumi.Output[str], so the apply receives a str.
        kube_config_output = oci.containerengine.get_cluster_kube_config_output(cluster_id=self.cluster.id)

        def _write(content: str) -> None:
            Path(filename).write_text(content)

        kube_config_output.content.apply(_write)  # type: ignore[union-attr]  # content is Optional[str] in stubs but never None for a live cluster


class OkeCluster(_OkeClusterMixin, BaseResource, AbstractKubernetes):
    """OKE `BASIC_CLUSTER` with node pools, security configuration, and NSGs.

    Creates a standard Oracle Kubernetes Engine cluster (`type="BASIC_CLUSTER"`)
    with OCI VCN-native pod networking (`OCI_VCN_IP_NATIVE` CNI) and each node
    pool spread across all availability domains in the region. Use
    `OkeClusterEnhanced` when you need OCI Workload Identity, cluster add-on
    lifecycle management, or OCI DevOps integration.

    Workers and pods share the private subnet CIDR. Four NSGs provide
    VNIC-level segmentation:

    - `api_nsg` controls who may reach the Kubernetes API endpoint.
    - `lb_nsg` is intended for OCI Load Balancers (attach via service
      annotation `oci.oraclecloud.com/security-group-ids`).
    - `worker_nsg` is assigned to every worker node VNIC.
    - `pod_nsg` is assigned to every pod VNIC (OCI CNI VCN-native).

    Public API:

    - `export()` — publish cluster stack outputs.
    - `create_kubeconfig(filename)` — write a kubectl-compatible
      kubeconfig YAML file during `pulumi up`.
    - `get_public_security_list_ids()` — OCIDs of public security lists
      populated with OKE rules.
    - `get_private_security_list_ids()` — OCIDs of private security lists
      populated with OKE rules.

    Attributes:
        vcn: The `Vcn` or `VcnRef` this cluster is deployed into.
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

    _CLUSTER_TYPE: str = "BASIC_CLUSTER"

    vcn: Vcn | VcnRef
    kubernetes_version: pulumi.Input[str]
    kubectl_allowed_cidrs: list[str]
    api_nsg: oci.core.NetworkSecurityGroup
    lb_nsg: oci.core.NetworkSecurityGroup
    worker_nsg: oci.core.NetworkSecurityGroup
    pod_nsg: oci.core.NetworkSecurityGroup
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
        kubectl_allowed_cidrs: list[str] | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a complete BASIC OKE cluster infrastructure.

        Adds all required OKE security rules to the VCN, finalises the network,
        creates four NSGs (api, lb, worker, pod) with NSG-to-NSG rules, and
        then creates the Kubernetes control plane and node pools.

        Args:
            name: Logical name for the cluster resource (e.g. `"k8s"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` that provides the public and private subnets.
            kubernetes_version: Kubernetes version string (e.g. `"v1.32.1"`).
            node_pools: List of `NodePoolConfig` descriptors.  Each entry
                creates a separate node pool on the cluster, enabling mixed
                shapes (e.g. a small system pool and a large app pool).
                Pass an empty list to create a cluster with no node pools
                (useful when pools are managed separately).
            stack_name: Pulumi stack name.  Defaults to `pulumi.get_stack()`
                when `None`.
            kubectl_allowed_cidrs: CIDRs permitted to reach the Kubernetes
                API endpoint on port 6443.  Pass `None` (default) to allow
                no external kubectl access; a `pulumi.warn()` is emitted to
                remind the caller to set this explicitly.  Pass `[]` to
                suppress the warning while still blocking all external access.
                Pass one or more CIDRs (e.g. `["203.0.113.0/24"]`) to allow
                kubectl from those addresses.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            RuntimeError: If `vcn.public_subnet` or `vcn.private_subnet` is
                `None` after `finalize_network()` completes.  This should not
                occur with a fully constructed `Vcn`; it can happen with a
                `VcnRef` that targets a stack that did not export the expected
                subnet resources.
        """
        super().__init__("custom:oke:Cluster", name, compartment_id, stack_name, opts)
        self._build_cluster(
            name=name,
            compartment_id=compartment_id,
            vcn=vcn,
            kubernetes_version=kubernetes_version,
            node_pools=node_pools,
            kubectl_allowed_cidrs=kubectl_allowed_cidrs,
        )


class OkeClusterEnhanced(_OkeClusterMixin, BaseResource, AbstractKubernetes):
    """OKE `ENHANCED_CLUSTER` with node pools, security configuration, and NSGs.

    Creates an Oracle Kubernetes Engine Enhanced cluster
    (`type="ENHANCED_CLUSTER"`) with OCI VCN-native pod networking
    (`OCI_VCN_IP_NATIVE` CNI) and each node pool spread across all availability
    domains in the region. Enhanced clusters support:

    - OCI Workload Identity — pods authenticate to OCI APIs without embedded
      credentials.
    - Cluster add-on lifecycle management — OCI manages add-on upgrades.
    - OCI DevOps integration.

    Use `OkeCluster` when you only need a standard (basic) cluster.

    Workers and pods share the private subnet CIDR. Four NSGs provide
    VNIC-level segmentation:

    - `api_nsg` controls who may reach the Kubernetes API endpoint.
    - `lb_nsg` is intended for OCI Load Balancers (attach via service
      annotation `oci.oraclecloud.com/security-group-ids`).
    - `worker_nsg` is assigned to every worker node VNIC.
    - `pod_nsg` is assigned to every pod VNIC (OCI CNI VCN-native).

    Public API:

    - `export()` — publish cluster stack outputs.
    - `create_kubeconfig(filename)` — write a kubectl-compatible
      kubeconfig YAML file during `pulumi up`.
    - `get_public_security_list_ids()` — OCIDs of public security lists
      populated with OKE rules.
    - `get_private_security_list_ids()` — OCIDs of private security lists
      populated with OKE rules.

    Attributes:
        vcn: The `Vcn` or `VcnRef` this cluster is deployed into.
        kubernetes_version: Kubernetes version string (e.g. `"v1.30.1"`).
        kubectl_allowed_cidrs: List of CIDRs permitted to reach the Kubernetes
            API endpoint on port 6443. An empty list means no external kubectl
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

        cluster = OkeClusterEnhanced(
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
        cluster.create_kubeconfig("/tmp/kubeconfig")
        ```
    """

    _CLUSTER_TYPE: str = "ENHANCED_CLUSTER"

    vcn: Vcn | VcnRef
    kubernetes_version: pulumi.Input[str]
    kubectl_allowed_cidrs: list[str]
    api_nsg: oci.core.NetworkSecurityGroup
    lb_nsg: oci.core.NetworkSecurityGroup
    worker_nsg: oci.core.NetworkSecurityGroup
    pod_nsg: oci.core.NetworkSecurityGroup
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
        kubectl_allowed_cidrs: list[str] | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a complete ENHANCED OKE cluster infrastructure.

        Adds all required OKE security rules to the VCN, finalises the network,
        creates four NSGs (api, lb, worker, pod) with NSG-to-NSG rules, and
        then creates the Kubernetes control plane and node pools.

        Args:
            name: Logical name for the cluster resource (e.g. `"k8s"`).
            compartment_id: OCID of the OCI compartment to deploy into.
            vcn: `Vcn` or `VcnRef` that provides the public and private subnets.
            kubernetes_version: Kubernetes version string (e.g. `"v1.32.1"`).
            node_pools: List of `NodePoolConfig` descriptors. Each entry
                creates a separate node pool on the cluster, enabling mixed
                shapes (e.g. a small system pool and a large app pool).
                Pass an empty list to create a cluster with no node pools
                (useful when pools are managed separately).
            stack_name: Pulumi stack name. Defaults to `pulumi.get_stack()`
                when `None`.
            kubectl_allowed_cidrs: CIDRs permitted to reach the Kubernetes
                API endpoint on port 6443. Pass `None` (default) to allow
                no external kubectl access; a `pulumi.warn()` is emitted to
                remind the caller to set this explicitly. Pass `[]` to
                suppress the warning while still blocking all external access.
                Pass one or more CIDRs (e.g. `["203.0.113.0/24"]`) to allow
                kubectl from those addresses.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            RuntimeError: If `vcn.public_subnet` or `vcn.private_subnet` is
                `None` after `finalize_network()` completes. This should not
                occur with a fully constructed `Vcn`; it can happen with a
                `VcnRef` that targets a stack that did not export the expected
                subnet resources.
        """
        super().__init__("custom:oke:ClusterEnhanced", name, compartment_id, stack_name, opts)
        self._build_cluster(
            name=name,
            compartment_id=compartment_id,
            vcn=vcn,
            kubernetes_version=kubernetes_version,
            node_pools=node_pools,
            kubectl_allowed_cidrs=kubectl_allowed_cidrs,
        )


__all__ = ["NodePoolConfig", "OkeCluster", "OkeClusterEnhanced"]
