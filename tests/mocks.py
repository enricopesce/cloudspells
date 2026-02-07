"""Shared Pulumi mocks for OCI resources."""

from typing import Any
import pulumi


class OCIMocks(pulumi.runtime.Mocks):
    """Mock OCI provider calls and resource creation."""

    def new_resource(self, args: pulumi.runtime.MockResourceArgs) -> tuple[str | None, dict[Any, Any]]:
        """Mock resource creation - returns resource ID and inputs."""
        outputs = args.inputs.copy()

        # Add computed outputs based on resource type
        if args.typ == "oci:Core/vcn:Vcn":
            outputs["defaultRouteTableId"] = f"{args.name}-default-rt-id"
            outputs["defaultSecurityListId"] = f"{args.name}-default-sl-id"

        if args.typ == "oci:Core/subnet:Subnet":
            outputs["id"] = f"{args.name}-id"

        if args.typ == "oci:Core/instance:Instance":
            outputs["privateIp"] = "10.0.128.10"
            outputs["publicIp"] = None

        if args.typ == "oci:Core/volume:Volume":
            outputs["id"] = f"{args.name}-id"

        if args.typ == "oci:LoadBalancer/loadBalancer:LoadBalancer":
            outputs["ipAddressDetails"] = [
                {"ipAddress": "10.0.0.100", "isPublic": True},
            ]

        return (f"{args.name}-id", outputs)

    def call(self, args: pulumi.runtime.MockCallArgs) -> tuple[dict[Any, Any], list[tuple[str, str]]]:
        """Mock OCI provider function calls."""

        # Mock get_services (for Service Gateway)
        if args.token == "oci:Core/getServices:getServices":
            return ({
                "services": [
                    {
                        "id": "mock-all-services-id",
                        "name": "All FRA Services In Oracle Services Network",
                        "cidrBlock": "all-fra-services-in-oracle-services-network",
                    }
                ]
            }, [])

        # Mock get_images (for Compute Instance)
        if args.token == "oci:Core/getImages:getImages":
            return ({
                "images": [
                    {
                        "id": "mock-oracle-linux-8-image-id",
                        "displayName": "Oracle-Linux-8.9-2024.01.26-0",
                        "operatingSystem": "Oracle Linux",
                        "operatingSystemVersion": "8",
                    }
                ]
            }, [])

        # Mock get_availability_domains
        if args.token == "oci:Identity/getAvailabilityDomains:getAvailabilityDomains":
            return ({
                "availabilityDomains": [
                    {"name": "AD-1", "id": "mock-ad-1-id"},
                    {"name": "AD-2", "id": "mock-ad-2-id"},
                    {"name": "AD-3", "id": "mock-ad-3-id"},
                ]
            }, [])

        return ({}, [])


def set_mocks():
    """Set up Pulumi mocks for testing."""
    pulumi.runtime.set_mocks(OCIMocks(), preview=False)
