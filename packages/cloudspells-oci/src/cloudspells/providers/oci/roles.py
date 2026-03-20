"""Role-based security posture descriptors — re-exported from core abstractions.

`Role` and all predefined role instances are defined in
`cloudspells.core.abstractions.roles` and re-exported here for backward
compatibility.  Import from either location; prefer the core path in
provider-agnostic code:

```python
# Provider-agnostic code
from cloudspells.core.abstractions import Role, APP_SERVER

# OCI-specific code (both forms work)
from cloudspells.providers.oci import APP_SERVER
from cloudspells.providers.oci.roles import APP_SERVER
```

Exports:
    Role: Security posture dataclass.
    INTERNET_EDGE: Predefined role for internet-facing resources.
    APP_SERVER: Predefined role for private-tier application servers.
    DATABASE: Predefined role for secure-tier databases.
    CACHE: Predefined role for private-tier caches and message brokers.
    MANAGEMENT: Predefined role for management-tier tooling.
"""

from cloudspells.core.abstractions.roles import (
    APP_SERVER,
    CACHE,
    DATABASE,
    INTERNET_EDGE,
    MANAGEMENT,
    Role,
)

__all__ = [
    "APP_SERVER",
    "CACHE",
    "DATABASE",
    "INTERNET_EDGE",
    "MANAGEMENT",
    "Role",
]
