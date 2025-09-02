# Framework Tooling Module

This module provides framework-specific tooling for popular web development frameworks in the Terminator IDE.

## Features

The Framework Tooling module offers:

- **Framework Detection**: Automatically detects frameworks used in a project
- **Framework-Specific Commands**: Tailored commands for each framework
- **Project Information**: Shows framework-specific project details
- **UI Integration**: Integrated UI components for framework commands

## Supported Frameworks

Currently, the module supports the following frameworks:

### Django (Python)

- Run development server
- Make and apply migrations
- Run Django shell
- Create superuser
- Collect static files
- Run tests
- Start new app

### Flask (Python)

- Run development server
- Run Flask shell
- List routes
- Database operations (with Flask-Migrate)
- Run tests
- Create blueprint

### FastAPI (Python)

- Run development server
- Access API documentation
- Generate API client
- Database migrations (with Alembic)
- Run tests

### React (JavaScript/TypeScript)

- Start development server
- Build application
- Run tests
- Lint code
- Create new component
- Analyze bundle size
- Run Storybook
- Eject from Create React App

## Usage

To use framework tooling in your application:

```python
from terminator.frameworks import (
    FrameworkDetector,
    DjangoFrameworkProvider,
    FlaskFrameworkProvider,
    FastAPIFrameworkProvider,
    ReactFrameworkProvider
)

# Detect frameworks in a project
detector = FrameworkDetector("/path/to/project")
frameworks = detector.detect_frameworks()

# Initialize a framework provider
if frameworks["django"]:
    provider = DjangoFrameworkProvider("/path/to/project")
    
    # Get project info
    info = await provider.get_project_info()
    
    # Run a command
    result = await provider.run_command("runserver")
```

## UI Integration

The module also provides UI components for framework tooling:

```python
from terminator.frameworks.base import FrameworkToolbar
from terminator.frameworks import DjangoFrameworkProvider

# Create a provider
provider = DjangoFrameworkProvider("/path/to/project")

# Create a toolbar for the provider
toolbar = FrameworkToolbar(provider)

# Add the toolbar to your UI
app.mount(toolbar)
```

## Extending

To add support for a new framework:

1. Create a new file in the `frameworks` directory
2. Implement a subclass of `FrameworkProvider`
3. Add the new provider to `__init__.py`

For example:

```python
from .base import FrameworkProvider

class VueFrameworkProvider(FrameworkProvider):
    @property
    def framework_name(self) -> str:
        return "Vue"
        
    @property
    def framework_icon(self) -> str:
        return "🟢"  # Vue icon
        
    # Implement other required methods...
```