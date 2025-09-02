## Contributing

Thanks for your interest in contributing! This project aims to be a clean example of a Textual-based IDE wired to the OpenAI Agents SDK.

### Development Setup

- Python 3.11+
- Create a venv (`python -m venv venv`; `source venv/bin/activate`)
- `pip install -U pip && pip install -r requirements.txt`
- Set `OPENAI_API_KEY` in your environment for agent features.

### Checks to Run Locally

- `ruff format .` (format)
- `ruff check .` (lint)
- `pyright` (types)
- `pytest -q` (tests)

CI runs the same steps on PRs.

### Pull Requests

- Keep changes focused; avoid unrelated refactors.
- Update docs (README/AGENTS.md) if behavior changes.
- Add tests for fixes/features when possible.

### Style & Conventions

- PEP 8 via ruff (formatter + linter).
- Type annotations; prefer `TypedDict`, `Protocol`, or `dataclass` for structured data.
- Follow the OpenAI Agents SDK docs in `Docs/` and keep examples consistent.

### License

Please confirm the project license before submitting non-trivial contributions.

