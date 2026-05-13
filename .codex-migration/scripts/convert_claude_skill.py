#!/usr/bin/env python3
"""Copy a Claude skill into the Codex repo-skill layout as a draft."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path.cwd()


def main() -> int:
    """Copy one skill tree into `.agents/skills` under the draft output directory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", help="Skill directory name, for example `new-spell`")
    parser.add_argument("--source-root", default=".claude/skills", help="Claude skills root")
    parser.add_argument(
        "--output-root",
        default=".codex-migration/generated/.agents/skills",
        help="Draft Codex skills root",
    )
    args = parser.parse_args()

    source = ROOT / args.source_root / args.skill
    output = ROOT / args.output_root / args.skill
    if not (source / "SKILL.md").exists():
        raise SystemExit(f"Missing source skill: {source / 'SKILL.md'}")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output)
    print(output.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
