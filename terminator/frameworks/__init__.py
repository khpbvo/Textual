# Framework Tooling Module for Terminator IDE

from .base import FrameworkDetector, FrameworkProvider
from .django import DjangoFrameworkProvider
from .flask import FlaskFrameworkProvider
from .fastapi import FastAPIFrameworkProvider
from .react import ReactFrameworkProvider

# The framework CSS will be composed from all framework providers
FRAMEWORKS_CSS = """
/* Framework tooling CSS */
#framework-panel {
    background: $surface;
    border: solid $panel-darken-1;
    height: 100%;
}

#framework-title {
    text-align: center;
    background: $primary;
    color: $text;
    padding: 1;
    margin-bottom: 1;
}

#framework-commands {
    margin-bottom: 1;
}

.framework-command-button {
    margin-bottom: 0;
    min-width: 15;
}

#framework-info {
    height: 8;
    background: $surface-darken-1;
    padding: 1;
    margin-bottom: 1;
}

#framework-output {
    height: 70%;
    overflow: auto;
}
"""

__all__ = [
    'FrameworkDetector',
    'FrameworkProvider',
    'DjangoFrameworkProvider',
    'FlaskFrameworkProvider',
    'FastAPIFrameworkProvider',
    'ReactFrameworkProvider',
    'FRAMEWORKS_CSS'
]