"""Object Storage spells for CloudSpells.

Provides purpose-built OCI Object Storage bucket spells for four common use
cases, plus a general-purpose baseline:

- `ObjectStorageBucket`: General-purpose private bucket with secure defaults.
- `BackupBucket`: Versioned bucket with automatic retention-based expiry.
- `DataLakeBucket`: Tiered lifecycle bucket — hot → archive → delete.
- `ArchiveBucket`: Immutable compliance bucket (Archive tier + retention rule).
- `StaticWebsiteBucket`: Publicly readable bucket for static website hosting.

All buckets follow CloudSpells naming (`{stack}-{name}-bucket`) and tagging
conventions.  The OCI tenancy namespace is a tenancy-scoped string that must
be supplied by the caller — it cannot be auto-discovered at deploy time without
violating the CS-002 determinism rule.

Exports:
    ObjectStorageBucket: General-purpose private bucket.
    BackupBucket: Versioned backup bucket with lifecycle deletion.
    DataLakeBucket: Tiered lifecycle bucket for analytics workloads.
    ArchiveBucket: Archive-tier bucket with a retention rule for long-term
        compliance. Note: the retention rule is not locked at creation time;
        administrators can still modify it via the OCI Console or API.
    StaticWebsiteBucket: Public read bucket for static website delivery.
"""

from __future__ import annotations

import pulumi
import pulumi_oci as oci
from cloudspells.core.base import BaseResource

_MULTIPART_EXPIRY_DAYS: int = 7


class _BucketMixin:
    """Private mixin providing shared accessor and export logic for all bucket spells.

    Extracted to satisfy CS-011 (DRY via private mixin): `get_bucket_name` and
    `export` are identical across all five bucket classes.  This mixin is not
    exported and must not appear in `__all__`.

    Requires that the concrete class sets `self.bucket` (an
    `oci.objectstorage.Bucket`) and `self.name` (the logical resource name)
    before any mixin method is called — both are guaranteed by `BaseResource`.
    """

    def get_bucket_name(self) -> pulumi.Output[str]:
        """Return the OCI bucket name.

        Returns:
            `pulumi.Output[str]` resolving to the physical OCI bucket name.
        """
        return self.bucket.name  # type: ignore[attr-defined]  # bucket set by concrete class __init__

    def export(self) -> None:
        """Export the bucket name as a Pulumi stack output.

        Publishes `{name}_bucket_name` so other stacks and tooling can
        reference the physical OCI bucket name without hard-coding it.

        Example:
            ```python
            bucket = ObjectStorageBucket(
                name="artifacts", compartment_id=comp_id, namespace="mytenancy"
            )
            bucket.export()
            # Stack output: artifacts_bucket_name = <stack>-artifacts-bucket
            ```
        """
        prefix = self.name.replace("-", "_")  # type: ignore[attr-defined]  # name set by BaseResource
        pulumi.export(f"{prefix}_bucket_name", self.get_bucket_name())


def _abort_multipart_rule() -> oci.objectstorage.ObjectLifecyclePolicyRuleArgs:
    """Return a lifecycle rule that aborts stale multipart uploads after 7 days.

    Prevents unbounded storage accumulation from failed large-object writes.

    Returns:
        An `oci.objectstorage.ObjectLifecyclePolicyRuleArgs` with `action="ABORT"`,
        targeting `"multipart-uploads"` and expiring after `_MULTIPART_EXPIRY_DAYS`
        days.
    """
    return oci.objectstorage.ObjectLifecyclePolicyRuleArgs(
        action="ABORT",
        is_enabled=True,
        name="abort-stale-multipart-uploads",
        time_amount=str(_MULTIPART_EXPIRY_DAYS),
        time_unit="DAYS",
        target="multipart-uploads",
    )


