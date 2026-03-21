---
name: docs-auditor
description: Audits and rewrites hand-written Markdown documentation pages so they are accurate, well-structured, and genuinely useful. Use when the user asks to "audit docs", "fix documentation", "rewrite docs pages", "check the docs", "update markdown pages", or "fix the docs for". Works on any project following the Diátaxis framework (tutorials, how-to, concepts, reference). Designed for CloudSpells docs/ but applies broadly.
metadata:
  author: CloudSpells
  version: 1.0.0
  category: documentation
---

# Docs Auditor

A senior-technical-writer workflow for auditing and rewriting hand-written Markdown pages so every page is accurate, well-structured, and genuinely useful.

> **Source of truth**: The Python implementation. Pages must describe what the code *actually does*.
> **Scope**: Fix and improve existing pages only — do not create new files.
> **Structure**: Do not restructure the Diátaxis sections — only improve content within each.

---

## Working Protocol

**1. Resolve scope, then stop.**

- **Single file given** → go straight to the audit for that file. No plan needed.
- **Directory given** → list every `.md` file in scope as a Markdown checklist, one file per item. Stop and wait for explicit approval ("go ahead", "proceed", or similar) before touching anything.
- **Scope unclear** → ask for a specific file or directory *before* doing anything else. Do not assume full-repo scope.

**2. One file at a time.**
Audit and rewrite one file completely before moving to the next. After finishing a file, re-print the checklist with progress and stop — do not start the next file until the user says "next", "proceed", or similar.

**3. No lazy editing.**
Every rewrite must be complete and ready to paste — no `<!-- rest unchanged -->`, no elided sections.

**4. Track progress.**
After each file, re-print the full checklist with `[x]` on finished items and `[ ]` on remaining ones.

---

## Step 1 — Audit

Read every file under `docs/` (excluding `docs/api/`). Classify each page:

| Status | Meaning |
|--------|---------|
| **STALE** | References a class, parameter, import path, or method that no longer exists |
| **WRONG** | Describes behaviour that contradicts the actual implementation |
| **INCOMPLETE** | A required section for the page type is missing |
| **IMPRECISE** | Technically correct but vague enough to cause misconfiguration |
| **OK** | Accurate, complete, and clear |

Also check `docs/api/` for stale `:::` directive paths only (not prose).
Also check `mkdocs.yml` nav entries for paths that don't match actual files.

Present the full audit table before any edits:

```
File | Item | Status | Detail
```

Consult `references/quality-bar.md` for pass/fail criteria per page type.

---

## Step 2 — Fix API directive paths (`docs/api/`)

For each `docs/api/**/*.md` file, verify the `:::` directive uses the correct importable module path. If stale, update it. Do not change any prose.

For stale nav entries in `mkdocs.yml`, correct the file path only — do not restructure the nav.

---

## Step 3 — Fix narrative pages

For every page that is not **OK**, rewrite it following the required structure for its type. Consult `references/page-templates.md` for exact required sections and rewrite rules per page type.

---

## Step 4 — Apply writing standards

Apply to all pages. Consult `references/writing-standards.md` for the full ruleset.

Key rules:
- Lead with the answer — most important fact or instruction goes first.
- CloudSpells voice: direct, confident, no hedging.
- Code blocks: always fenced triple-backtick with language tag.
- OCID placeholders: always `ocid1.compartment.oc1..example`.
- No RST syntax anywhere.

---

## Step 5 — Summary Report

```
Files changed: N
  STALE → corrected: N
  WRONG → corrected: N
  INCOMPLETE → completed: N
  IMPRECISE → clarified: N
mkdocs.yml nav entries fixed: N
API directive paths fixed: N
Remaining gaps (not auto-fixable): <list with reason>
```

Flag anything requiring a human decision (e.g. a tutorial covering a spell whose behaviour has changed substantially).
