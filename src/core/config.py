"""Pulumi configuration wrapper for CloudBlocks.

Provides `Config`, a thin composition wrapper around `pulumi.Config` that
exposes the methods needed by CloudBlocks stacks without requiring user code
to import Pulumi directly.

Exports:
    Config
"""

from __future__ import annotations

import pulumi


class Config:
    """Thin wrapper around `pulumi.Config` for stack configuration.

    Composes (not inherits) `pulumi.Config` so that user-facing stacks have
    zero direct Pulumi dependency while retaining full type safety.

    Attributes:
        _config: The underlying `pulumi.Config` instance.

    Example:
        ```python
        from providers.oci import Config

        config = Config()
        compartment_id = config.require("compartment_ocid")
        max_nodes = config.require_int("max_nodes")
        ```
    """

    def __init__(self, name: str | None = None) -> None:
        """Create a Config for the given package name.

        Args:
            name: Optional package/namespace name passed to `pulumi.Config`.
                Defaults to the current project name when `None`.
        """
        self._config: pulumi.Config = pulumi.Config(name)

    # ------------------------------------------------------------------
    # Required reads (raise if key is missing)
    # ------------------------------------------------------------------

    def require(self, key: str) -> str:
        """Return a required configuration value as a string.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The string value for `key`.

        Raises:
            pulumi.ConfigMissingError: If `key` is not set in the stack config.

        Example:
            ```python
            compartment_id = config.require("compartment_ocid")
            ```
        """
        return self._config.require(key)

    def require_int(self, key: str) -> int:
        """Return a required configuration value as an integer.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The integer value for `key`.

        Raises:
            pulumi.ConfigMissingError: If `key` is not set.
            pulumi.ConfigTypeError: If the value cannot be parsed as an integer.

        Example:
            ```python
            min_nodes = config.require_int("min_nodes")
            ```
        """
        return self._config.require_int(key)

    def require_float(self, key: str) -> float:
        """Return a required configuration value as a float.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The float value for `key`.

        Raises:
            pulumi.ConfigMissingError: If `key` is not set.
            pulumi.ConfigTypeError: If the value cannot be parsed as a float.

        Example:
            ```python
            ocpus = config.require_float("oke_ocpus")
            ```
        """
        return self._config.require_float(key)

    def require_bool(self, key: str) -> bool:
        """Return a required configuration value as a boolean.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The boolean value for `key`.

        Raises:
            pulumi.ConfigMissingError: If `key` is not set.
            pulumi.ConfigTypeError: If the value cannot be parsed as a boolean.

        Example:
            ```python
            enable_logging = config.require_bool("enable_logging")
            ```
        """
        return self._config.require_bool(key)

    def require_secret(self, key: str) -> pulumi.Output[str]:
        """Return a required secret configuration value as a `pulumi.Output`.

        The value is marked as secret so Pulumi redacts it in logs and state.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            A `pulumi.Output[str]` wrapping the secret value.

        Raises:
            pulumi.ConfigMissingError: If `key` is not set.

        Example:
            ```python
            db_password = config.require_secret("db_password")
            ```
        """
        return self._config.require_secret(key)

    # ------------------------------------------------------------------
    # Optional reads (return None if key is missing)
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        """Return an optional configuration value as a string.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The string value for `key`, or `None` if not set.

        Example:
            ```python
            ssh_key = config.get("ssh_key")
            ```
        """
        return self._config.get(key)

    def get_int(self, key: str) -> int | None:
        """Return an optional configuration value as an integer.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The integer value for `key`, or `None` if not set.

        Raises:
            pulumi.ConfigTypeError: If the value is present but cannot be
                parsed as an integer.

        Example:
            ```python
            app_port = config.get_int("app_port") or 8080
            ```
        """
        return self._config.get_int(key)

    def get_float(self, key: str) -> float | None:
        """Return an optional configuration value as a float.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The float value for `key`, or `None` if not set.

        Raises:
            pulumi.ConfigTypeError: If the value is present but cannot be
                parsed as a float.

        Example:
            ```python
            memory_gbs = config.get_float("memory_in_gbs") or 16.0
            ```
        """
        return self._config.get_float(key)

    def get_bool(self, key: str) -> bool | None:
        """Return an optional configuration value as a boolean.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            The boolean value for `key`, or `None` if not set.

        Raises:
            pulumi.ConfigTypeError: If the value is present but cannot be
                parsed as a boolean.

        Example:
            ```python
            debug = config.get_bool("debug") or False
            ```
        """
        return self._config.get_bool(key)

    def get_secret(self, key: str) -> pulumi.Output[str] | None:
        """Return an optional secret configuration value as a `pulumi.Output`.

        The value is marked as secret so Pulumi redacts it in logs and state.

        Args:
            key: Configuration key (without namespace prefix).

        Returns:
            A `pulumi.Output[str]` wrapping the secret value, or `None` if
            not set.

        Example:
            ```python
            api_token = config.get_secret("api_token")
            ```
        """
        return self._config.get_secret(key)
