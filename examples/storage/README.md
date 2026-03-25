# Storage Example

Deploys two Object Storage buckets that cover the most common data retention patterns: a versioned backup bucket with fixed-window deletion, and a data lake bucket with tiered lifecycle management.

## What Gets Created

**Backup bucket** (`db-backups`):

- `oci.objectstorage.Bucket` — Standard tier, versioning enabled, `NoPublicAccess`
- `oci.objectstorage.ObjectLifecyclePolicy` — deletes all objects after 30 days

**Data lake bucket** (`events`):

- `oci.objectstorage.Bucket` — Standard tier, versioning disabled, `NoPublicAccess`
- `oci.objectstorage.ObjectLifecyclePolicy` — archives objects after 90 days, deletes after 365 days

## Architecture

```
BackupBucket (db-backups)
  Standard tier · versioning enabled
  └── Lifecycle: DELETE after 30 days

DataLakeBucket (events)
  Standard tier · versioning disabled
  └── Lifecycle: ARCHIVE after 90 days → DELETE after 365 days
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
| `db_backups_bucket_name` | Physical name of the backup bucket |
| `events_bucket_name` | Physical name of the data lake bucket |

## Teardown

```bash
pulumi destroy
```

## Other Storage Spell Variants

| Spell | Use case |
|-------|----------|
| `ObjectStorageBucket` | General-purpose private bucket; no lifecycle policy |
| `BackupBucket` | Versioned bucket with retention-based deletion |
| `DataLakeBucket` | Hot → Archive → Delete lifecycle for analytics |
| `ArchiveBucket` | Archive tier with a compliance retention rule (default 7 years) |
| `StaticWebsiteBucket` | Public-read bucket for static asset hosting |
