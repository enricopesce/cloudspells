class ResourceNamer:
    """Helper class for creating standardized resource names and DNS labels."""

    stack_name: str
    resource_name: str

    def __init__(self, stack_name: str, resource_name: str) -> None:
        self.stack_name = stack_name
        self.resource_name = resource_name

    def create_resource_name(self, suffix: str) -> str:
        """Create a standardized resource name."""
        return f"{self.stack_name}-{self.resource_name}-{suffix}"

    def create_dns_label(self, prefix: str) -> str:
        """Create a standardized DNS label."""
        return f"{prefix}{self.stack_name}"