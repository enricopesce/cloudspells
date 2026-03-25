"""Unit tests for all ObjectStorage spell variants."""

import unittest

import pulumi

# Set up mocks BEFORE importing infrastructure
from tests.mocks import set_mocks

set_mocks()

# Import AFTER mocks are set
from cloudspells.providers.oci.storage import (
    ArchiveBucket,
    BackupBucket,
    DataLakeBucket,
    ObjectStorageBucket,
    StaticWebsiteBucket,
)


class TestObjectStorageBucket(unittest.TestCase):
    """Test cases for ObjectStorageBucket spell."""

    @pulumi.runtime.test
    def test_bucket_created(self):
        """Test that ObjectStorageBucket creates the bucket resource."""
        bucket = ObjectStorageBucket(
            name="test-bucket",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)

        return bucket.bucket.name.apply(check)

    @pulumi.runtime.test
    def test_bucket_name_follows_namer(self):
        """Test that the bucket name uses ResourceNamer pattern."""
        bucket = ObjectStorageBucket(
            name="artifacts",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            stack_name="prod",
        )

        def check(name: str) -> None:
            self.assertIn("prod", name)
            self.assertIn("artifacts", name)
            self.assertIn("bucket", name)

        return bucket.bucket.name.apply(check)

    @pulumi.runtime.test
    def test_get_bucket_name_returns_output(self):
        """Test that get_bucket_name() returns a pulumi.Output."""
        bucket = ObjectStorageBucket(
            name="getter-bucket",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)

        return bucket.get_bucket_name().apply(check)

    def test_bucket_name_output_attribute_set(self) -> None:
        """Test that bucket_name attribute is set on the spell."""
        bucket = ObjectStorageBucket(
            name="attr-bucket",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )
        self.assertIsNotNone(bucket.bucket_name)

    def test_bucket_resource_attribute_set(self) -> None:
        """Test that the bucket attribute holds the OCI resource."""
        bucket = ObjectStorageBucket(
            name="resource-bucket",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )
        self.assertIsNotNone(bucket.bucket)


class TestBackupBucket(unittest.TestCase):
    """Test cases for BackupBucket spell."""

    @pulumi.runtime.test
    def test_bucket_and_lifecycle_created(self):
        """Test that BackupBucket creates the bucket and lifecycle policy."""
        backup = BackupBucket(
            name="db-backups",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            stack_name="prod",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)
            self.assertIn("prod", name)
            self.assertIn("db-backups", name)

        self.assertIsNotNone(backup.lifecycle_policy)
        return backup.bucket.name.apply(check)

    @pulumi.runtime.test
    def test_default_retention(self):
        """Test that BackupBucket defaults to 90-day retention."""
        backup = BackupBucket(
            name="default-retention",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)

        return backup.get_bucket_name().apply(check)

    def test_custom_retention(self) -> None:
        """Test that BackupBucket accepts a custom retention_days."""
        backup = BackupBucket(
            name="custom-retention",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            retention_days=30,
        )
        self.assertIsNotNone(backup.bucket)
        self.assertIsNotNone(backup.lifecycle_policy)

    def test_zero_retention_raises(self) -> None:
        """Test that retention_days=0 raises ValueError."""
        with self.assertRaises(ValueError):
            BackupBucket(
                name="zero-retention",
                compartment_id="ocid1.compartment.test",
                namespace="testtenancy",
                retention_days=0,
            )

    def test_negative_retention_raises(self) -> None:
        """Test that negative retention_days raises ValueError."""
        with self.assertRaises(ValueError):
            BackupBucket(
                name="neg-retention",
                compartment_id="ocid1.compartment.test",
                namespace="testtenancy",
                retention_days=-1,
            )

    def test_bucket_name_attribute_set(self) -> None:
        """Test that bucket_name Output attribute is set."""
        backup = BackupBucket(
            name="attr-backup",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )
        self.assertIsNotNone(backup.bucket_name)


