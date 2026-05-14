"""Regression tests for CS-008 resource name construction."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from cloudspells.providers.oci._naming import ordinal_suffix

REPO_ROOT = Path(__file__).resolve().parents[1]
OCI_PROVIDER_DIR = REPO_ROOT / "packages/cloudspells-oci/src/cloudspells/providers/oci"


def test_create_resource_name_suffixes_are_static_or_helpers() -> None:
    """Require CS-008-safe suffix construction in OCI provider spells."""
    violations: list[str] = []

    for path in sorted(OCI_PROVIDER_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
        visitor = _ResourceNameVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    assert not violations, "CS-008 resource name violations:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, "vol-1"),
        (1, "vol-2"),
    ],
)
def test_ordinal_suffix_returns_one_based_suffix(index: int, expected: str) -> None:
    """Return a stable one-based suffix for zero-based indexes."""
    assert ordinal_suffix("vol", index) == expected


def test_ordinal_suffix_rejects_negative_index() -> None:
    """Reject negative indexes because suffix ordinals are one-based."""
    with pytest.raises(ValueError, match="non-negative"):
        ordinal_suffix("vol", -1)


class _ResourceNameVisitor(ast.NodeVisitor):
    """Collect CS-008 naming violations from a provider module AST."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        """Inspect resource naming calls before visiting their children."""
        call_name = _call_name(node.func)
        if call_name == "create_resource_name":
            suffix_arg = _first_argument(node, "suffix")
            if suffix_arg is not None:
                reason = _create_resource_name_violation(suffix_arg)
                if reason is not None:
                    self._add_violation(suffix_arg, f"create_resource_name() {reason}")

        if call_name == "ordinal_suffix":
            prefix_arg = _first_argument(node, "prefix")
            if not _is_string_literal(prefix_arg):
                self._add_violation(node, "ordinal_suffix() first argument must be a string literal")

        self.generic_visit(node)

    def _add_violation(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 0)
        path = self._path.relative_to(REPO_ROOT)
        self.violations.append(f"{path}:{line}: {message}")


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _first_argument(node: ast.Call, keyword_name: str) -> ast.expr | None:
    if node.args:
        return node.args[0]

    for keyword in node.keywords:
        if keyword.arg == keyword_name:
            return keyword.value

    return None


def _create_resource_name_violation(node: ast.expr) -> str | None:
    if isinstance(node, ast.JoinedStr):
        return "must not receive an inline f-string"

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            return "must not receive string concatenation"
        if isinstance(node.op, ast.Mod):
            return "must not receive percent-formatting"

    if _is_format_call(node):
        return "must not receive a .format() call"

    return None


def _is_format_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"


def _is_string_literal(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)
