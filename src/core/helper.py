"""Cloud-neutral utility helpers for OCIBlocks resource management.

Provides :class:`Helper`, a stateless utility class whose methods cover
two cloud-neutral areas:

* **Subnet CIDR calculation** – splitting a supernet CIDR into *n* equal
  sub-networks.
* **SSH key generation** – creating RSA 4096-bit key pairs on the fly
  using the system ``ssh-keygen`` binary.

OCI-specific helpers (image resolution and availability-domain mapping)
live in :mod:`providers.oci.helper`.
"""

import ipaddress
import os
import subprocess
import tempfile
from typing import List, Union

from random_word import RandomWords


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
                    "-t",
                    "rsa",
                    "-b",
                    "4096",
                    "-f",
                    key_path,
                    "-N",
                    "",
                    "-C",
                    f"ociblocks-{stack_name}-{resource_name}",
                ],
                check=True,
                capture_output=True,
            )
            with open(f"{key_path}.pub") as f:
                public_key = f.read().strip()
            with open(key_path) as f:
                private_key = f.read()
        return public_key, private_key

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
