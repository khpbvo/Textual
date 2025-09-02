# Terminator v1 — Textual IDE with OpenAI Agents

Terminator is a terminal UI IDE built with Textual. It includes a code editor, file explorer, Git tools, an integrated terminal, and an AI assistant powered by the OpenAI Agents SDK.

- AI model: always uses `gpt-5` (config enforced in code).
- SDK compliance: adheres to the local docs in `Docs/`.
- Linting & typing: `ruff` and `pyright`.
- Tests: `pytest`.

## Quick Start

1) Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2) Install dependencies

```bash
pip install -U pip
pip install -r requirements.txt
```

3) Set your OpenAI API key

```bash
export OPENAI_API_KEY=sk-...  # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."
```

4) Run the app

```bash
python TerminatorV1_main.py
```

## Features

- Resizable three-panel layout (explorer, editor/terminal, AI assistant)
- Code editing with syntax highlighting (if `textual[syntax]` available)
- Git status, commit, push/pull, branch visualization
- Python execution and basic debugger UI
- AI assistant with streaming responses, tool/handoff progress events, and code-diff review

## Development

Formatting, linting, typing, and tests:

```bash
ruff format .
ruff check .
pyright
pytest -q
```

We recommend running these before opening a PR. CI runs the same checks.

## Project Conventions

- See `AGENTS.md` for agent guidelines (always `gpt-5`, `pytest`, `ruff`, `pyright`).
- See `Docs/` for the local OpenAI Agents SDK documentation the app adheres to.
- Do not commit virtual environments, logs, or local caches (see `.gitignore`).

## Troubleshooting

- If UI resizing doesn’t work, ensure you click the vertical gutter bar and drag horizontally.
- If streaming doesn’t appear: verify the API key is set and watch for tool/handoff bubbles indicating progress.
- For syntax highlighting, install `textual[syntax]` extras and ensure `tree-sitter-languages` is present.

## Contributing

See `CONTRIBUTING.md` for guidelines. Please open issues for bugs or improvement suggestions.

## License

Please confirm which license to use before publishing. Common choices: MIT, Apache-2.0.

