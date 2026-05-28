"""Resource naming utilities for CloudSpells.

Provides `ResourceNamer`, which generates consistent, predictable names
for every resource created by a CloudSpells component. All names follow
the pattern:

```
{stack_name}-{resource_name}-{suffix}
```

DNS labels are built by concatenating a short prefix with the stack name.
OCI requires DNS labels to be at most 15 alphanumeric characters, so keep
both `prefix` and `stack_name` short.
"""

__all__ = ["ResourceNamer"]

import hashlib
import re


class ResourceNamer:
    """Generate standardised resource names and DNS labels.

    Every `BaseResource` owns a `ResourceNamer` instance and delegates naming
    to it via `BaseResource.create_resource_name` and
    `BaseResource.create_dns_label`.

    Attributes:
        stack_name: Pulumi stack name (e.g. `"prod"`).
        resource_name: Logical name of the spell (e.g. `"lab"`).
    """

    stack_name: str
    resource_name: str

    def __init__(self, stack_name: str, resource_name: str) -> None:
        """Initialise a namer for a specific resource.

        Args:
            stack_name: Pulumi stack name (e.g. `"prod"`).
            resource_name: Logical name of the spell (e.g. `"lab"`).
        """
        self.stack_name = stack_name
        self.resource_name = resource_name

    def create_resource_name(self, suffix: str) -> str:
        """Build a standardised OCI resource name.

        Combines the stack name, resource name, and a type suffix into the
        canonical CloudSpells naming pattern: `{stack_name}-{resource_name}-{suffix}`.

        Args:
            suffix: Resource type suffix (e.g. `"vcn"`, `"igw"`, `"sn-public"`).

        Returns:
            Fully-qualified resource name string.

        Example:
            >>> namer = ResourceNamer("prod", "lab")
            >>> namer.create_resource_name("vcn")
            'prod-lab-vcn'
        """
        return f"{self.stack_name}-{self.resource_name}-{suffix}"

    def create_dns_label(self, prefix: str) -> str:
        """Build a DNS-safe label for OCI networking resources.

        OCI requires DNS labels to be alphanumeric, start with a letter, and
        be at most 15 characters.  This method removes invalid characters,
        lowercases the result, guarantees a leading letter, and truncates with
        a short hash suffix when needed so common stack names cannot fail only
        at apply time.

        Args:
            prefix: Short alphanumeric prefix (e.g. `"pub"`, `"priv"`,
                `"vcn"`).

        Returns:
            DNS-safe label derived from `"{prefix}{stack_name}"`.

        Example:
            >>> namer = ResourceNamer("my-stack", "lab")
            >>> namer.create_dns_label("vcn")
            'vcnmystack'
        """
        raw_label = f"{prefix}{self.stack_name}"
        label = re.sub(r"[^A-Za-z0-9]", "", raw_label).lower()
        if not label:
            label = "c"
        if not label[0].isalpha():
            label = f"c{label}"
        if len(label) > 15:
            digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:4]
            label = f"{label[:11]}{digest}"
        return label
