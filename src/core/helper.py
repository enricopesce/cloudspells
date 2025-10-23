from random_word import RandomWords
import re
import ipaddress
from typing import List, Dict, Any, Union


class Helper:
    """Helper class providing utility methods for resource management."""

    def get_random_word(self) -> str:
        """Get a random word using the RandomWords library.

        Returns:
            A random word string.
        """
        r = RandomWords()
        return r.get_random_word()

    # def format_version(self, input_string: str) -> str:
    #     version_number = input_string.lstrip("v")
    #     formatted_version = re.sub(r"\.", r"\\.", version_number)
    #     return formatted_version

    # def get_oke_image(self, source: List[Dict[str, Any]], shape: str, kubernetes_version: str) -> str:
    #     version = self.format_version(kubernetes_version)
    #     if re.match("^VM\.Standard\.A\d+\.Flex", shape):
    #         pattern = f"(Oracle-Linux).*?(aarch64).*?({version})"
    #     elif re.match(".*GPU.*", shape):
    #         pattern = f"(Oracle-Linux).*?(GPU).*?({version})"
    #     else:
    #         pattern = f"(Oracle-Linux)-(?!.*?(?:GPU|aarch64)).*?({version})"
    #     return list(filter(lambda x: re.search(pattern, x["source_name"]), source))[0][
    #         "image_id"
    #     ]

    def get_ads(self, ads: List[Dict[str, Any]], net: str) -> List[Dict[str, str]]:
        """Convert availability domain data into placement configuration format.

        Args:
            ads: List of availability domain dictionaries containing 'name' key.
            net: Network/subnet identifier string.

        Returns:
            List of dictionaries with 'availability_domain' and 'subnet_id' keys.
        """
        z: List[Dict[str, str]] = []
        for ad in ads:
            z.append({"availability_domain": str(
                ad["name"]), "subnet_id": net})
        return z

    def calculate_subnets(self, cidr: str, num_subnets: int) -> List[str]:
        """Calculate subnet CIDR blocks from a supernet.

        Args:
            cidr: The supernet CIDR block string (e.g., "10.0.0.0/16").
            num_subnets: The number of subnets to create.

        Returns:
            List of subnet CIDR block strings.
        """
        supernet: Union[ipaddress.IPv4Network, ipaddress.IPv6Network] = ipaddress.ip_network(cidr)
        new_prefix_length: int = supernet.prefixlen
        while (2 ** (new_prefix_length - supernet.prefixlen)) < num_subnets:
            new_prefix_length += 1
        subnets: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = list(
            supernet.subnets(new_prefix=new_prefix_length)
        )
        subnet_strings: List[str] = [str(subnet) for subnet in subnets[:num_subnets]]
        return subnet_strings