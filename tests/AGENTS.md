# Pulumi tests

- Call `tests.mocks.set_mocks()` before infrastructure imports so the test uses mocked provider calls. Pytest adds package paths from `pyproject.toml`.
- Use [`mocks.py`](mocks.py) as the source of truth for OCI resource types, invoke tokens, and computed outputs. Extend the mocks when a spell reads a new computed output or relies on a new invoke result.
- Use `@pulumi.runtime.test` for Pulumi outputs, and return the output or assertion chain so the runtime waits for it. Leave the return annotation off decorated methods. Annotate ordinary test methods that return nothing with `-> None`.
- Keep OCI tests in `tests/` and CLI tests in `packages/cloudspells-cli/tests/`.

Run the full suite with `make test`. Use `--no-cov` for a focused run so repository-wide coverage does not fail a single case.

```bash
.venv/bin/pytest --no-cov tests/test_vcn.py::TestVcn::test_vcn_creates_base_resources
```
