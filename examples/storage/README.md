# Storage Example

Deploys one bucket of every CloudSpells storage type so the example covers the full palette of retention and access patterns: a general-purpose private bucket, a versioned backup bucket with fixed-window deletion, a data lake bucket with tiered lifecycle management, an immutable compliance archive, and a public static-website bucket.

## What Gets Created

**Object storage bucket** (`artifacts`):

- `oci.objectstorage.Bucket` — Standard tier, versioning disabled, `NoPublicAccess`
- No lifecycle policy — general-purpose private storage

**Backup bucket** (`db-backups`):

- `oci.objectstorage.Bucket` — Standard tier, versioning enabled, `NoPublicAccess`
- `oci.objectstorage.ObjectLifecyclePolicy` — deletes all objects after 30 days

**Data lake bucket** (`events`):

- `oci.objectstorage.Bucket` — Standard tier, versioning disabled, `NoPublicAccess`
- `oci.objectstorage.ObjectLifecyclePolicy` — archives objects after 90 days, deletes after 365 days

**Archive bucket** (`audit-logs`):

- `oci.objectstorage.Bucket` — Archive tier, versioning enabled, `NoPublicAccess`
- `oci.objectstorage.BucketRetentionRule` — objects cannot be deleted for ~7 years (2555 days)

**Static website bucket** (`site`):

- `oci.objectstorage.Bucket` — Standard tier, versioning disabled, **`ObjectRead` (public)**
- ⚠ Every object is world-readable without authentication — do not upload sensitive data

## Architecture

```
ObjectStorageBucket (artifacts)
  Standard tier · versioning disabled · private
  └── No lifecycle policy

BackupBucket (db-backups)
  Standard tier · versioning enabled · private
  └── Lifecycle: DELETE after 30 days

DataLakeBucket (events)
  Standard tier · versioning disabled · private
  └── Lifecycle: ARCHIVE after 90 days → DELETE after 365 days

ArchiveBucket (audit-logs)
  Archive tier · versioning enabled · private
  └── Retention rule: objects immutable for ~7 years (2555 days)

StaticWebsiteBucket (site)
  Standard tier · versioning disabled · PUBLIC read
  └── No lifecycle policy
```

## Prerequisites

- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed
- OCI credentials configured (`~/.oci/config`)
- Python virtual environment set up from the repository root:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- Your OCI tenancy Object Storage namespace. Find it in the OCI Console under **Profile → Tenancy Details → Object Storage Namespace**, or via the CLI:
  ```bash
  oci os ns get
  ```

## Configuration

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `compartment_ocid` | Yes | — | OCI compartment OCID |
| `namespace` | Yes | — | OCI tenancy Object Storage namespace |

## Deploy

```bash
cd examples/storage

# Create a new stack
pulumi stack init dev

# Set required config
pulumi config set compartment_ocid <your-compartment-ocid>
pulumi config set namespace <your-tenancy-namespace>

# Preview changes
pulumi preview

# Deploy
pulumi up
```

## Outputs

| Output | Description |
|--------|-------------|
| `artifacts_bucket_name` | Physical name of the general-purpose bucket |
| `db_backups_bucket_name` | Physical name of the backup bucket |
| `events_bucket_name` | Physical name of the data lake bucket |
| `audit_logs_bucket_name` | Physical name of the archive bucket |
| `site_bucket_name` | Physical name of the static website bucket |

## Teardown

```bash
pulumi destroy
```

> **Note:** `ArchiveBucket` enforces a retention rule, so its objects cannot be
> deleted until the retention window elapses. An empty archive bucket destroys
> cleanly; a bucket containing objects still within retention will block
> `pulumi destroy` until those objects age out.

## Storage Spell Reference

| Spell | Use case |
|-------|----------|
| `ObjectStorageBucket` | General-purpose private bucket; no lifecycle policy |
| `BackupBucket` | Versioned bucket with retention-based deletion |
| `DataLakeBucket` | Hot → Archive → Delete lifecycle for analytics |
| `ArchiveBucket` | Archive tier with a compliance retention rule (default 7 years) |
| `StaticWebsiteBucket` | Public-read bucket for static asset hosting |
