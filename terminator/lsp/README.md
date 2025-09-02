# Language Server Protocol (LSP) Integration

This module provides LSP integration for the Terminator IDE, allowing for language-aware features like code completion, hover information, go-to-definition, and more.

## Features

- **Code Completion**: Intelligent code suggestions based on the file's language and context
- **Hover Information**: Display documentation and type information when hovering over symbols
- **Go to Definition**: Jump to the definition of a symbol
- **Find References**: Find all references to a symbol across the codebase
- **Diagnostics**: Display errors, warnings, and other issues as you type
- **Code Formatting**: Format code using language-specific formatters

## Supported Languages

The LSP integration supports the following languages out of the box:

- Python (via pylsp)
- TypeScript/JavaScript (via typescript-language-server)
- JSON (via vscode-json-language-server)
- HTML (via vscode-html-language-server)
- CSS (via vscode-css-language-server)

## Usage

To use the LSP integration in the Terminator IDE:

```python
from terminator.lsp import LSPIntegration

# Initialize LSP integration
lsp_integration = LSPIntegration(app, workspace_path="/path/to/workspace")
await lsp_integration.initialize()

# Notify when a document is opened
await lsp_integration.document_opened(file_path, content)

# Notify when a document is changed
await lsp_integration.document_changed(file_path, content)

# Get completions at cursor
completions = await lsp_integration.get_completions_at_cursor(editor, file_path)

# Get hover information at cursor
hover_info = await lsp_integration.get_hover_at_cursor(editor, file_path)

# Go to definition
definition = await lsp_integration.go_to_definition(editor, file_path)

# Find references
references = await lsp_integration.find_references(editor, file_path)

# Format document
formatted_content = await lsp_integration.format_document(file_path, content)

# Clean up when shutting down
await lsp_integration.shutdown()
```

## Installation Requirements

Before using the LSP integration, you need to install the language servers for the languages you want to support:

```bash
# Python Language Server
pip install python-lsp-server

# TypeScript/JavaScript Language Server
npm install -g typescript typescript-language-server

# HTML/CSS/JSON Language Servers
npm install -g vscode-langservers-extracted
```

## UI Components

The LSP integration comes with UI components for displaying LSP features:

- `HoverTooltip`: Display hover information
- `CompletionMenu`: Display completion suggestions
- `DiagnosticsPanel`: Display diagnostics (errors, warnings)
- `ReferencesPanel`: Display references to a symbol

## Extending

To add support for additional languages, you can extend the `DEFAULT_SERVERS` dictionary in the `LanguageServerManager` class:

```python
# Add support for Rust
server_manager.DEFAULT_SERVERS["rust"] = {
    "command": ["rust-analyzer"],
    "name": "Rust Analyzer",
    "file_extensions": [".rs"]
}
```