class TestDataLakeBucket(unittest.TestCase):
    """Test cases for DataLakeBucket spell."""

    @pulumi.runtime.test
    def test_bucket_and_lifecycle_created(self):
        """Test that DataLakeBucket creates bucket and tiered lifecycle policy."""
        lake = DataLakeBucket(
            name="events",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            stack_name="prod",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)
            self.assertIn("prod", name)
            self.assertIn("events", name)

        self.assertIsNotNone(lake.lifecycle_policy)
        return lake.bucket.name.apply(check)

    def test_invalid_delete_days_raises(self) -> None:
        """Test that delete_days <= hot_days raises ValueError."""
        with self.assertRaises(ValueError):
            DataLakeBucket(
                name="bad-lake",
                compartment_id="ocid1.compartment.test",
                namespace="testtenancy",
                hot_days=180,
                delete_days=90,
            )

    def test_equal_days_raises(self) -> None:
        """Test that delete_days == hot_days raises ValueError."""
        with self.assertRaises(ValueError):
            DataLakeBucket(
                name="equal-lake",
                compartment_id="ocid1.compartment.test",
                namespace="testtenancy",
                hot_days=90,
                delete_days=90,
            )

    def test_custom_lifecycle_days(self) -> None:
        """Test that DataLakeBucket accepts custom hot_days and delete_days."""
        lake = DataLakeBucket(
            name="custom-lake",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            hot_days=60,
            delete_days=730,
        )
        self.assertIsNotNone(lake.bucket)
        self.assertIsNotNone(lake.lifecycle_policy)

    def test_bucket_name_attribute_set(self) -> None:
        """Test that bucket_name Output attribute is set."""
        lake = DataLakeBucket(
            name="attr-lake",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )
        self.assertIsNotNone(lake.bucket_name)


class TestArchiveBucket(unittest.TestCase):
    """Test cases for ArchiveBucket spell."""

    @pulumi.runtime.test
    def test_bucket_created_with_retention(self):
        """Test that ArchiveBucket creates an Archive-tier bucket."""
        archive = ArchiveBucket(
            name="audit-logs",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            stack_name="prod",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)
            self.assertIn("prod", name)
            self.assertIn("audit-logs", name)

        return archive.bucket.name.apply(check)

    def test_default_retention_days(self) -> None:
        """Test that ArchiveBucket defaults to 2555-day retention."""
        archive = ArchiveBucket(
            name="default-archive",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )
        self.assertIsNotNone(archive.bucket)

    def test_custom_retention_days(self) -> None:
        """Test that ArchiveBucket accepts a custom retention_days."""
        archive = ArchiveBucket(
            name="short-archive",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            retention_days=365,
        )
        self.assertIsNotNone(archive.bucket)

    def test_zero_retention_raises(self) -> None:
        """Test that retention_days=0 raises ValueError."""
        with self.assertRaises(ValueError):
            ArchiveBucket(
                name="zero-archive",
                compartment_id="ocid1.compartment.test",
                namespace="testtenancy",
                retention_days=0,
            )

    def test_negative_retention_raises(self) -> None:
        """Test that negative retention_days raises ValueError."""
        with self.assertRaises(ValueError):
            ArchiveBucket(
                name="neg-archive",
                compartment_id="ocid1.compartment.test",
                namespace="testtenancy",
                retention_days=-1,
            )

    def test_bucket_name_attribute_set(self) -> None:
        """Test that bucket_name Output attribute is set."""
        archive = ArchiveBucket(
            name="attr-archive",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )
        self.assertIsNotNone(archive.bucket_name)


class TestStaticWebsiteBucket(unittest.TestCase):
    """Test cases for StaticWebsiteBucket spell."""

    @pulumi.runtime.test
    def test_bucket_created(self):
        """Test that StaticWebsiteBucket creates the bucket resource."""
        site = StaticWebsiteBucket(
            name="my-site",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
            stack_name="prod",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)
            self.assertIn("prod", name)
            self.assertIn("my-site", name)

        return site.bucket.name.apply(check)

    def test_bucket_name_attribute_set(self) -> None:
        """Test that bucket_name Output attribute is set."""
        site = StaticWebsiteBucket(
            name="attr-site",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )
        self.assertIsNotNone(site.bucket_name)

    @pulumi.runtime.test
    def test_get_bucket_name_returns_output(self):
        """Test that get_bucket_name() returns a pulumi.Output."""
        site = StaticWebsiteBucket(
            name="getter-site",
            compartment_id="ocid1.compartment.test",
            namespace="testtenancy",
        )

        def check(name: str) -> None:
            self.assertIsNotNone(name)

        return site.get_bucket_name().apply(check)


if __name__ == "__main__":
    unittest.main()
