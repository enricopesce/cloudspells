"""Tests for OCI backend URL builder and cs backend command."""

from cloudspells.cli.automation.backend import oci_backend_url
from cloudspells.cli.main import app


def test_oci_backend_url_contains_bucket() -> None:
    url = oci_backend_url("myns", "my-bucket", "eu-frankfurt-1")
    assert url.startswith("s3://my-bucket")


def test_oci_backend_url_contains_endpoint() -> None:
    url = oci_backend_url("myns", "my-bucket", "eu-frankfurt-1")
    assert "myns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com" in url


def test_oci_backend_url_contains_region() -> None:
    url = oci_backend_url("myns", "my-bucket", "eu-frankfurt-1")
    assert "region=eu-frankfurt-1" in url


def test_oci_backend_url_forces_path_style() -> None:
    url = oci_backend_url("myns", "my-bucket", "eu-frankfurt-1")
    assert "s3ForcePathStyle=true" in url


def test_backend_oci_url_command_prints_url(runner) -> None:
    result = runner.invoke(
        app,
        ["backend", "oci-url", "--namespace", "myns", "--bucket", "bkt", "--region", "eu-frankfurt-1"],
    )
    assert result.exit_code == 0, result.output
    assert "s3://bkt" in result.output
    assert "myns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com" in result.output
