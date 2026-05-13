#!/usr/bin/env python3
"""Audit Claude-related artifacts in a repository and emit JSON."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path.cwd()
SKIP_DIRS = {".git", ".venv", "__pycache__", "dist", "htmlcov"}


def rel(path: Path) -> str:
    """Return a POSIX path relative to the repository root."""
    return path.relative_to(ROOT).as_posix()


def iter_files() -> list[Path]:
    """Return all repository files except ignored implementation/cache directories."""
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def find_files(predicate) -> list[str]:
    """Return relative file paths matching a predicate."""
    return [rel(path) for path in iter_files() if predicate(path)]


def read_json(path: Path) -> dict:
    """Read JSON when present; return an error payload when parsing fails."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"_error": str(exc)}


def main() -> int:
    """Print the Claude artifact inventory."""
    claude_dir = ROOT / ".claude"
    settings = read_json(claude_dir / "settings.json")
    local_settings = read_json(claude_dir / "settings.local.json")

    inventory = {
        "claude_md": find_files(lambda path: path.name == "CLAUDE.md"),
        "agents": find_files(lambda path: ".claude/agents" in rel(path) and path.suffix == ".md"),
        "skills": find_files(lambda path: ".claude/skills" in rel(path) and path.name == "SKILL.md"),
        "rules": find_files(lambda path: ".claude/rules" in rel(path) and path.suffix == ".md"),
        "settings": find_files(lambda path: rel(path) in {".claude/settings.json", ".claude/settings.local.json"}),
        "review_reports": find_files(lambda path: ".claude/review-reports" in rel(path)),
        "worktrees_present": (claude_dir / "worktrees").exists(),
        "commands": find_files(lambda path: ".claude/commands" in rel(path)),
        "hooks": find_files(lambda path: ".claude/hooks" in rel(path) or "hook" in path.name.lower()),
        "mcp": find_files(lambda path: path.name in {".mcp.json", "mcp.json"} or "mcp" in path.name.lower()),
        "settings_summary": {
            "tracked_allow_count": len(settings.get("permissions", {}).get("allow", [])),
            "tracked_deny_count": len(settings.get("permissions", {}).get("deny", [])),
            "local_allow_count": len(local_settings.get("permissions", {}).get("allow", [])),
            "local_deny_count": len(local_settings.get("permissions", {}).get("deny", [])),
        },
    }
    print(json.dumps(inventory, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