class ObjectStorageBucket(_BucketMixin, BaseResource):
    """OCI Object Storage bucket with private access and standard storage tier.

    Creates a single `oci.objectstorage.Bucket` scoped to the supplied
    compartment and tenancy namespace.  Access is locked to
    `NoPublicAccess` and the storage tier is fixed at `Standard` — both
    are opinionated defaults that callers cannot override.

    The bucket name is derived via `ResourceNamer` and follows the
    `{stack}-{name}-bucket` pattern, ensuring it is unique within the
    tenancy namespace and consistent with all other CloudSpells resource
    names.

    Resources created:

    - One `oci.objectstorage.Bucket` with `NoPublicAccess` and `Standard`
      storage tier.

    Attributes:
        bucket: The underlying `oci.objectstorage.Bucket` resource.
        bucket_name: `pulumi.Output[str]` resolving to the OCI bucket name.

    Example:
        ```python
        bucket = ObjectStorageBucket(
            name="artifacts",
            compartment_id=comp_id,
            namespace="mytenancy",
        )
        pulumi.export("bucket_name", bucket.bucket_name)
        ```
    """

    bucket: oci.objectstorage.Bucket
    bucket_name: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        namespace: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a private OCI Object Storage bucket.

        Args:
            name: Logical name for the bucket (e.g. `"artifacts"`).
                Combined with the stack name to form the physical bucket
                name `"{stack}-{name}-bucket"`.
            compartment_id: OCID of the OCI compartment to deploy into.
            namespace: OCI tenancy-level Object Storage namespace.  This
                is a fixed string assigned to your tenancy (visible in
                the OCI Console under Tenancy Details).  It cannot be
                resolved automatically at deploy time without violating
                the CS-002 determinism rule, so it must be supplied
                explicitly.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.  Override in tests
                only; production stacks should omit this parameter.
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:storage:ObjectStorageBucket", name, compartment_id, stack_name, opts)

        # The Pulumi logical name (first arg) and the OCI bucket `name=` are
        # intentionally set to the same value so the Pulumi URN and the OCI
        # resource name remain in sync.
        bucket_name = self.create_resource_name("bucket")
        self.bucket = oci.objectstorage.Bucket(
            bucket_name,
            compartment_id=self.compartment_id,
            namespace=namespace,
            name=bucket_name,
            access_type="NoPublicAccess",
            storage_tier="Standard",
            versioning="Disabled",
            freeform_tags=self.create_freeform_tags(bucket_name, "bucket"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.bucket_name = self.bucket.name

        self.register_outputs({
            "bucket_name": self.bucket.name,
        })


class BackupBucket(_BucketMixin, BaseResource):
    """OCI Object Storage bucket configured for backup and disaster recovery.

    Creates a `Standard`-tier bucket with object versioning enabled and a
    lifecycle policy that permanently deletes objects older than
    `retention_days` days.  Access is locked to `NoPublicAccess`.

    Versioning protects against accidental deletion and data corruption —
    a prior object version is always recoverable within the retention window.

    Resources created:

    - One `oci.objectstorage.Bucket` with `NoPublicAccess`, `Standard`
      storage tier, and versioning enabled.
    - One `oci.objectstorage.ObjectLifecyclePolicy` with two rules: delete
      all objects after `retention_days` days, and abort incomplete
      multipart uploads after 7 days.

    Attributes:
        bucket: The underlying `oci.objectstorage.Bucket` resource.
        lifecycle_policy: The `oci.objectstorage.ObjectLifecyclePolicy`
            that enforces retention-based deletion.
        bucket_name: `pulumi.Output[str]` resolving to the OCI bucket name.

    Example:
        ```python
        backup = BackupBucket(
            name="db-backups",
            compartment_id=comp_id,
            namespace="mytenancy",
            retention_days=30,
        )
        pulumi.export("backup_bucket", backup.bucket_name)
        ```
    """

    bucket: oci.objectstorage.Bucket
    lifecycle_policy: oci.objectstorage.ObjectLifecyclePolicy
    bucket_name: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        namespace: pulumi.Input[str],
        retention_days: int = 90,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a versioned backup bucket with automatic object expiry.

        Args:
            name: Logical name (e.g. `"db-backups"`).  Combined with the
                stack name to form `"{stack}-{name}-bucket"`.
            compartment_id: OCID of the OCI compartment to deploy into.
            namespace: OCI tenancy-level Object Storage namespace.
            retention_days: Days after object creation before permanent
                deletion.  Must be greater than `0`.  Defaults to `90`.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.  Override in tests
                only; production stacks should omit this parameter.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `retention_days` is not greater than `0`.
        """
        if retention_days <= 0:
            raise ValueError(f"retention_days ({retention_days}) must be greater than 0")

        super().__init__("custom:storage:BackupBucket", name, compartment_id, stack_name, opts)

        # The Pulumi logical name (first arg) and the OCI bucket `name=` are
        # intentionally set to the same value so the Pulumi URN and the OCI
        # resource name remain in sync.
        bucket_name = self.create_resource_name("bucket")
        self.bucket = oci.objectstorage.Bucket(
            bucket_name,
            compartment_id=self.compartment_id,
            namespace=namespace,
            name=bucket_name,
            access_type="NoPublicAccess",
            storage_tier="Standard",
            versioning="Enabled",
            freeform_tags=self.create_freeform_tags(bucket_name, "bucket"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.lifecycle_policy = oci.objectstorage.ObjectLifecyclePolicy(
            self.create_resource_name("lifecycle"),
            namespace=namespace,
            bucket=self.bucket.name,
            rules=[
                oci.objectstorage.ObjectLifecyclePolicyRuleArgs(
                    action="DELETE",
                    is_enabled=True,
                    name="delete-after-retention",
                    # The pulumi-oci SDK models timeAmount as pulumi.Input[str]
                    # (mirroring the Terraform provider's string type), so the
                    # integer day count must be coerced to str here.
                    time_amount=str(retention_days),
                    time_unit="DAYS",
                    target="objects",
                ),
                _abort_multipart_rule(),
            ],
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.bucket_name = self.bucket.name
        self.register_outputs({"bucket_name": self.bucket.name})


class DataLakeBucket(_BucketMixin, BaseResource):
    """OCI Object Storage bucket configured for data lake and analytics workloads.

    Creates a `Standard`-tier bucket with a two-stage lifecycle policy:
    objects are moved to `Archive` tier after `hot_days` days, then
    permanently deleted after `delete_days` days (both measured from object
    creation).  Access is locked to `NoPublicAccess`.

    Versioning is disabled to control costs at the high write volumes typical
    of analytics pipelines.

    Resources created:

    - One `oci.objectstorage.Bucket` with `NoPublicAccess` and `Standard`
      storage tier.
    - One `oci.objectstorage.ObjectLifecyclePolicy` with three rules:
      archive after `hot_days` days, delete after `delete_days` days, and
      abort incomplete multipart uploads after 7 days.

    Attributes:
        bucket: The underlying `oci.objectstorage.Bucket` resource.
        lifecycle_policy: The `oci.objectstorage.ObjectLifecyclePolicy`
            that governs hot-to-archive-to-delete transitions.
        bucket_name: `pulumi.Output[str]` resolving to the OCI bucket name.

    Example:
        ```python
        lake = DataLakeBucket(
            name="events",
            compartment_id=comp_id,
            namespace="mytenancy",
            hot_days=90,
            delete_days=730,
        )
        pulumi.export("lake_bucket", lake.bucket_name)
        ```
    """

    bucket: oci.objectstorage.Bucket
    lifecycle_policy: oci.objectstorage.ObjectLifecyclePolicy
    bucket_name: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        namespace: pulumi.Input[str],
        hot_days: int = 90,
        delete_days: int = 365,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a tiered lifecycle data lake bucket.

        Args:
            name: Logical name (e.g. `"events"`).  Combined with the stack
                name to form `"{stack}-{name}-bucket"`.
            compartment_id: OCID of the OCI compartment to deploy into.
            namespace: OCI tenancy-level Object Storage namespace.
            hot_days: Days after object creation before transition to
                `Archive` tier.  Defaults to `90`.
            delete_days: Days after object creation before permanent
                deletion.  Must be greater than `hot_days`.  Defaults to
                `365`.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.  Override in tests
                only; production stacks should omit this parameter.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `delete_days` is not greater than `hot_days`.
        """
        if delete_days <= hot_days:
            raise ValueError(f"delete_days ({delete_days}) must be greater than hot_days ({hot_days})")

        super().__init__("custom:storage:DataLakeBucket", name, compartment_id, stack_name, opts)

        # The Pulumi logical name (first arg) and the OCI bucket `name=` are
        # intentionally set to the same value so the Pulumi URN and the OCI
        # resource name remain in sync.
        bucket_name = self.create_resource_name("bucket")
        self.bucket = oci.objectstorage.Bucket(
            bucket_name,
            compartment_id=self.compartment_id,
            namespace=namespace,
            name=bucket_name,
            access_type="NoPublicAccess",
            storage_tier="Standard",
            versioning="Disabled",
            freeform_tags=self.create_freeform_tags(bucket_name, "bucket"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.lifecycle_policy = oci.objectstorage.ObjectLifecyclePolicy(
            self.create_resource_name("lifecycle"),
            namespace=namespace,
            bucket=self.bucket.name,
            rules=[
                oci.objectstorage.ObjectLifecyclePolicyRuleArgs(
                    action="ARCHIVE",
                    is_enabled=True,
                    name="archive-cold-data",
                    # The pulumi-oci SDK models timeAmount as pulumi.Input[str]
                    # (mirroring the Terraform provider's string type), so the
                    # integer day count must be coerced to str here.
                    time_amount=str(hot_days),
                    time_unit="DAYS",
                    target="objects",
                ),
                oci.objectstorage.ObjectLifecyclePolicyRuleArgs(
                    action="DELETE",
                    is_enabled=True,
                    name="delete-expired-data",
                    # See note above on time_amount str coercion.
                    time_amount=str(delete_days),
                    time_unit="DAYS",
                    target="objects",
                ),
                _abort_multipart_rule(),
            ],
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.bucket_name = self.bucket.name
        self.register_outputs({"bucket_name": self.bucket.name})


class ArchiveBucket(_BucketMixin, BaseResource):
    """OCI Object Storage bucket for long-term archiving and compliance.

    Creates an `Archive`-tier bucket with versioning enabled and a
    retention rule that prevents objects from being deleted or modified for
    `retention_days` days after creation.  Access is locked to
    `NoPublicAccess`.

    The retention rule provides a strong compliance control: no principal
    can delete an object before its retention period expires without an
    explicit administrator override.  Note that the rule created here is
    not cryptographically locked — a tenancy administrator can still modify
    or delete the retention rule itself via the OCI Console or API.
    Locking the retention rule requires a separate, manual action after
    initial deployment (OCI does not support immutable rule creation in a
    single API call).  This satisfies soft data-retention requirements
    (GDPR, HIPAA, financial regulations) but review your compliance mandate
    to determine whether a hard lock is required.

    Resources created:

    - One `oci.objectstorage.Bucket` with `NoPublicAccess`, `Archive`
      storage tier, versioning enabled, and an inline
      `BucketRetentionRuleArgs` that prevents object deletion for
      `retention_days` days.

    Attributes:
        bucket: The underlying `oci.objectstorage.Bucket` resource.
        bucket_name: `pulumi.Output[str]` resolving to the OCI bucket name.

    Example:
        ```python
        archive = ArchiveBucket(
            name="audit-logs",
            compartment_id=comp_id,
            namespace="mytenancy",
            retention_days=2555,  # 7 years
        )
        pulumi.export("archive_bucket", archive.bucket_name)
        ```
    """

    bucket: oci.objectstorage.Bucket
    bucket_name: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        namespace: pulumi.Input[str],
        retention_days: int = 2555,
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create an immutable Archive-tier compliance bucket.

        Args:
            name: Logical name (e.g. `"audit-logs"`).  Combined with the
                stack name to form `"{stack}-{name}-bucket"`.
            compartment_id: OCID of the OCI compartment to deploy into.
            namespace: OCI tenancy-level Object Storage namespace.
            retention_days: Minimum number of days objects must be retained
                before they can be deleted.  Must be greater than `0`.
                Defaults to `2555` (approximately 7 years).
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.  Override in tests
                only; production stacks should omit this parameter.
            opts: Pulumi resource options forwarded to the component.

        Raises:
            ValueError: If `retention_days` is not greater than `0`.
        """
        if retention_days <= 0:
            raise ValueError(f"retention_days ({retention_days}) must be greater than 0")

        super().__init__("custom:storage:ArchiveBucket", name, compartment_id, stack_name, opts)

        # The Pulumi logical name (first arg) and the OCI bucket `name=` are
        # intentionally set to the same value so the Pulumi URN and the OCI
        # resource name remain in sync.
        bucket_name = self.create_resource_name("bucket")
        self.bucket = oci.objectstorage.Bucket(
            bucket_name,
            compartment_id=self.compartment_id,
            namespace=namespace,
            name=bucket_name,
            access_type="NoPublicAccess",
            storage_tier="Archive",
            versioning="Enabled",
            retention_rules=[
                oci.objectstorage.BucketRetentionRuleArgs(
                    display_name=self.create_resource_name("retention-rule"),
                    duration=oci.objectstorage.BucketRetentionRuleDurationArgs(
                        # The pulumi-oci SDK models timeAmount as pulumi.Input[str]
                        # (mirroring the Terraform provider's string type), so the
                        # integer day count must be coerced to str here.
                        time_amount=str(retention_days),
                        time_unit="DAYS",
                    ),
                ),
            ],
            freeform_tags=self.create_freeform_tags(bucket_name, "bucket"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.bucket_name = self.bucket.name
        self.register_outputs({"bucket_name": self.bucket.name})


class StaticWebsiteBucket(_BucketMixin, BaseResource):
    """OCI Object Storage bucket configured for static website hosting.

    Creates a `Standard`-tier bucket with `ObjectRead` public access,
    making every object URL-accessible without authentication.  Intended
    for static assets (HTML, CSS, JS, images) served directly from OCI
    Object Storage, optionally fronted by OCI CDN.

    This is the only CloudSpells storage spell where public access is
    intentional and enforced.  Versioning is disabled to keep the object
    namespace clean for deployment tooling.

    Objects are accessible at:
    `https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/<bucket>/o/<object>`

    Do not upload sensitive data to this bucket.

    Resources created:

    - One `oci.objectstorage.Bucket` with `ObjectRead` access and
      `Standard` storage tier.

    Attributes:
        bucket: The underlying `oci.objectstorage.Bucket` resource.
        bucket_name: `pulumi.Output[str]` resolving to the OCI bucket name.

    Raises:
        RuntimeError: If `BaseResource.__init__` fails during Pulumi context
            setup (e.g. outside a Pulumi program entry point).

    Example:
        ```python
        site = StaticWebsiteBucket(
            name="my-site",
            compartment_id=comp_id,
            namespace="mytenancy",
        )
        # All objects in this bucket are publicly readable — do not upload
        # sensitive data.  access_type="ObjectRead" is enforced by the spell.
        pulumi.export("site_bucket", site.bucket_name)
        ```
    """

    bucket: oci.objectstorage.Bucket
    bucket_name: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        compartment_id: pulumi.Input[str],
        namespace: pulumi.Input[str],
        stack_name: str | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        """Create a publicly readable static website bucket.

        Every object uploaded to this bucket is publicly accessible via
        its OCI Object Storage URL without any authentication.  This is
        intentional for static website hosting.  Do not upload sensitive
        data to this bucket.

        Args:
            name: Logical name (e.g. `"my-site"`).  Combined with the
                stack name to form `"{stack}-{name}-bucket"`.
            compartment_id: OCID of the OCI compartment to deploy into.
            namespace: OCI tenancy-level Object Storage namespace.
            stack_name: Pulumi stack name.  Defaults to
                `pulumi.get_stack()` when `None`.  Override in tests
                only; production stacks should omit this parameter.
            opts: Pulumi resource options forwarded to the component.
        """
        super().__init__("custom:storage:StaticWebsiteBucket", name, compartment_id, stack_name, opts)

        pulumi.warn(
            f"StaticWebsiteBucket '{name}': access_type='ObjectRead' — every object in "
            "this bucket is publicly readable without authentication.  Do not upload "
            "sensitive data.  This is intentional for static website hosting."
        )

        # The Pulumi logical name (first arg) and the OCI bucket `name=` are
        # intentionally set to the same value so the Pulumi URN and the OCI
        # resource name remain in sync.
        bucket_name = self.create_resource_name("bucket")
        self.bucket = oci.objectstorage.Bucket(
            bucket_name,
            compartment_id=self.compartment_id,
            namespace=namespace,
            name=bucket_name,
            access_type="ObjectRead",
            storage_tier="Standard",
            versioning="Disabled",
            freeform_tags=self.create_freeform_tags(bucket_name, "bucket"),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.bucket_name = self.bucket.name
        self.register_outputs({"bucket_name": self.bucket.name})


__all__ = [
    "ArchiveBucket",
    "BackupBucket",
    "DataLakeBucket",
    "ObjectStorageBucket",
    "StaticWebsiteBucket",
]
