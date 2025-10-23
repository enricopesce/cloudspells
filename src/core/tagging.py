from typing import Dict, Any, Optional

class ResourceTagger:
    """Helper class for creating standardized resource tags."""

    stack_name: str
    resource_name: str

    def __init__(self, stack_name: str, resource_name: str) -> None:
        self.stack_name = stack_name
        self.resource_name = resource_name

    def create_freeform_tags(
        self,
        resource_name: str,
        resource_type: str,
        additional_tags: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Create standardized freeform tags with optional additional tags."""
        tags = {
            "Name": resource_name,
            "ResourceType": resource_type,
            "Environment": self.stack_name,
            "CreatedBy": f"{self.stack_name}-{self.resource_name}"
        }
        
        if additional_tags:
            tags.update(additional_tags)
            
        return tags

    def create_network_resource_tags(
        self,
        resource_name: str,
        resource_type: str,
        network_type: str,
        subnet_group: Optional[str] = None,
        additional_tags: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Create standardized tags for network resources."""
        tags = {
            "NetworkType": network_type
        }
        
        if subnet_group:
            tags["SubnetGroup"] = subnet_group
            
        if additional_tags:
            tags.update(additional_tags)
            
        return self.create_freeform_tags(resource_name, resource_type, tags)

    def create_gateway_tags(
        self,
        resource_name: str,
        gateway_type: str,
        additional_tags: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Create standardized tags for gateway resources."""
        tags = {
            "GatewayType": gateway_type
        }
        
        if additional_tags:
            tags.update(additional_tags)
            
        return self.create_freeform_tags(resource_name, "gateway", tags)