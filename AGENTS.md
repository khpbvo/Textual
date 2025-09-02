# AGENTS Guidelines

These guidelines standardize how we build, lint, type-check, and test agents in this repository. They are mandatory for all Python code and all work that touches the OpenAI Agents SDK.

## Core Rules (Non-Negotiable)

- Model: ALWAYS use `gpt-5` as the model anywhere a model is specified.
- SDK Compliance: Code MUST adhere to the OpenAI Agents SDK documentation located in `Docs/`. When the docs and code disagree, update the code or propose a docs change before merging.
- Style: Enforce PEP 8 consistently. Use `ruff` for linting and formatting.
- Types: Enforce static typing. Use `pyright` for type checking.
- Tests: ALWAYS write and run tests with `pytest` for any changes. No merges without green tests.
- CI/Local parity: The same `ruff`, `pyright`, and `pytest` commands run locally MUST pass in CI.

## Quick Commands

Run these from the repository root before committing or opening a PR:

```bash
# Format code (idempotent; safe to run anytime)
ruff format .

# Lint for PEP 8 and other issues
ruff check .

# Type check (strict where feasible)
pyright

# Run tests
pytest -q
```

All four commands MUST pass. If any fail, fix issues before pushing.

## OpenAI Agents SDK Compliance

- Source of truth: `Docs/` contains the project’s local OpenAI Agents SDK documentation. Implementations, examples, and public interfaces MUST match those docs.
- Breaking changes: If you need to deviate from `Docs/`, propose and land a docs update in the same PR. Reviewers should reject PRs that change behavior without docs alignment.
- Examples and snippets: When adding examples, keep them minimal and consistent with the patterns recommended in `Docs/`.
- Versioning: If the SDK doc versioning is used in `Docs/`, be explicit about which version your change targets and update references accordingly.

## Model Policy

- Always set the model to `"gpt-5"` whenever specifying a model in code, configuration, or examples.
- Do not parameterize or override the model unless a test explicitly validates `gpt-5` handling; the default and deployed value remains `gpt-5`.

Examples (illustrative only; follow the exact API surface documented in `Docs/`):

```python
# Wherever a model is specified, it must be gpt-5
agent = SomeAgentsSDKClass(..., model="gpt-5")
```

## Linting & Style (PEP 8 via Ruff)

- Use `ruff` to enforce style and common correctness rules.
- Prefer auto-fixes when safe: run `ruff check .` and then apply targeted fixes.
- Keep imports ordered and clean; remove unused code.
- Use `ruff format .` to keep formatting consistent across contributors.

Optional baseline configuration (if adjusting repo settings):

```toml
# pyproject.toml (excerpt)
[tool.ruff]
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]  # PEP 8 errors/warnings + import rules
ignore = []

[tool.ruff.format]
quote-style = "double"
```

## Type Checking (Pyright)

- Run `pyright` locally and in CI. Fix all reported errors and warnings or justify with narrow `# type: ignore[...]` plus rationale.
- Prefer explicit types for public APIs, function boundaries, and complex structures. Use `TypedDict`, `Protocol`, or `dataclass` where appropriate.
- Avoid `Any` unless strictly necessary and documented.

Optional baseline configuration (if adjusting repo settings):

```json
// pyrightconfig.json (excerpt)
{
  "typeCheckingMode": "strict",
  "venvPath": ".",
  "venv": ".venv",
  "reportMissingTypeStubs": false
}
```

## Testing (Pytest)

- Write unit tests for all new code and any regressions. Favor small, focused tests.
- Name tests `test_*.py` and place alongside code or under `tests/`.
- Keep tests deterministic; avoid network and time flakiness.
- Run `pytest -q` locally before pushing. CI MUST run the same.
- If adding new SDK surfaces or behaviors, include example-backed tests that mirror `Docs/`.

Suggested minimal conventions:

- Use fixtures for setup/teardown.
- Assert behavior, not implementation details.
- Prefer parametrization over loops.

## Required Local Workflow

1) Update code in alignment with `Docs/` and set all models to `gpt-5`.
2) Format: `ruff format .`
3) Lint: `ruff check .` and fix findings.
4) Type check: `pyright` and fix findings.
5) Test: `pytest -q` and ensure all tests pass.
6) Push/PR only after all checks pass.

## PR Review Checklist

- Model is `gpt-5` everywhere a model is specified.
- Code matches `Docs/` for all relevant SDK surfaces.
- `ruff check .` passes with no new violations; code is formatted.
- `pyright` passes with no unaddressed errors.
- `pytest` is green with adequate test coverage for changes.
- New examples and README snippets follow `Docs/` patterns and use `gpt-5`.

## Optional CI Snippet (reference)

If/when CI is configured, ensure it runs the exact commands below. Adjust paths as needed.

```yaml
name: agents-ci
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -U pip
      - run: pip install -r requirements.txt
      - run: pip install ruff pyright pytest
      - run: ruff format --check .
      - run: ruff check .
      - run: pyright
      - run: pytest -q
```

## Notes

- Prefer small, incremental PRs that are easy to review.
- If you must temporarily skip a test, include an issue link and remove the skip before merging.
- Do not merge any PR that fails `ruff`, `pyright`, or `pytest`.

