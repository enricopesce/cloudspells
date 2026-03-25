"""Object Storage example — backup bucket and data lake bucket.

Deploys two complementary storage buckets:

- `BackupBucket`: versioned bucket that permanently deletes objects after
  `retention_days` days.  Suitable for database dumps, snapshot archives,
  and any data you need to recover within a fixed window.
- `DataLakeBucket`: lifecycle bucket that moves objects to Archive tier
  after `hot_days` days, then permanently deletes them after
  `delete_days` days.  Suitable for event logs, telemetry, and analytics
  pipelines where hot data is queried frequently but cold data rarely is.

The OCI tenancy namespace is a fixed string visible in the OCI Console under
Tenancy Details.  It cannot be resolved automatically at deploy time (CS-002)
and must be supplied via config.
"""

import os
import sys

_root = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-core/src"))
sys.path.insert(0, os.path.join(_root, "packages/cloudspells-oci/src"))

import pulumi

from cloudspells.core import Config
from cloudspells.providers.oci.storage import BackupBucket, DataLakeBucket

config = Config()
compartment_id: str = config.require("compartment_ocid")
namespace: str = config.require("namespace")

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

pulumi.export("backup_bucket_name", backup.bucket_name)
pulumi.export("lake_bucket_name", lake.bucket_name)
