---
name: docstring-auditor
description: Audits and rewrites Python API docstrings so auto-generated references (via mkdocstrings) are complete, accurate, and genuinely useful. Use when the user asks to "audit docstrings", "fix docstrings", "rewrite API docs", "improve Python documentation", or "check docstrings". Works on any Python project using mkdocstrings. Designed for CloudSpells source files under cloudspells-core and cloudspells-oci packages but applies broadly.
metadata:
  author: CloudSpells
  version: 1.0.0
  category: documentation
---

# Docstring Auditor

A senior-technical-writer workflow for auditing and rewriting Python API docstrings so the auto-generated API reference is complete, accurate, and genuinely useful.

> **Source of truth**: The Python implementation. Docstrings must describe what the code *actually does*, not what it was intended to do.
> **Scope**: Fix existing public docstrings only — do not add new public symbols.

---

## Working Protocol

Follow these rules for every invocation:

**1. Resolve scope, then stop.**

- **Single file given** → go straight to the audit for that file. No plan needed.
- **Directory given** → list every `.py` file in scope as a Markdown checklist, one file per item. Stop and wait for explicit approval ("go ahead", "proceed", or similar) before touching anything.
- **Scope unclear** → ask for a specific file or directory *before* doing anything else. Do not assume full-repo scope.

**2. One file at a time.**
Audit and rewrite one file completely before moving to the next. After finishing a file, re-print the checklist with progress and stop — do not start the next file until the user says "next", "proceed", or similar.

**3. No lazy coding.**
Every docstring rewrite must be complete and ready to paste — no `# ... rest unchanged`, no elided sections. Write all of it.

**4. Track progress.**
After each file, re-print the full checklist with `[x]` on finished items and `[ ]` on remaining ones. Open with one line summarising the overall goal when the conversation is long.

---

## Step 1 — Audit

Read all source files. For each public symbol, classify its docstring:

| Status | Meaning |
|--------|---------|
| **MISSING** | No docstring at all |
| **INCOMPLETE** | One or more required sections absent |
| **STALE** | References a parameter, class, or behaviour that no longer exists |
| **WRONG** | Describes behaviour that contradicts the implementation |
| **OK** | Meets the quality bar |

Present the full audit table before making any edits:

```
File | Symbol | Status | Detail
```

### Quality bar

A docstring passes when a user who has never read the source can:

1. Understand what the class or function does from the summary alone.
2. Know exactly what to pass for every parameter, including valid values and side-effects.
3. Know what they get back and what can go wrong.
4. Copy the `Example:` block and have it work with only their OCID substituted.

A docstring **fails** if it:
- Repeats the function name in the summary (e.g. "Creates a VCN" for `class Vcn`).
- Lists a parameter without saying what values are valid or what the default implies.
- Has a section header with no content.
- Uses RST syntax (`` ``value`` ``, `::` code blocks) instead of pure Markdown.
- Has an `Example:` that imports a stale path or uses a removed parameter.

---

## Step 2 — Rewrite

For every symbol that is not **OK**, rewrite the docstring in place. See `references/format-rules.md` for exact section templates and writing guidance.

---

## Step 3 — Verify

After all rewrites:

1. Re-read each changed docstring and confirm it passes the quality bar above.
2. Check that every `Example:` import path matches the module's actual location.
3. Check that no `Example:` passes a parameter that was removed.

---

## Step 4 — Summary Report

Output a report in this exact format:

```
Files changed: N
Symbols updated: N
  MISSING → written: N
  INCOMPLETE → completed: N
  STALE → corrected: N
  WRONG → corrected: N
Remaining gaps (not auto-fixable): <list with reason>
```

Flag anything requiring a human decision (e.g. a parameter whose purpose is unclear from the implementation alone).
