#!/usr/bin/env bash
# Local quality gate — run by the pre-commit hook and callable directly.
# Mirrors the CI pipeline exactly.
# Usage: ./ci-local.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
VENV="$REPO_ROOT/.venv/bin"

echo "==> lint"
"$VENV/ruff" check packages/ tests/

echo "==> format check"
"$VENV/ruff" format --check packages/ tests/

echo "==> typecheck"
"$VENV/pyright"

echo "==> tests"
"$VENV/pytest"

echo "==> quality gate passed"
