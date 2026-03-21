# Docstring Format Rules

All docstrings use **pure Markdown** only — the only syntax that renders correctly in both VS Code (Pylance hover) and mkdocstrings.

## Syntax Reference

| Use | Avoid |
|-----|-------|
| `` `value` `` — inline code | `` ``value`` `` — RST double-backtick |
| Fenced code block (` ``` `) | `::` + indented block — RST code block |
| Plain prose | `*italic*` for RST emphasis |

---

## Required Sections by Symbol Type

### Module docstring

```
One-sentence description of what this module provides.

Exports:
    ClassName: Short description.
    function_name: Short description.
```

### Class docstring

```
One-sentence description of what this class represents or encapsulates.

Longer paragraph if the class has non-obvious behaviour (lazy init, builder pattern, etc.).

Attributes:
    attr_name: Type and meaning.

Example:
    ```python
    obj = ClassName("name", compartment_id="ocid1.compartment.oc1..example")
    ```
```

### `__init__` docstring (separate from the class docstring)

```
Deploy/create description — what resources are created or what state is set up.

Args:
    param_name: Type. What it controls. Valid values or range if constrained.
        Defaults to `value` which means X.

Raises:
    ValueError: When and why.

Example:
    ```python
    instance = ClassName(
        "name",
        compartment_id="ocid1.compartment.oc1..example",
        vcn=vcn,
    )
    ```
```

### Public method docstring

```
One-sentence imperative description (e.g. "Register an inbound rule...").

Longer paragraph only if the method has non-obvious side-effects or ordering constraints.

Args:
    param_name: Type. What it controls.

Returns:
    Type: What is returned and when it is useful.

Raises:
    ValueError: When and why.
```

### Private helper docstring

One line only — private helpers are not rendered by mkdocstrings.

---

## Writing Guidance

- **Summaries**: imperative for methods (`"Register…"`), noun phrase for classes (`"A 4-tier OCI VCN…"`).
- **Args**: describe semantic meaning, not just the type. If a parameter accepts an enum or fixed set of strings, list them.
- **Defaults**: always say what the default *does*, not just what it *is*. "Defaults to `True`, which enables CPU-based autoscaling." — not "Defaults to `True`."
- **Cross-references**: mention related classes by name (e.g. "Pass the `Vcn` or `VcnRef` returned by…").
- **Examples**: use `"ocid1.compartment.oc1..example"` as the placeholder OCID. Keep examples to the minimum that demonstrates the primary use case. Use multi-line keyword form for more than 2 args.

---

## Source Paths (CloudSpells)

```
packages/cloudspells-core/src/cloudspells/
packages/cloudspells-oci/src/cloudspells/providers/oci/
```

For each file extract:
- Module docstring
- Every public class: summary, `Attributes:`, `Example:`
- Every `__init__`: `Args:` (each parameter with type, valid values, default behaviour), `Raises:`, `Example:`
- Every public method: summary, `Args:`, `Returns:`, `Raises:`
- Private helpers: one-line docstring only
