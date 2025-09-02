# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

## [Unreleased]
- Expand ruff/pyright coverage beyond core modules
- Optional: add stop/cancel button for streaming
- Optional: collapsible tool-output bubbles

## [1.0.0] - 2025-09-02
### Added
- Streaming AI assistant with chat-style UI (user/assistant/system bubbles)
- System bubbles for tool calls and handoffs during streaming
- Resizable panel gutters with reliable mouse capture
- Diff review flow for AI-suggested code changes
- Repo hygiene: .gitignore, CI (ruff/pyright/pytest), README, CONTRIBUTING
- Tooling configs: ruff/black, pyright
- License: Apache-2.0

### Fixed
- OpenAI client compatibility shim for Agents SDK hosted tool filters
- Guardrail stringify fallback to avoid ItemHelpers dependency
- CSS fixes for Textual (removed unsupported properties, wrapped long content)

