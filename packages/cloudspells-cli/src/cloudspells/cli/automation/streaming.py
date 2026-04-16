"""Rich streaming callback for Pulumi Automation API operations.

Provides `make_on_output`, which wraps a Rich `Console` in the callback
signature expected by `stack.up(on_output=...)` and `stack.preview(...)`.
"""

__all__ = ["make_on_output"]

from collections.abc import Callable

from rich.console import Console


def make_on_output(console: Console) -> Callable[[str], None]:
    """Create an `on_output` callback that streams Pulumi output via Rich.

    Args:
        console: Rich `Console` instance to write each message line to.

    Returns:
        Callback function compatible with `stack.up(on_output=...)`,
        `stack.preview(on_output=...)`, and `stack.destroy(on_output=...)`.
        Strips trailing whitespace before printing to avoid double newlines.
    """

    def _cb(msg: str) -> None:
        console.print(msg.rstrip(), highlight=False, markup=False)

    return _cb
