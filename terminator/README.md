# Terminator IDE Package

This package contains modularized components for the Terminator IDE, a terminal-based Python IDE with AI capabilities.

## Package Structure

The package is organized into the following modules:

- **ui**: User interface components and screens
  - `panels.py`: Resizable panel implementation
  - `diff_view.py`: Diff view for comparing code changes
  - `lsp_widgets.py`: UI widgets for LSP integration

- **utils**: Utility functions and helpers
  - `git_manager.py`: Git repository management and UI
  - `performance.py`: Performance optimization utilities

- **agents**: AI agent functionality
  - `context_manager.py`: AI agent context management and summarization

- **lsp**: Language Server Protocol integration
  - `client.py`: LSP client and language server manager
  - `features.py`: LSP feature providers
  - `integration.py`: Integration with Terminator IDE

- **frameworks**: Framework-specific tooling
  - `base.py`: Base framework detector and provider
  - `django.py`: Django framework tooling
  - `flask.py`: Flask framework tooling
  - `fastapi.py`: FastAPI framework tooling
  - `react.py`: React framework tooling

## Usage

To use these modules in the main application:

```python
# Import modules
from terminator.ui import ResizablePanelsMixin, DiffViewScreen, HoverTooltip
from terminator.utils import GitManager, CommitDialog, PerformanceOptimizer
from terminator.agents import AgentContextManager, summarize_context
from terminator.lsp import LSPIntegration
from terminator.frameworks import (
    FrameworkDetector,
    DjangoFrameworkProvider,
    FlaskFrameworkProvider,
    FastAPIFrameworkProvider,
    ReactFrameworkProvider
)

# Use them in your application
class MyApp(App, ResizablePanelsMixin):
    def __init__(self):
        super().__init__()
        self.agent_context_manager = AgentContextManager()
        self.lsp_integration = LSPIntegration(self, os.getcwd())
        
        # Detect frameworks in the workspace
        detector = FrameworkDetector(os.getcwd())
        frameworks = detector.detect_frameworks()
        
        # Initialize appropriate framework provider
        if frameworks["django"]:
            self.framework_provider = DjangoFrameworkProvider(os.getcwd(), self)
        elif frameworks["flask"]:
            self.framework_provider = FlaskFrameworkProvider(os.getcwd(), self)
        elif frameworks["fastapi"]:
            self.framework_provider = FastAPIFrameworkProvider(os.getcwd(), self)
        elif frameworks["react"]:
            self.framework_provider = ReactFrameworkProvider(os.getcwd(), self)
```

## CSS Styles

Each module provides its own CSS styles that can be included in your application:

```python
from terminator.ui import PANEL_CSS, DIFF_VIEW_CSS
from terminator.utils import COMMIT_DIALOG_CSS
from terminator.lsp import LSP_CSS
from terminator.frameworks import FRAMEWORKS_CSS

class MyApp(App):
    CSS = """
        /* Your base CSS */
    """ + PANEL_CSS + DIFF_VIEW_CSS + COMMIT_DIALOG_CSS + LSP_CSS + FRAMEWORKS_CSS
```