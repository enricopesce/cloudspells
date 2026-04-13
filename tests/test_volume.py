"""Unit tests for the VolumeSpec dataclass."""

import unittest

from cloudspells.providers.oci.volume import VolumeSpec


class TestVolumeSpecDefaults(unittest.TestCase):
    """Tests for VolumeSpec default values."""

    def test_default_label(self) -> None:
        """VolumeSpec defaults label to 'data'."""
        vol = VolumeSpec(size_in_gbs=100)
        self.assertEqual(vol.label, "data")

    def test_default_vpus(self) -> None:
        """VolumeSpec defaults vpus_per_gb to PERF_BALANCED (10)."""
        vol = VolumeSpec(size_in_gbs=100)
        self.assertEqual(vol.vpus_per_gb, VolumeSpec.PERF_BALANCED)

    def test_default_not_read_only(self) -> None:
        """VolumeSpec defaults is_read_only to False."""
        vol = VolumeSpec(size_in_gbs=100)
        self.assertFalse(vol.is_read_only)

    def test_default_device_none(self) -> None:
        """VolumeSpec defaults device to None."""
        vol = VolumeSpec(size_in_gbs=100)
        self.assertIsNone(vol.device)


class TestVolumeSpecPerformanceTiers(unittest.TestCase):
    """Tests for the four VolumeSpec performance tier constants."""

    def test_perf_low_constant(self) -> None:
        """PERF_LOW is 0."""
        self.assertEqual(VolumeSpec.PERF_LOW, 0)

    def test_perf_balanced_constant(self) -> None:
        """PERF_BALANCED is 10."""
        self.assertEqual(VolumeSpec.PERF_BALANCED, 10)

    def test_perf_high_constant(self) -> None:
        """PERF_HIGH is 20."""
        self.assertEqual(VolumeSpec.PERF_HIGH, 20)

    def test_perf_ultra_constant(self) -> None:
        """PERF_ULTRA is 120."""
        self.assertEqual(VolumeSpec.PERF_ULTRA, 120)

    def test_all_valid_tiers_accepted(self) -> None:
        """All four PERF_* tiers are accepted without raising."""
        for tier in (VolumeSpec.PERF_LOW, VolumeSpec.PERF_BALANCED, VolumeSpec.PERF_HIGH, VolumeSpec.PERF_ULTRA):
            vol = VolumeSpec(size_in_gbs=100, vpus_per_gb=tier)
            self.assertEqual(vol.vpus_per_gb, tier)


class TestVolumeSpecValidation(unittest.TestCase):
    """Tests for VolumeSpec field validation."""

    def test_size_below_minimum_raises(self) -> None:
        """size_in_gbs < 50 raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=49)

    def test_size_at_minimum_accepted(self) -> None:
        """size_in_gbs == 50 is accepted."""
        vol = VolumeSpec(size_in_gbs=50)
        self.assertEqual(vol.size_in_gbs, 50)

    def test_size_above_maximum_raises(self) -> None:
        """size_in_gbs > 32768 raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=32_769)

    def test_size_at_maximum_accepted(self) -> None:
        """size_in_gbs == 32768 is accepted."""
        vol = VolumeSpec(size_in_gbs=32_768)
        self.assertEqual(vol.size_in_gbs, 32_768)

    def test_invalid_vpus_raises(self) -> None:
        """vpus_per_gb not in {0, 10, 20, 120} raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, vpus_per_gb=5)

    def test_invalid_label_empty_raises(self) -> None:
        """An empty label raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, label="")

    def test_invalid_label_uppercase_raises(self) -> None:
        """A label with uppercase letters raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, label="Data")

    def test_invalid_label_trailing_hyphen_raises(self) -> None:
        """A label with a trailing hyphen raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, label="data-")

    def test_invalid_label_consecutive_hyphens_raises(self) -> None:
        """A label with consecutive hyphens raises ValueError."""
        with self.assertRaises(ValueError):
            VolumeSpec(size_in_gbs=100, label="da--ta")

    def test_valid_label_with_hyphen(self) -> None:
        """A label with a single internal hyphen is accepted."""
        vol = VolumeSpec(size_in_gbs=100, label="my-data")
        self.assertEqual(vol.label, "my-data")

    def test_valid_label_with_digits(self) -> None:
        """A label ending with a digit is accepted."""
        vol = VolumeSpec(size_in_gbs=100, label="disk1")
        self.assertEqual(vol.label, "disk1")


class TestVolumeSpecImmutability(unittest.TestCase):
    """Tests for VolumeSpec frozen-dataclass immutability."""

    def test_frozen_raises_on_assignment(self) -> None:
        """VolumeSpec is frozen — attribute assignment raises."""
        vol = VolumeSpec(size_in_gbs=100)
        with self.assertRaises(AttributeError):
            vol.size_in_gbs = 200  # type: ignore[misc]


class TestVolumeSpecCustomValues(unittest.TestCase):
    """Tests for VolumeSpec with fully specified fields."""

    def test_custom_spec_fields(self) -> None:
        """All fields are stored correctly when explicitly supplied."""
        vol = VolumeSpec(
            size_in_gbs=500,
            label="db",
            vpus_per_gb=VolumeSpec.PERF_HIGH,
            is_read_only=True,
            device="/dev/oracleoci/oraclevdb",
        )
        self.assertEqual(vol.size_in_gbs, 500)
        self.assertEqual(vol.label, "db")
        self.assertEqual(vol.vpus_per_gb, VolumeSpec.PERF_HIGH)
        self.assertTrue(vol.is_read_only)
        self.assertEqual(vol.device, "/dev/oracleoci/oraclevdb")


if __name__ == "__main__":
    unittest.main()
