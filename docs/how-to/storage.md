# How to Use Object Storage Buckets

This guide shows you how to provision OCI Object Storage buckets for five common use cases using the CloudSpells storage spells.

## When to use this

- You need a private bucket for application artifacts or configuration.
- You need versioned backups with automatic retention-based expiry.
- You need a tiered data lake bucket (hot to archive to delete).
- You need an immutable archive bucket for compliance (GDPR, HIPAA, financial).
- You need a publicly readable bucket for static website hosting.

---

## Prerequisites

All storage spells require your OCI tenancy Object Storage **namespace** — a fixed string assigned to your tenancy. Find it in the OCI Console under **Tenancy Details**, or via the CLI:

```bash
oci os ns get --query 'data' --raw-output
```

Store it in Pulumi config:

```bash
pulumi config set namespace <your-namespace>
```

---

## General-purpose private bucket

`ObjectStorageBucket` creates a private, standard-tier bucket with no versioning:

```python
from cloudspells.providers.oci.storage import ObjectStorageBucket

bucket = ObjectStorageBucket(
    name="artifacts",
    compartment_id=compartment_id,
    namespace=namespace,
)
bucket.export()
```

Access is locked to `NoPublicAccess`. Storage tier is `Standard`. Both are opinionated defaults.

---

## Versioned backup bucket

`BackupBucket` enables versioning and adds a lifecycle policy that deletes objects after `retention_days`:

```python
from cloudspells.providers.oci.storage import BackupBucket

backup = BackupBucket(
    name="db-backups",
    compartment_id=compartment_id,
    namespace=namespace,
    retention_days=30,
)
backup.export()
```

Stale multipart uploads are automatically aborted after 7 days. Object versions are recoverable within the retention window.

---

## Data lake bucket

`DataLakeBucket` implements a two-stage lifecycle: objects move to `Archive` tier after `hot_days`, then are permanently deleted after `delete_days`:

```python
from cloudspells.providers.oci.storage import DataLakeBucket

lake = DataLakeBucket(
    name="events",
    compartment_id=compartment_id,
    namespace=namespace,
    hot_days=90,
    delete_days=730,
)
lake.export()
```

Versioning is disabled to control costs at high write volumes. `delete_days` must be greater than `hot_days`.

---

## Archive bucket for compliance

`ArchiveBucket` creates an `Archive`-tier bucket with a retention rule that prevents object deletion for `retention_days`:

```python
from cloudspells.providers.oci.storage import ArchiveBucket

archive = ArchiveBucket(
    name="audit-logs",
    compartment_id=compartment_id,
    namespace=namespace,
    retention_days=2555,  # ~7 years
)
archive.export()
```

The retention rule is **not** cryptographically locked at creation time. A tenancy administrator can modify the rule via the OCI Console. If your compliance mandate requires a hard lock, apply it manually after deployment.

---

## Static website bucket

`StaticWebsiteBucket` creates a publicly readable bucket for static assets (HTML, CSS, JS, images):

```python
from cloudspells.providers.oci.storage import StaticWebsiteBucket

site = StaticWebsiteBucket(
    name="docs-site",
    compartment_id=compartment_id,
    namespace=namespace,
)
site.export()
```

Every object is accessible at:

```text
https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/<bucket>/o/<object>
```

A warning is emitted during deployment as a reminder that all objects are publicly readable. Do not upload sensitive data.

---

## Choosing the right bucket

| Use case | Spell | Tier | Versioning | Lifecycle | Access |
|----------|-------|------|------------|-----------|--------|
| App artifacts | `ObjectStorageBucket` | Standard | Off | None | Private |
| Backups | `BackupBucket` | Standard | On | Delete after N days | Private |
| Analytics / data lake | `DataLakeBucket` | Standard | Off | Archive then delete | Private |
| Compliance archive | `ArchiveBucket` | Archive | On | Retention rule | Private |
| Static website | `StaticWebsiteBucket` | Standard | Off | None | Public read |

---

## Outputs

All spells export `{name}_bucket_name` via `export()`.

---

## Configuration reference

| Spell | Parameter | Default | Description |
|-------|-----------|---------|-------------|
| All | `namespace` | _(required)_ | OCI tenancy Object Storage namespace |
| `BackupBucket` | `retention_days` | `90` | Days before permanent deletion |
| `DataLakeBucket` | `hot_days` | `90` | Days before archive transition |
| `DataLakeBucket` | `delete_days` | `365` | Days before permanent deletion |
| `ArchiveBucket` | `retention_days` | `2555` | Minimum retention before deletion allowed |
