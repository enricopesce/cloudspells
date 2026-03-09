"""Utility helpers for OCIBlocks resource management.

Provides :class:`Helper`, a stateless utility class whose methods cover
three areas:

* **Subnet CIDR calculation** – splitting a VCN supernet into *n* equal
  sub-networks.
* **SSH key generation** – creating RSA 4096-bit key pairs on the fly
  using the system ``ssh-keygen`` binary.
* **Image resolution** – looking up the latest Oracle Linux 8 image for a
  given compute shape when no explicit image OCID is supplied.
* **Availability domain mapping** – converting the OCI SDK representation
  of availability domains into the placement configuration format expected
  by the OKE node pool API.
"""

from random_word import RandomWords
import ipaddress
import os
import subprocess
import tempfile
from typing import List, Dict, Any, Union


class Helper:
    """Stateless utility methods used by OCIBlocks building blocks.

    All methods are safe to call multiple times and have no side-effects
    on instance state.  Instantiate with ``Helper()`` wherever needed.
    """

    def get_random_word(self) -> str:
        """Return a single random English word.

        Uses the ``random-word`` library internally.  Useful for generating
        unique name suffixes during testing or prototyping.

        Returns:
            A random lower-case word string (e.g. ``"banana"``).
        """
        r = RandomWords()
        return r.get_random_word()

    def get_ads(self, ads: List[Dict[str, Any]], net: str) -> List[Dict[str, str]]:
        """Convert availability domain data into placement configuration dicts.

        Transforms the raw list returned by
        ``oci.identity.get_availability_domains()`` into the format expected
        by the OKE node pool ``placement_configs`` argument.

        Args:
            ads: List of availability domain dictionaries, each containing at
                least a ``"name"`` key (e.g. ``[{"name": "AD-1"}, ...]``).
            net: Subnet OCID to assign to every placement configuration entry.

        Returns:
            List of ``{"availability_domain": str, "subnet_id": str}`` dicts,
            one entry per availability domain.

        Example:
            >>> h = Helper()
            >>> ads = [{"name": "Uocm:PHX-AD-1"}, {"name": "Uocm:PHX-AD-2"}]
            >>> h.get_ads(ads, "ocid1.subnet.oc1...")
            [{'availability_domain': 'Uocm:PHX-AD-1', 'subnet_id': 'ocid1.subnet.oc1...'},
             {'availability_domain': 'Uocm:PHX-AD-2', 'subnet_id': 'ocid1.subnet.oc1...'}]
        """
        result: List[Dict[str, str]] = []
        for ad in ads:
            result.append({"availability_domain": str(ad["name"]), "subnet_id": net})
        return result

    def generate_ssh_key_pair(self, stack_name: str, resource_name: str) -> tuple[str, str]:
        """Generate an RSA 4096-bit SSH key pair using ``ssh-keygen``.

        The key pair is created in a temporary directory that is
        automatically cleaned up after the keys have been read.  The key
        comment is set to ``"ociblocks-{stack_name}-{resource_name}"`` for
        traceability.

        Args:
            stack_name: Stack identifier embedded in the key comment.
            resource_name: Resource name embedded in the key comment.

        Returns:
            A ``(public_key, private_key)`` tuple where both elements are
            plain strings.  *public_key* is the single-line OpenSSH public
            key; *private_key* is the full PEM-encoded private key.

        Raises:
            subprocess.CalledProcessError: If ``ssh-keygen`` exits with a
                non-zero status.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "id_rsa")
            subprocess.run(
                [
                    "ssh-keygen",
                    "-t", "rsa",
                    "-b", "4096",
                    "-f", key_path,
                    "-N", "",
                    "-C", f"ociblocks-{stack_name}-{resource_name}",
                ],
                check=True,
                capture_output=True,
            )
            with open(f"{key_path}.pub", "r") as f:
                public_key = f.read().strip()
            with open(key_path, "r") as f:
                private_key = f.read()
        return public_key, private_key

    # Maps friendly OS names to (operating_system, operating_system_version)
    # as expected by the OCI images API.
    _OS_MAP: dict[str, tuple[str, str]] = {
        "oracle": ("Oracle Linux", "8"),
        "ubuntu": ("Canonical Ubuntu", "22.04"),
        "windows": ("Windows", "Server 2022 Standard"),
    }

    def resolve_image_id(
        self,
        compartment_id: str,
        shape: str,
        image_id: str | None = None,
        os_name: str = "oracle",
    ) -> str:
        """Resolve the compute image OCID to use for an instance.

        When *image_id* is provided it is returned immediately.  Otherwise
        the method queries the OCI API for the most recently created image
        matching *os_name* that is compatible with *shape*.

        Args:
            compartment_id: OCID of the compartment to search for images.
            shape: Compute shape name used to filter compatible images
                (e.g. ``"VM.Standard.E4.Flex"``).
            image_id: Optional explicit image OCID.  When provided, the OCI
                API is not queried and this value is returned as-is.
            os_name: Friendly OS identifier.  Supported values:

                * ``"oracle"`` – Oracle Linux 8 (default)
                * ``"ubuntu"`` – Canonical Ubuntu 22.04
                * ``"windows"`` – Windows Server 2022 Standard

        Returns:
            The image OCID string to use for instance creation.

        Raises:
            ValueError: If *os_name* is not one of the supported values.
        """
        if image_id is not None:
            return image_id
        if os_name not in self._OS_MAP:
            supported = ", ".join(f'"{k}"' for k in self._OS_MAP)
            raise ValueError(f"Unsupported os_name {os_name!r}. Supported values: {supported}")
        operating_system, operating_system_version = self._OS_MAP[os_name]
        import pulumi_oci as oci
        images = oci.core.get_images(
            compartment_id=compartment_id,
            operating_system=operating_system,
            operating_system_version=operating_system_version,
            shape=shape,
            sort_by="TIMECREATED",
            sort_order="DESC",
        )
        return images.images[0].id

    def calculate_subnets(self, cidr: str, num_subnets: int) -> List[str]:
        """Split a supernet CIDR into *n* equal sub-networks.

        The method increases the prefix length of *cidr* by the minimum
        number of bits required to accommodate at least *num_subnets* subnets,
        then returns the first *num_subnets* of them.

        Args:
            cidr: The supernet CIDR block string (e.g. ``"10.0.0.0/16"``).
            num_subnets: The number of subnets to return.

        Returns:
            List of *num_subnets* CIDR block strings in address order
            (e.g. ``["10.0.0.0/17", "10.0.128.0/17"]`` for
            ``calculate_subnets("10.0.0.0/16", 2)``).

        Example:
            >>> h = Helper()
            >>> h.calculate_subnets("10.0.0.0/16", 2)
            ['10.0.0.0/17', '10.0.128.0/17']
        """
        supernet: Union[ipaddress.IPv4Network, ipaddress.IPv6Network] = ipaddress.ip_network(cidr)
        new_prefix_length: int = supernet.prefixlen
        while (2 ** (new_prefix_length - supernet.prefixlen)) < num_subnets:
            new_prefix_length += 1
        subnets: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = list(
            supernet.subnets(new_prefix=new_prefix_length)
        )
        return [str(subnet) for subnet in subnets[:num_subnets]]
