"""Private naming helpers for OCI provider spells."""

from __future__ import annotations


def ordinal_suffix(prefix: str, index: int) -> str:
    """Create a one-based ordinal suffix from a zero-based index.

    Args:
        prefix: CloudSpells-owned static suffix prefix to place before the
            ordinal.
        index: Zero-based index to convert into a one-based ordinal.

    Returns:
        The prefix and one-based ordinal joined by a hyphen.

    Raises:
        ValueError: If `index` is negative.
    """
    if index < 0:
        raise ValueError("ordinal suffix index must be non-negative")

    return "-".join((prefix, str(index + 1)))
