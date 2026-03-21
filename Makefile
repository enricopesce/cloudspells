.DEFAULT_GOAL := check

VENV := .venv
PYTHON := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff
PYRIGHT := $(VENV)/bin/pyright
PYTEST := $(VENV)/bin/pytest

# ── Individual targets ────────────────────────────────────────────────────────

.PHONY: lint
lint:
	$(RUFF) check packages/ tests/

.PHONY: lint-fix
lint-fix:
	$(RUFF) check packages/ tests/ --fix

.PHONY: format
format:
	$(RUFF) format packages/ tests/

.PHONY: format-check
format-check:
	$(RUFF) format --check packages/ tests/

.PHONY: typecheck
typecheck:
	$(PYRIGHT)

.PHONY: test
test:
	$(PYTEST)

.PHONY: deadcode
deadcode:
	$(VENV)/bin/vulture packages/ --min-confidence 80

# ── Full quality gate (mirrors CI exactly) ───────────────────────────────────

.PHONY: check
check: lint format-check typecheck test
	@echo "Quality gate passed."
