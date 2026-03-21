# Quality Bar

A page passes when a CloudSpells user can:

1. **Tutorials** — follow steps from a blank terminal to a running stack without hitting an error or needing to consult source code.
2. **How-to guides** — accomplish the specific goal in the title by following the guide, with no steps that require guessing.
3. **Concepts** — finish reading with a clear mental model that transfers to real usage.
4. **Reference** — look up a specific detail and get a precise, unambiguous answer.

## A page FAILS if it:

- Contains a code snippet that imports from a stale path or passes a removed parameter.
- Describes behaviour that contradicts the actual Python implementation.
- Shows a parameter the user no longer needs to pass (CloudSpells defaults it).
- Uses RST syntax or raw HTML where plain Markdown works.
- Buries the key information in preamble — the most important sentence must come first.

---

## Diátaxis Directory Map

| Directory | Type | Purpose |
|-----------|------|---------|
| `docs/tutorials/` | Tutorial | Learning-oriented. Reader follows steps, builds something real. No explanations of why — just what. |
| `docs/how-to/` | How-to | Task-oriented. Solves a specific problem the reader already has. |
| `docs/concepts/` | Concept | Understanding-oriented. Explains the why and the mental model. No step-by-step. |
| `docs/reference/` | Reference | Information-oriented. Precise, factual, no prose padding. |
| `docs/getting-started/` | Tutorial | First-run experience. Must work on a clean machine. |
| `docs/index.md` | Landing | Sells the value proposition in 3 sentences. Points to entry paths. |
| `docs/api/` | Reference | Auto-generated via mkdocstrings `:::` directives. Fix directive paths only — never rewrite prose here. |

---

## Source of Truth (CloudSpells)

Before editing any page, read the relevant Python source:

- `packages/cloudspells-core/src/cloudspells/` — core abstractions and base classes
- `packages/cloudspells-oci/src/cloudspells/providers/oci/` — OCI spell implementations
- `examples/*/` — canonical working usage for each spell

Extract for each spell:
- Constructor signature: required parameters, optional parameters, defaults
- What OCI resources get created
- What outputs are available
- Any ordering constraints (e.g. `finalize_network()`)

Cross-check every code snippet in `docs/` against the live constructor signature before editing.
