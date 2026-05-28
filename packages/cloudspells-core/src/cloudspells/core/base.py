"""Base resource class for all CloudSpells spells.

All CloudSpells resource classes (`Vcn`, `OkeCluster`, `ComputeInstance`,
`ScalableWorkload`, etc.) inherit from `BaseResource`, which extends
`pulumi.ComponentResource` with:

- **Standardised naming** via `ResourceNamer` —
  all child resources follow the `{stack}-{name}-{suffix}` pattern.
- **Consistent tagging** via `ResourceTagger` —
  every resource receives `managed-by`, `spell-type`, `spell-name`,
  `environment`, `name`, and `resource-type` tags automatically.
  The `spell-type` is derived from the Pulumi resource type URN so
  callers never need to supply it explicitly.
- **SSH key management** — auto-generates RSA 4096-bit key pairs when no
  key is provided, and exports them as Pulumi secrets.
- **Convenience wrappers** that delegate to the namer and tagger so
  subclasses never import those helpers directly.
"""

__all__ = ["BaseResource"]

import re
from typing import Any

import pulumi
import pulumi.dynamic as pulumi_dynamic

from .helper import Helper
from .naming import ResourceNamer
from .tagging import ResourceTagger


def _spell_type_from_urn(resource_type: str) -> str:
    """Derive a kebab-case spell-type tag value from a Pulumi resource type URN.

    Extracts the class-name segment (last `:`-delimited part) and converts
    it from CamelCase to kebab-case.

    Args:
        resource_type: Pulumi resource type string in
            `"custom:namespace:ClassName"` format.

    Returns:
        Lowercase kebab-case string (e.g. `"vcn-flow-logs"`).

    Example:
        >>> _spell_type_from_urn("custom:network:VcnFlowLogs")
        'vcn-flow-logs'
        >>> _spell_type_from_urn("custom:oke:Cluster")
        'cluster'
    """
    class_name = resource_type.rsplit(":", 1)[-1]
    # Insert hyphen between a run of uppercase and an uppercase+lowercase pair,
    # then between a lowercase/digit and the next uppercase letter.
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", class_name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1-\2", s)
    return s.lower()


class _SshKeyPairProvider(pulumi_dynamic.ResourceProvider):
    """Pulumi dynamic provider that creates SSH keys only at resource create time."""

    def create(self, props: dict[str, Any]) -> pulumi_dynamic.CreateResult:
        """Generate an SSH key pair and return it as resource state.

        Args:
            props: Dynamic resource input properties.

        Returns:
            Pulumi dynamic create result containing the generated key pair.
        """
        public_key, private_key = Helper().generate_ssh_key_pair(
            str(props["stack_name"]),
            str(props["resource_name"]),
        )
        outs = {
            **props,
            "public_key": public_key,
            "private_key": private_key,
        }
        return pulumi_dynamic.CreateResult(
            id_=f"{props['stack_name']}:{props['resource_name']}",
            outs=outs,
        )

    def diff(self, _id: str, olds: dict[str, Any], news: dict[str, Any]) -> pulumi_dynamic.DiffResult:
        """Replace the generated key only when its identity inputs change.

        Args:
            _id: Existing dynamic resource ID.
            olds: Previous state properties.
            news: New desired properties.

        Returns:
            Pulumi diff result indicating whether replacement is required.
        """
        replaces = [field for field in ("stack_name", "resource_name") if str(olds.get(field)) != str(news.get(field))]
        return pulumi_dynamic.DiffResult(
            changes=bool(replaces),
            replaces=replaces,
            delete_before_replace=True,
        )


