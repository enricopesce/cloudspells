"""Object Storage example — the full palette of bucket spells.

Deploys one bucket of every CloudSpells storage type so the example covers
every retention and access pattern the OCI provider offers:

- `ObjectStorageBucket`: general-purpose private bucket with no lifecycle
  policy.  Suitable for application artifacts, config, and assets.
- `BackupBucket`: versioned bucket that permanently deletes objects after
  `retention_days` days.  Suitable for database dumps, snapshot archives,
  and any data you need to recover within a fixed window.
- `DataLakeBucket`: lifecycle bucket that moves objects to Archive tier
  after `hot_days` days, then permanently deletes them after
  `delete_days` days.  Suitable for event logs, telemetry, and analytics
  pipelines where hot data is queried frequently but cold data rarely is.
- `ArchiveBucket`: Archive-tier bucket with an immutable retention rule.
  Suitable for long-term compliance and audit storage where objects must
  not be deletable before the retention window elapses.
- `StaticWebsiteBucket`: publicly readable Standard-tier bucket for static
  website hosting.  Every object is world-readable — do not upload secrets.

The OCI tenancy namespace is a fixed string visible in the OCI Console under
Tenancy Details.  It cannot be resolved automatically at deploy time (CS-002)
and must be supplied via config.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

from cloudspells.core import Config
from cloudspells.providers.oci.storage import (
    ArchiveBucket,
    BackupBucket,
    DataLakeBucket,
    ObjectStorageBucket,
    StaticWebsiteBucket,
)

config = Config()
compartment_id: str = config.require("compartment_ocid")
namespace: str = config.require("namespace")

# ObjectStorageBucket — general-purpose private bucket, no lifecycle policy.
artifacts: ObjectStorageBucket = ObjectStorageBucket(
    name="artifacts",
    compartment_id=compartment_id,
    namespace=namespace,
)

# BackupBucket — versioned, deletes objects after 30 days.
backup: BackupBucket = BackupBucket(
    name="db-backups",
    compartment_id=compartment_id,
    namespace=namespace,
    retention_days=30,
)

# DataLakeBucket — hot for 90 days, archived until day 365, then deleted.
lake: DataLakeBucket = DataLakeBucket(
    name="events",
    compartment_id=compartment_id,
    namespace=namespace,
    hot_days=90,
    delete_days=365,
)

# ArchiveBucket — Archive tier with an immutable 7-year retention rule.
# Objects cannot be deleted before retention_days elapses (compliance/audit).
audit: ArchiveBucket = ArchiveBucket(
    name="audit-logs",
    compartment_id=compartment_id,
    namespace=namespace,
    retention_days=2555,  # ~7 years; this is also the default.
)

# StaticWebsiteBucket — public-read Standard tier for static hosting.
# ⚠ Every object is world-readable without authentication. Do not upload
# sensitive data. The spell emits a pulumi.warn() to underline this.
site: StaticWebsiteBucket = StaticWebsiteBucket(
    name="site",
    compartment_id=compartment_id,
    namespace=namespace,
)

artifacts.export()
backup.export()
lake.export()
audit.export()
site.export()
