# Page Templates

## Tutorial (`docs/tutorials/`, `docs/getting-started/`)

Required structure:

1. **What you will build** — ASCII architecture diagram in a fenced code block, then a one-line "What gets created:" summary listing resource counts.
2. **Prerequisites** — bulleted list. Every item must be actionable (not "familiarity with OCI").
3. **Numbered steps** — each step has a heading, explanation of *what* (not *why*), and a single code block. Steps must match the corresponding `examples/` directory.
4. **Stack outputs** — what `pulumi stack output` returns after a successful deploy.

### Tutorial rewrite rules

- Remove any parameters from code snippets that are not required by the current constructor.
- Add any parameters that are required but missing.
- Verify import paths (`from cloudspells.providers.oci.X import Y`).
- Step headings use title case. Code block language tags always specified (`python`, `yaml`, `bash`).

---

## How-to guide (`docs/how-to/`)

Required structure:

1. **Goal statement** — one sentence: "This guide shows you how to X."
2. **When to use this** — one short paragraph or a bullet list of scenarios.
3. **Steps** — numbered, each containing only what is necessary to achieve the goal.
4. **Complete example** — a single working code block at the end the user can copy.

### How-to rewrite rules

- Cut all background explanation — concepts go in `docs/concepts/`, not here.
- Every step must have a concrete action (not "configure the NSG" — "call `nsg.serves(target, port=443)`").

---

## Concept (`docs/concepts/`)

Required structure:

1. **The problem** — one paragraph.
2. **The solution CloudSpells applies** — one paragraph or table.
3. **Mental model** — the core insight in plain English.
4. **What this means in practice** — implications for the user, not implementation details.

### Concept rewrite rules

- No step-by-step instructions — those go in tutorials.
- No parameter lists — those go in reference.
- Every claim must be backed by the actual implementation behaviour.

---

## Reference page (`docs/reference/`)

Required structure:

1. **Summary table** — key facts at the top.
2. **Detail sections** — precise, factual, no narrative.
3. **Diagrams** — ASCII art in fenced code blocks only.

### Reference rewrite rules

- Remove any prose padding ("This section describes…", "As you can see…").
- Numbers must be exact (CIDR splits, port numbers, resource limits).
- Cross-reference related pages with Markdown links.

---

## Landing page (`docs/index.md`)

- Value proposition in 3 sentences maximum.
- Points clearly to entry paths (getting started, tutorials, reference).
- No implementation details.
