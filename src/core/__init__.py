"""CloudBlocks core utilities.

Provides cloud-neutral base classes, naming helpers, and the `Config` wrapper
so that provider-agnostic user code has zero direct Pulumi dependency.

Exports:
    Config
"""

from .config import Config

__all__ = ["Config"]
