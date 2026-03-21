# Writing Standards

Apply to every page regardless of type.

## Voice and tone

- **Lead with the answer.** The most important fact or instruction goes first.
- **CloudSpells voice**: direct, confident, no hedging.
  - ✅ "The subnet is private."
  - ❌ "The subnet may be private depending on configuration."
- No preamble ("In this section, we will…"). Start with the content.

## Markdown syntax

| Use | Avoid |
|-----|-------|
| Fenced ` ``` ` with language tag | Unlabelled code blocks |
| ` `inline code` ` for values | `` ``double-backtick`` `` (RST) |
| Plain Markdown tables | Raw HTML tables |
| `---` horizontal rule | `.. note::` RST directives |

- **Code blocks**: always fenced triple-backtick with language tag (`python`, `yaml`, `bash`). Never inline code for multi-line blocks.
- **Tables**: use for comparisons and parameter lists. Avoid for sequential steps.
- **No RST**: no `::` code blocks, no `` ``double-backtick`` ``, no `.. note::` directives.

## Links

- Use relative Markdown links: `../concepts/design.md`
- Verify every link target exists before writing it.

## Code examples

- OCID placeholders: always `ocid1.compartment.oc1..example`
- Import paths must match the actual module location:
  - `from cloudspells.providers.oci.<module> import <Class>`
  - `from cloudspells.core.<module> import <Class>`
- Never pass a parameter that no longer exists in the constructor.
- Never omit a required parameter.
