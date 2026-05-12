"""OCI Object Storage backend URL builder for Pulumi local state.

OCI Object Storage exposes an S3-compatible API. This module builds the
Pulumi backend URL that points a stack at an OCI bucket instead of the
local filesystem.
"""

__all__ = ["oci_backend_url"]


def oci_backend_url(namespace: str, bucket: str, region: str) -> str:
    """Build a Pulumi-compatible S3 backend URL for OCI Object Storage.

    The returned URL is suitable for use as the `backend.url` in `Pulumi.yaml`
    or as the value passed to `cs new --backend`.

    OCI credentials must be exported as S3-compatible environment variables
    before running `cs up`:

    ```
    export AWS_ACCESS_KEY_ID=<OCI customer secret key>
    export AWS_SECRET_ACCESS_KEY=<OCI customer secret key secret>
    export AWS_DEFAULT_REGION=<region>
    ```

    Args:
        namespace: OCI Object Storage namespace (tenant namespace string).
        bucket: OCI bucket name.
        region: OCI region identifier (e.g. `"eu-frankfurt-1"`).

    Returns:
        Pulumi S3-backend URL string, e.g.
        `"s3://my-bucket?endpoint=https://ns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com&region=eu-frankfurt-1&s3ForcePathStyle=true"`.

    Example:
        ```python
        url = oci_backend_url("myns", "tf-state", "eu-frankfurt-1")
        # s3://tf-state?endpoint=https://myns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com&...
        ```
    """
    endpoint = f"https://{namespace}.compat.objectstorage.{region}.oraclecloud.com"
    return f"s3://{bucket}?endpoint={endpoint}&region={region}&s3ForcePathStyle=true"
