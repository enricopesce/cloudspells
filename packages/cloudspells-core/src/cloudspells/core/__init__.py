"""CloudSpells core public API.

Exports the two symbols available to user-facing stacks without requiring
a direct Pulumi import:

- `Config` — thin wrapper around `pulumi.Config` for reading stack
  configuration values (compartment OCIDs, CIDR blocks, feature flags,
  etc.).
- `ports` — well-known TCP/UDP port-number constants (`HTTP`, `HTTPS`,
  `SSH`, `POSTGRES`, etc.) for use in security rules.

All other core utilities (`BaseResource`, `ResourceNamer`, `ResourceTagger`,
`Helper`) are internal infrastructure consumed by provider packages, not
by user stacks directly.

Example:
    ```python
    from cloudspells.core import Config, ports

    config = Config()
    compartment_id = config.require("compartment_ocid")
    ssh_port = ports.SSH  # 22
    ```
"""

from . import ports
from .config import Config

__all__ = ["Config", "ports"]
