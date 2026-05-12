"""cs backend — backend URL helpers for Pulumi state storage.

Provides sub-commands for building Pulumi-compatible backend URLs so that
stacks can store state in remote backends instead of the local filesystem.
"""

__all__ = ["backend_app"]

from typing import Annotated

import typer
from cloudspells.cli.automation.backend import oci_backend_url
from cloudspells.cli.console import console

backend_app = typer.Typer(
    name="backend",
    help="Generate Pulumi backend URLs for remote state storage.",
    no_args_is_help=True,
)


@backend_app.command("oci-url")
def oci_url(
    namespace: Annotated[str, typer.Option("--namespace", "-n", help="OCI Object Storage namespace (tenant).")],
    bucket: Annotated[str, typer.Option("--bucket", "-b", help="OCI bucket name.")],
    region: Annotated[str, typer.Option("--region", "-r", help="OCI region identifier.")],
) -> None:
    """Print a Pulumi S3 backend URL for OCI Object Storage.

    The printed URL can be passed to `cs new --backend` to store stack state
    in an OCI bucket instead of the local filesystem.

    OCI S3-compatible credentials must be set in the environment before
    running `cs up`:

    ```
    export AWS_ACCESS_KEY_ID=<OCI customer secret key>
    export AWS_SECRET_ACCESS_KEY=<OCI customer secret key secret>
    export AWS_DEFAULT_REGION=<region>
    ```

    Raises:
        typer.Exit: Never — always prints the URL and exits cleanly.

    Examples:
        cs backend oci-url --namespace myns --bucket tf-state --region eu-frankfurt-1

        cs new vcn my-net --backend "$(cs backend oci-url -n ns -b bucket -r eu-frankfurt-1)"
    """
    url = oci_backend_url(namespace, bucket, region)
    typer.echo(url)
    console.print('\n[dim]Pass this URL to:[/dim]  cs new <spell> <name> [bold]--backend[/bold] "<url>"')
