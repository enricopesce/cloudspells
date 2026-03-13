"""pytest configuration for OCI provider tests.

Sets up Pulumi mocks at module load time — before any test file imports
OCI provider modules.  New OCI provider tests in this directory inherit
this setup automatically via pytest's conftest discovery.

Usage:
    Place new OCI provider tests under ``tests/providers/oci/``.  No
    per-file ``set_mocks()`` call is needed; this conftest handles it.
"""

import os
import sys

# Ensure src/ is on the path so provider modules resolve correctly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from tests.mocks import set_mocks

set_mocks()
