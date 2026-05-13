#!/usr/bin/env python3
"""Convert Claude agent Markdown files into draft Codex custom-agent TOML files."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path.cwd()


def toml_string(value: str) -> str:
    """Return a TOML-safe basic string."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a Markdown file into frontmatter and body."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[4:end], text[end + 5 :]


def extract_field(frontmatter: str, field: str, fallback: str) -> str:
    """Extract a simple YAML-like field from frontmatter."""
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{field}:"):
            value = line.split(":", 1)[1].strip()
            if value in {">", "|"}:
                block: list[str] = []
                for child in lines[index + 1 :]:
                    if child and not child.startswith(" "):
                        break
                    block.append(child.strip())
                return " ".join(part for part in block if part) or fallback
            return value.strip('"') or fallback
    return fallback


def sandbox_for(name: str) -> str:
    """Return the Codex sandbox mode for an agent."""
    if "review" in name or "audit" in name or "auditor" in name:
        return "read-only"
    return "workspace-write"


def convert_file(source: Path, output_dir: Path) -> Path:
    """Convert one Claude agent file to draft TOML."""
    text = source.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    name = extract_field(frontmatter, "name", source.stem)
    description = extract_field(frontmatter, "description", f"Migrated Codex subagent for {name}.")
    output = output_dir / f"{name}.toml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(
            [
                f"name = {toml_string(name)}",
                f"description = {toml_string(description)}",
                f"sandbox_mode = {toml_string(sandbox_for(name))}",
                'model_reasoning_effort = "high"',
                "",
                'developer_instructions = """',
                "Migrated from Claude agent file:",
                source.as_posix(),
                "",
                body.strip().replace('"""', '\\"\\"\\"'),
                '"""',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return output


def main() -> int:
    """Convert all Claude agent files into draft Codex TOML files."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=".claude/agents", help="Claude agent directory")
    parser.add_argument("--output", default=".codex-migration/generated/agents", help="Draft output directory")
    args = parser.parse_args()

    source_dir = ROOT / args.source
    output_dir = ROOT / args.output
    for source in sorted(source_dir.glob("*.md")):
        print(convert_file(source, output_dir).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