class _SshKeyPairResource(
    pulumi_dynamic.Resource,
    module="cloudspells",
    name="SshKeyPair",
):
    """Stateful generated SSH key pair stored in Pulumi state."""

    public_key: pulumi.Output[str]
    private_key: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        stack_name: str,
        resource_name: str,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a dynamic SSH key resource.

        Args:
            name: Pulumi child resource name.
            stack_name: Pulumi stack name included in the key comment.
            resource_name: Logical CloudSpells resource name included in the
                key comment.
            opts: Pulumi resource options.
        """
        super().__init__(
            _SshKeyPairProvider(),
            name,
            {
                "stack_name": stack_name,
                "resource_name": resource_name,
                "public_key": None,
                "private_key": None,
            },
            opts,
        )


class BaseResource(pulumi.ComponentResource):
    """Base class for all CloudSpells components.

    Extends `pulumi.ComponentResource` with standardised naming, tagging,
    and optional SSH key management.  All spells inherit from this class
    and call `super().__init__()` as their first step.

    Attributes:
        project_ref: Cloud-neutral provider project reference (OCI compartment
            OCID, AWS account ID, GCP project ID, etc.).
        compartment_id: OCI-specific alias for `project_ref`.  Kept for
            backward compatibility with all OCI spells.
        stack_name: Resolved Pulumi stack name used in all resource names and
            tags.
        name: Logical resource name supplied by the caller.
        display_name: Human-readable name in the form `"{stack_name}-{name}"`.
        namer: `ResourceNamer` instance for this resource.
        tagger: `ResourceTagger` instance for this resource.
        ssh_public_key: OpenSSH public key input installed on the instance.
            Set by `_setup_ssh_keys`; generated by a Pulumi stateful dynamic
            resource or caller-supplied.
        ssh_private_key: PEM-encoded private key output when generated,
            `None` when the caller supplied their own public key.  Always
            wrapped as a Pulumi secret before export.  Set by
            `_setup_ssh_keys`.
        auto_generated_keys: `True` when the SSH key pair was auto-generated
            by `_setup_ssh_keys`, `False` when the caller supplied a key.
    """

    project_ref: pulumi.Input[str] | None
    compartment_id: pulumi.Input[str] | None
    stack_name: str
    name: str
    display_name: str
    namer: ResourceNamer
    tagger: ResourceTagger
    ssh_public_key: pulumi.Input[str]
    ssh_private_key: pulumi.Output[str] | None
    auto_generated_keys: bool
    _ssh_key_pair: _SshKeyPairResource | None

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
                (e.g. `"custom:network:Vcn"`).
            name: Logical resource name (e.g. `"lab"`).  Combined with
                stack_name to form the Pulumi resource URN
                `"{stack_name}-{name}"`.
            compartment_id: OCID of the OCI compartment that will own the
                child resources created by this component.  For non-OCI
                providers pass `project_ref` instead.  When both are given,
                `compartment_id` takes precedence.  May be `None` when the
                spell does not require a project reference.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`; override in tests to
                avoid a live Pulumi context.
            opts: Standard Pulumi resource options forwarded to the component
                base class (e.g. `protect`, `depends_on`).
            project_ref: Cloud-neutral alias for `compartment_id` for
                non-OCI providers (AWS account ID, GCP project ID, etc.).
                Ignored when `compartment_id` is also provided.  May be
                `None` when the spell does not require a project reference.
        """
        resolved_stack = stack_name if stack_name is not None else pulumi.get_stack()
        super().__init__(resource_type, f"{resolved_stack}-{name}", {}, opts)

        # Resolve the provider-specific project reference from either alias.
        # compartment_id is kept for backward compatibility with all OCI spells.
        resolved_ref = compartment_id if compartment_id is not None else project_ref
        self.project_ref = resolved_ref
        self.compartment_id = resolved_ref
        self.stack_name = resolved_stack
        self.name = name
        self.display_name = f"{resolved_stack}-{name}"

        # Initialize helper classes
        self.namer = ResourceNamer(resolved_stack, name)
        self.tagger = ResourceTagger(resolved_stack, name, _spell_type_from_urn(resource_type))

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------

    def create_resource_name(self, suffix: str) -> str:
        """Return a standardised child resource name.

        Delegates to `ResourceNamer.create_resource_name`.

        Args:
            suffix: Short type suffix (e.g. `"vcn"`, `"igw"`,
                `"sn-public"`).

        Returns:
            `"{stack_name}-{resource_name}-{suffix}"` string.
        """
        return self.namer.create_resource_name(suffix)

    def create_dns_label(self, prefix: str) -> str:
        """Return a DNS-safe label for OCI networking resources.

        Delegates to `ResourceNamer.create_dns_label`.

        Args:
            prefix: Short alphanumeric prefix (e.g. `"pub"`, `"vcn"`).
                Keep both prefix and stack_name short so the combined
                label stays within OCI's 15-character alphanumeric limit.

        Returns:
            `"{prefix}{stack_name}"` string (e.g. `"vcnprod"`).
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

        Delegates to `ResourceTagger.create_freeform_tags`.

        Args:
            resource_name: Display name used as the `Name` tag value.
            resource_type: Resource category (e.g. `"vcn"`, `"subnet"`).
            additional_tags: Optional extra tags to merge into the result.

        Returns:
            Flat `dict[str, str]` with the six baseline CloudSpells tags
            (`managed-by`, `spell-type`, `spell-name`, `environment`,
            `name`, `resource-type`) plus any entries from
            `additional_tags`.  Valid as `freeform_tags=` (OCI),
            `tags=` (AWS/Azure), or `labels=` (GCP).
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

        Delegates to `ResourceTagger.create_network_resource_tags`.

        Args:
            resource_name: Display name used as the `Name` tag value.
            resource_type: Resource category (e.g. `"subnet"`).
            network_type: Subnet tier — one of `"public"`, `"private"`,
                `"secure"`, or `"management"`.
            subnet_group: Optional sub-group label (e.g. `"public-a"`).
            additional_tags: Optional extra tags to merge.

        Returns:
            `dict[str, str]` including `network-type` (and optionally
            `subnet-group`) keys alongside the baseline tags.
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

        Delegates to `ResourceTagger.create_gateway_tags`.

        Args:
            resource_name: Display name used as the `Name` tag value.
            gateway_type: Gateway category (e.g. `"internet"`, `"nat"`,
                `"service"`).
            additional_tags: Optional extra tags to merge.

        Returns:
            `dict[str, str]` including the `gateway-type` key alongside
            the baseline tags.
        """
        return self.tagger.create_gateway_tags(resource_name, gateway_type, additional_tags)

    # ------------------------------------------------------------------
    # SSH key management
    # ------------------------------------------------------------------

    def _setup_ssh_keys(self, ssh_public_key: pulumi.Input[str] | None) -> None:
        """Configure the SSH key pair for this resource.

        If ssh_public_key is `None` or an empty string, a Pulumi dynamic
        resource is created to generate and persist a new RSA 4096-bit key
        pair in state.  This keeps previews and updates deterministic because
        key generation happens at dynamic resource create time, not during
        every Python program evaluation.  Otherwise the provided public key is
        used as-is and no private key is stored by CloudSpells.

        Sets the following instance attributes:

        - `self.ssh_public_key` — public key input.
        - `self.ssh_private_key` — private key output, or `None`.
        - `self.auto_generated_keys` — `True` when keys were generated
          automatically.

        Args:
            ssh_public_key: An existing OpenSSH public key input, or `None` to
                trigger automatic key generation.
        """
        if ssh_public_key is None or (isinstance(ssh_public_key, str) and ssh_public_key.strip() == ""):
            key_pair = _SshKeyPairResource(
                self.create_resource_name("ssh-key"),
                self.stack_name,
                self.name,
                pulumi.ResourceOptions(
                    parent=self,
                    additional_secret_outputs=["private_key"],
                ),
            )
            self._ssh_key_pair = key_pair
            self.ssh_public_key = key_pair.public_key
            self.ssh_private_key = key_pair.private_key
            self.auto_generated_keys = True
        else:
            self._ssh_key_pair = None
            self.ssh_public_key = ssh_public_key
            self.ssh_private_key = None
            self.auto_generated_keys = False

    def _get_ssh_outputs(self) -> dict[str, pulumi.Output[str]]:
        """Collect Pulumi stack outputs for auto-generated SSH key material.

        Returns a mapping with `ssh_public_key` and `ssh_private_key`
        wrapped as Pulumi secrets, but only when keys were auto-generated
        (i.e. `auto_generated_keys` is `True`).  The outputs are
        suitable for passing directly to `self.register_outputs()`.

        Returns:
            Mapping of output name to `pulumi.Output[str]` secret value.
            Returns an empty dict when SSH keys were supplied by the caller.
        """
        outputs: dict[str, pulumi.Output[str]] = {}
        if self.auto_generated_keys:
            outputs["ssh_public_key"] = pulumi.Output.secret(self.ssh_public_key)
            if self.ssh_private_key:
                outputs["ssh_private_key"] = pulumi.Output.secret(self.ssh_private_key)
        return outputs

    def get_ssh_public_key(self) -> pulumi.Input[str]:
        """Return the SSH public key associated with this resource.

        Available on any spell that invokes `_setup_ssh_keys` during
        construction (e.g. `ComputeInstance`, `ScalableWorkload`).

        Returns:
            OpenSSH public key input (auto-generated or caller-supplied).
        """
        return self.ssh_public_key

    def get_ssh_private_key(self) -> pulumi.Output[str] | None:
        """Return the SSH private key if it was auto-generated.

        Available on any spell that invokes `_setup_ssh_keys` during
        construction (e.g. `ComputeInstance`, `ScalableWorkload`).

        Returns:
            PEM-encoded private key output when keys were auto-generated,
            or `None` when the caller supplied their own public key.
        """
        return self.ssh_private_key

    # ------------------------------------------------------------------
    # Resource introspection
    # ------------------------------------------------------------------

    def get_resource(self, resource_name: str) -> Any | None:
        """Get a child resource by attribute name.

        A generic accessor for any attribute on the component.  Following
        Pulumi best practices for component resource introspection.

        Args:
            resource_name: Attribute name of the child resource
                (e.g. `"public_subnet"`, `"nat_gateway"`).

        Returns:
            The requested resource object, or `None` if the attribute does
            not exist.

        Example:
            ```python
            from cloudspells.providers.oci import Vcn

            vcn = Vcn(name="my-vcn", compartment_id="ocid1.compartment...",
                      stack_name="prod")
            vcn.finalize_network()
            public_subnet = vcn.get_resource("public_subnet")
            nat_gateway   = vcn.get_resource("nat_gateway")
            ```
        """
        return getattr(self, resource_name, None)
