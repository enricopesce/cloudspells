"""Base resource class for all OCIBlocks building blocks.

All OCIBlocks resource classes (:class:`~blocks.vcn.network.Vcn`,
:class:`~blocks.oke.cluster.OkeCluster`,
:class:`~blocks.compute.instance.ComputeInstance`,
:class:`~blocks.autoscale.workload.ScalableWorkload`, …) inherit from
:class:`BaseResource`, which extends ``pulumi.ComponentResource`` with:

* **Standardised naming** via :class:`~core.naming.ResourceNamer` –
  all child resources follow the ``{stack}-{name}-{suffix}`` pattern.
* **Consistent tagging** via :class:`~core.tagging.ResourceTagger` –
  every resource receives ``Name``, ``ResourceType``, ``Environment``,
  and ``CreatedBy`` tags automatically.
* **SSH key management** – auto-generates RSA 4096-bit key pairs when no
  key is provided, and exports them as Pulumi secrets.
* **Convenience wrappers** that delegate to the namer and tagger so
  subclasses never import those helpers directly.
"""

import pulumi
from typing import Any, Optional
from .naming import ResourceNamer
from .tagging import ResourceTagger
from .helper import Helper


class BaseResource(pulumi.ComponentResource):
    """Base class for all OCIBlocks components.

    Extends ``pulumi.ComponentResource`` with standardised naming, tagging,
    and optional SSH key management.  All building blocks inherit from this
    class and call ``super().__init__()`` as their first step.

    Attributes:
        project_ref: Cloud-neutral provider project reference (OCI compartment
            OCID, AWS account ID, GCP project ID, etc.).
        compartment_id: OCI-specific alias for :attr:`project_ref`.  Kept for
            backward compatibility with all OCI blocks.
        stack_name: Resolved Pulumi stack name used in all resource names and
            tags.
        name: Logical resource name supplied by the caller.
        display_name: Human-readable name in the form ``"{stack_name}-{name}"``.
        namer: :class:`~core.naming.ResourceNamer` instance for this resource.
        tagger: :class:`~core.tagging.ResourceTagger` instance for this
            resource.
    """

    project_ref: pulumi.Input[str] | None
    compartment_id: pulumi.Input[str] | None
    stack_name: str
    name: str
    display_name: str
    namer: ResourceNamer
    tagger: ResourceTagger

    def __init__(
        self,
        resource_type: str,
        name: str,
        compartment_id: pulumi.Input[str] | None = None,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
        *,
        project_ref: pulumi.Input[str] | None = None,
    ) -> None:
        """Initialise a named, tagged Pulumi component resource.

        Args:
            resource_type: Pulumi resource type URN string
                (e.g. ``"custom:network:Vcn"``).
            name: Logical resource name (e.g. ``"lab"``).  Combined with
                *stack_name* to form the Pulumi resource URN
                ``"{stack_name}-{name}"``.
            compartment_id: OCID of the OCI compartment that will own the
                child resources created by this component.  For non-OCI
                providers use *project_ref* instead.  At least one of
                *compartment_id* or *project_ref* must be provided.
            stack_name: Pulumi stack name.  Defaults to
                ``pulumi.get_stack()`` when ``None``; override in tests to
                avoid a live Pulumi context.
            opts: Standard Pulumi resource options forwarded to the component
                base class (e.g. ``protect``, ``depends_on``).
            project_ref: Cloud-neutral alias for *compartment_id*.  When both
                are provided *compartment_id* takes precedence.  Use this
                parameter for non-OCI providers (AWS account ID, GCP project
                ID, etc.) to keep :class:`BaseResource` cloud-neutral.
        """
        resolved_stack = stack_name if stack_name is not None else pulumi.get_stack()
        super().__init__(resource_type, f"{resolved_stack}-{name}", {}, opts)

        # Resolve the provider-specific project reference from either alias.
        # compartment_id is kept for backward compatibility with all OCI blocks.
        resolved_ref = compartment_id if compartment_id is not None else project_ref
        self.project_ref = resolved_ref
        self.compartment_id = resolved_ref
        self.stack_name = resolved_stack
        self.name = name
        self.display_name = f"{resolved_stack}-{name}"

        # Initialize helper classes
        self.namer = ResourceNamer(resolved_stack, name)
        self.tagger = ResourceTagger(resolved_stack, name)

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------

    def create_resource_name(self, suffix: str) -> str:
        """Return a standardised child resource name.

        Delegates to :class:`~core.naming.ResourceNamer.create_resource_name`.

        Args:
            suffix: Short type suffix (e.g. ``"vcn"``, ``"igw"``,
                ``"sn-public"``).

        Returns:
            ``"{stack_name}-{resource_name}-{suffix}"`` string.
        """
        return self.namer.create_resource_name(suffix)

    def create_dns_label(self, prefix: str) -> str:
        """Return a DNS-safe label for OCI networking resources.

        Delegates to :class:`~core.naming.ResourceNamer.create_dns_label`.

        Args:
            prefix: Short alphanumeric prefix (e.g. ``"pub"``, ``"vcn"``).

        Returns:
            Concatenation of *prefix* and the stack name.
        """
        return self.namer.create_dns_label(prefix)

    # ------------------------------------------------------------------
    # Tagging helpers
    # ------------------------------------------------------------------

    def create_freeform_tags(
        self,
        resource_name: str,
        resource_type: str,
        additional_tags: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Return standard freeform tags for a child resource.

        Delegates to
        :meth:`~core.tagging.ResourceTagger.create_freeform_tags`.

        Args:
            resource_name: Display name used as the ``Name`` tag value.
            resource_type: Resource category (e.g. ``"vcn"``, ``"subnet"``).
            additional_tags: Optional extra tags to merge into the result.

        Returns:
            ``dict[str, str]`` of OCI freeform tags.
        """
        return self.tagger.create_freeform_tags(resource_name, resource_type, additional_tags)

    def create_network_resource_tags(
        self,
        resource_name: str,
        resource_type: str,
        network_type: str,
        subnet_group: str | None = None,
        additional_tags: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Return freeform tags enriched with networking metadata.

        Delegates to
        :meth:`~core.tagging.ResourceTagger.create_network_resource_tags`.

        Args:
            resource_name: Display name used as the ``Name`` tag value.
            resource_type: Resource category (e.g. ``"subnet"``).
            network_type: ``"public"`` or ``"private"``.
            subnet_group: Optional sub-group label (e.g. ``"public-a"``).
            additional_tags: Optional extra tags to merge.

        Returns:
            ``dict[str, str]`` including ``NetworkType`` (and optionally
            ``SubnetGroup``) keys alongside the baseline tags.
        """
        return self.tagger.create_network_resource_tags(
            resource_name,
            resource_type,
            network_type,
            subnet_group,
            additional_tags,
        )

    def create_gateway_tags(
        self,
        resource_name: str,
        gateway_type: str,
        additional_tags: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Return freeform tags for a gateway resource.

        Delegates to
        :meth:`~core.tagging.ResourceTagger.create_gateway_tags`.

        Args:
            resource_name: Display name used as the ``Name`` tag value.
            gateway_type: Gateway category (e.g. ``"internet"``, ``"nat"``,
                ``"service"``).
            additional_tags: Optional extra tags to merge.

        Returns:
            ``dict[str, str]`` including the ``GatewayType`` key alongside
            the baseline tags.
        """
        return self.tagger.create_gateway_tags(resource_name, gateway_type, additional_tags)

    # ------------------------------------------------------------------
    # SSH key management
    # ------------------------------------------------------------------

    def _setup_ssh_keys(self, ssh_public_key: pulumi.Input[str] | None) -> None:
        """Configure the SSH key pair for this resource.

        If *ssh_public_key* is ``None`` or an empty string, a new RSA
        4096-bit key pair is generated with
        :meth:`~core.helper.Helper.generate_ssh_key_pair` and the result is
        stored on ``self``.  Otherwise the provided public key is used as-is
        and no private key is stored.

        Sets the following instance attributes:

        * ``self.ssh_public_key``    – public key string.
        * ``self.ssh_private_key``   – private key string, or ``None``.
        * ``self.auto_generated_keys`` – ``True`` when keys were generated
          automatically.

        Args:
            ssh_public_key: An existing OpenSSH public key string, or
                ``None`` to trigger automatic key generation.
        """
        if ssh_public_key is None or (isinstance(ssh_public_key, str) and ssh_public_key.strip() == ""):
            public_key, private_key = Helper().generate_ssh_key_pair(self.stack_name, self.name)
            self.ssh_public_key = public_key
            self.ssh_private_key = private_key
            self.auto_generated_keys = True
        else:
            self.ssh_public_key = str(ssh_public_key)
            self.ssh_private_key = None
            self.auto_generated_keys = False

    def _get_ssh_outputs(self) -> dict[str, pulumi.Output[str]]:
        """Collect Pulumi stack outputs for auto-generated SSH key material.

        Returns a mapping with ``ssh_public_key`` and ``ssh_private_key``
        wrapped as Pulumi secrets, but *only* when keys were auto-generated
        (i.e. :attr:`auto_generated_keys` is ``True``).  The outputs are
        suitable for passing directly to ``self.register_outputs()``.

        Returns:
            Mapping of output name to ``pulumi.Output[str]`` secret value.
            Returns an empty dict when SSH keys were supplied by the caller.
        """
        outputs: dict[str, pulumi.Output[str]] = {}
        if self.auto_generated_keys:
            outputs["ssh_public_key"] = pulumi.Output.secret(self.ssh_public_key)
            if self.ssh_private_key:
                outputs["ssh_private_key"] = pulumi.Output.secret(self.ssh_private_key)
        return outputs

    # ------------------------------------------------------------------
    # Resource introspection
    # ------------------------------------------------------------------

    def get_resource(self, resource_name: str) -> Any | None:
        """Get a child resource by attribute name.

        A generic accessor for any attribute on the component.  Following
        Pulumi best practices for component resource introspection.

        Args:
            resource_name: Attribute name of the child resource
                (e.g. ``"public_subnet"``, ``"nat_gateway"``).

        Returns:
            The requested resource object, or ``None`` if the attribute does
            not exist.

        Example:
            >>> vcn = Vcn(name="my-vcn", compartment_id="...", stack_name="prod")
            >>> vcn.finalize_network()
            >>> public_subnet = vcn.get_resource("public_subnet")
            >>> nat_gateway   = vcn.get_resource("nat_gateway")
        """
        return getattr(self, resource_name, None)
