"""CloudSpells core utilities.

Provides cloud-neutral base classes, naming helpers, the `Config` wrapper,
and well-known TCP/UDP port constants so that provider-agnostic user code
has zero direct Pulumi dependency.

Exports:
    Config
    ports: Well-known TCP/UDP port number constants (HTTP, HTTPS, SSH, …).
"""

from . import ports
from .config import Config

__all__ = ["Config", "ports"]
