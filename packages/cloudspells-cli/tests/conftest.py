"""Shared test fixtures for the CloudSpells CLI test suite."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """CliRunner for invoking CLI commands in isolation."""
    return CliRunner()


@pytest.fixture
def mock_stack() -> MagicMock:
    """Mock Pulumi Stack with pre-configured return values for all operations."""
    mock = MagicMock()
    mock.up.return_value = MagicMock(
        summary=MagicMock(result="succeeded", resource_changes={"+": 3}),
        outputs={},
    )
    mock.preview.return_value = MagicMock(change_summary={"+": 3})
    mock.outputs.return_value = {
        "endpoint": MagicMock(value="https://example.com", secret=False),
        "vcn_id": MagicMock(value="ocid1.vcn.oc1..", secret=False),
    }
    mock.destroy.return_value = MagicMock(
        summary=MagicMock(result="succeeded", resource_changes={"-": 3}),
    )
    mock.workspace = MagicMock()
    mock.workspace.list_plugins.return_value = []
    return mock


@pytest.fixture
def stack_dir(tmp_path: Path) -> Path:
    """Temporary directory with a minimal Pulumi.yaml present."""
    (tmp_path / "Pulumi.yaml").write_text("name: test\nruntime:\n  name: python\n")
    return tmp_path
