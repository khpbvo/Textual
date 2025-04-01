# Language Server Protocol (LSP) Module for Terminator IDE

from .client import LSPClient, LanguageServerManager
from .features import (
    CompletionProvider,
    DiagnosticsProvider,
    HoverProvider,
    DefinitionProvider,
    ReferenceProvider
)
from .integration import LSPIntegration

# Default CSS for LSP UI components
LSP_CSS = """
/* Hover tooltip */
.lsp-hover {
    background: $surface;
    border: solid $accent;
    padding: 1;
    max-width: 80;
    max-height: 20;
    overflow: auto;
}

/* Diagnostics */
.lsp-error {
    text-decoration: underline $error;
    text-decoration-style: wavy;
}

.lsp-warning {
    text-decoration: underline $warning;
    text-decoration-style: wavy;
}

.lsp-info {
    text-decoration: underline $info;
    text-decoration-style: dotted;
}

/* Completion menu */
.lsp-completion-menu {
    background: $surface;
    border: solid $accent;
    padding: 0;
    max-width: 60;
    max-height: 15;
    overflow: auto;
}

.lsp-completion-item {
    padding: 0 1;
}

.lsp-completion-item-selected {
    background: $accent;
    color: $text;
}

.lsp-completion-kind-icon {
    width: 2;
    margin-right: 1;
    color: $text-muted;
}

/* References panel */
.lsp-references-panel {
    background: $surface;
    border: solid $accent;
    padding: 1;
    height: 15;
    overflow: auto;
}

.lsp-references-title {
    text-align: center;
    background: $primary;
    color: $text;
    margin-bottom: 1;
}

.lsp-reference-item {
    margin-bottom: 0;
    padding: 0 1;
}

.lsp-reference-item-selected {
    background: $accent-darken-2;
}
"""

__all__ = [
    'LSPClient',
    'LanguageServerManager',
    'CompletionProvider',
    'DiagnosticsProvider',
    'HoverProvider',
    'DefinitionProvider',
    'ReferenceProvider',
    'LSPIntegration',
    'LSP_CSS'
]