#!/usr/bin/env python3
"""Validate the CloudSpells Codex migration artifacts."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path.cwd()
RULE_RE = re.compile(r'^prefix_rule\(pattern=\[[^\]]+\], decision="(allow|forbidden|ask)"(?:, justification="[^"]*")?\)$')


def rel(path: Path) -> str:
    """Return a POSIX path relative to the repository root."""
    return path.relative_to(ROOT).as_posix()


def check_file(path: Path, failures: list[str]) -> None:
    """Record a failure if a required file is missing."""
    if not path.exists():
        failures.append(f"missing required file: {rel(path)}")


def check_toml(path: Path, failures: list[str]) -> None:
    """Validate TOML syntax."""
    try:
        tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - validator should report any parser failure
        failures.append(f"invalid TOML in {rel(path)}: {exc}")


def check_skill(path: Path, failures: list[str]) -> None:
    """Validate minimal Codex skill frontmatter."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        failures.append(f"missing frontmatter in {rel(path)}")
        return
    end = text.find("\n---\n", 4)
    if end == -1:
        failures.append(f"unterminated frontmatter in {rel(path)}")
        return
    frontmatter = text[4:end]
    for field in ("name:", "description:"):
        if field not in frontmatter:
            failures.append(f"missing `{field}` in {rel(path)}")


def check_rules(path: Path, failures: list[str]) -> None:
    """Validate basic `.rules` line shape."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not RULE_RE.match(stripped):
            failures.append(f"invalid rule syntax at {rel(path)}:{number}: {stripped}")


def tracked(path: str) -> bool:
    """Return whether git tracks a path."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    """Run all validation checks."""
    failures: list[str] = []
    required = [
        ROOT / "AGENTS.md",
        ROOT / "examples/AGENTS.md",
        ROOT / "tests/AGENTS.md",
        ROOT / "packages/AGENTS.md",
        ROOT / ".agents/skills/new-spell/SKILL.md",
        ROOT / ".codex/config.toml",
        ROOT / ".codex/rules/default.rules",
    ]
    for path in required:
        check_file(path, failures)

    for path in [ROOT / ".codex/config.toml", *sorted((ROOT / ".codex/agents").glob("*.toml"))]:
        check_toml(path, failures)

    check_skill(ROOT / ".agents/skills/new-spell/SKILL.md", failures)
    check_rules(ROOT / ".codex/rules/default.rules", failures)

    if tracked(".claude/settings.local.json"):
        failures.append(".claude/settings.local.json is tracked; keep machine-local Claude settings untracked")

    summary = {
        "ok": not failures,
        "failures": failures,
        "agents": [rel(path) for path in sorted((ROOT / ".codex/agents").glob("*.toml"))],
        "skills": [rel(path) for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
