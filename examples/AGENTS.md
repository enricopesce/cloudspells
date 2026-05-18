# Example Stack Instructions

Each subdirectory is a standalone Pulumi stack. Run commands from the repository root, then change into the example directory.

```bash
source .venv/bin/activate
cd examples/<name>
pulumi preview
pulumi up
pulumi destroy
```

## Rules

- Examples demonstrate usage patterns; they are not tests.
- Keep each example minimal and focused on one concept.
- Never add logic to an example that belongs in a spell.
- `__main__.py` is the entry point for every Pulumi stack.
- Most OCI examples require `compartment_ocid`; workload examples often also require image, shape, or tenancy-specific config documented in their README.

Do not create new example directories or Pulumi config files as part of documentation sync work unless the user explicitly asks for scaffolding.
