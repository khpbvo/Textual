"""
Base Framework Module - Provides base classes for framework-specific tooling
"""

import os
import logging
import json
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Set, Tuple, Callable

from textual.app import App, ComposeResult
from textual.widgets import Button, Label, Container, ScrollableContainer

logger = logging.getLogger(__name__)

class FrameworkDetector:
    """
    Detects which frameworks are used in a project
    
    This class examines a project's files and dependencies to identify
    which frameworks are being used.
    """
    
    def __init__(self, workspace_path: str):
        """
        Initialize the framework detector
        
        Args:
            workspace_path: Root path of the project workspace
        """
        self.workspace_path = workspace_path
        
    def detect_frameworks(self) -> Dict[str, bool]:
        """
        Detect which frameworks are used in the project
        
        Returns:
            Dictionary mapping framework names to booleans indicating if they're used
        """
        results = {
            "django": self._detect_django(),
            "flask": self._detect_flask(),
            "fastapi": self._detect_fastapi(),
            "react": self._detect_react()
        }
        
        return results
    
    def _detect_django(self) -> bool:
        """Check if Django is used in the project"""
        # Look for Django-specific files
        django_markers = [
            os.path.join(self.workspace_path, "manage.py"),
            os.path.join(self.workspace_path, "settings.py"),
            os.path.join(self.workspace_path, "*", "settings.py")
        ]
        
        # Check if any markers exist
        for marker in django_markers:
            if "*" in marker:
                # Handle wildcard pattern
                base_dir = os.path.dirname(marker.replace("*", ""))
                if os.path.exists(base_dir):
                    for item in os.listdir(base_dir):
                        item_path = os.path.join(base_dir, item)
                        if os.path.isdir(item_path):
                            settings_path = os.path.join(item_path, "settings.py")
                            if os.path.exists(settings_path):
                                return True
            else:
                if os.path.exists(marker):
                    return True
                    
        # Check requirements.txt or pyproject.toml
        requirements_path = os.path.join(self.workspace_path, "requirements.txt")
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, "r") as f:
                    content = f.read()
                    if "django" in content.lower():
                        return True
            except Exception as e:
                logger.error(f"Error reading requirements.txt: {str(e)}", exc_info=True)
                
        pyproject_path = os.path.join(self.workspace_path, "pyproject.toml")
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, "r") as f:
                    content = f.read()
                    if "django" in content.lower():
                        return True
            except Exception as e:
                logger.error(f"Error reading pyproject.toml: {str(e)}", exc_info=True)
                
        return False
    
    def _detect_flask(self) -> bool:
        """Check if Flask is used in the project"""
        # Look for Flask app files
        flask_patterns = [
            "app.py",
            "application.py",
            "wsgi.py",
            "*.py"  # We'll search for Flask imports
        ]
        
        # Common Flask imports
        flask_imports = [
            "from flask import",
            "import flask"
        ]
        
        # Check for Flask imports in Python files
        for pattern in flask_patterns:
            if pattern == "*.py":
                for root, _, files in os.walk(self.workspace_path):
                    for file in files:
                        if file.endswith(".py"):
                            file_path = os.path.join(root, file)
                            try:
                                with open(file_path, "r") as f:
                                    content = f.read()
                                    for import_stmt in flask_imports:
                                        if import_stmt in content:
                                            return True
                            except Exception as e:
                                logger.error(f"Error reading {file_path}: {str(e)}", exc_info=True)
            else:
                file_path = os.path.join(self.workspace_path, pattern)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r") as f:
                            content = f.read()
                            for import_stmt in flask_imports:
                                if import_stmt in content:
                                    return True
                    except Exception as e:
                        logger.error(f"Error reading {file_path}: {str(e)}", exc_info=True)
                        
        # Check requirements.txt or pyproject.toml
        requirements_path = os.path.join(self.workspace_path, "requirements.txt")
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, "r") as f:
                    content = f.read()
                    if "flask" in content.lower():
                        return True
            except Exception as e:
                logger.error(f"Error reading requirements.txt: {str(e)}", exc_info=True)
                
        pyproject_path = os.path.join(self.workspace_path, "pyproject.toml")
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, "r") as f:
                    content = f.read()
                    if "flask" in content.lower():
                        return True
            except Exception as e:
                logger.error(f"Error reading pyproject.toml: {str(e)}", exc_info=True)
                
        return False
    
    def _detect_fastapi(self) -> bool:
        """Check if FastAPI is used in the project"""
        # Look for FastAPI app files
        fastapi_patterns = [
            "app.py",
            "main.py",
            "api.py",
            "*.py"  # We'll search for FastAPI imports
        ]
        
        # Common FastAPI imports
        fastapi_imports = [
            "from fastapi import",
            "import fastapi"
        ]
        
        # Check for FastAPI imports in Python files
        for pattern in fastapi_patterns:
            if pattern == "*.py":
                for root, _, files in os.walk(self.workspace_path):
                    for file in files:
                        if file.endswith(".py"):
                            file_path = os.path.join(root, file)
                            try:
                                with open(file_path, "r") as f:
                                    content = f.read()
                                    for import_stmt in fastapi_imports:
                                        if import_stmt in content:
                                            return True
                            except Exception as e:
                                logger.error(f"Error reading {file_path}: {str(e)}", exc_info=True)
            else:
                file_path = os.path.join(self.workspace_path, pattern)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r") as f:
                            content = f.read()
                            for import_stmt in fastapi_imports:
                                if import_stmt in content:
                                    return True
                    except Exception as e:
                        logger.error(f"Error reading {file_path}: {str(e)}", exc_info=True)
                        
        # Check requirements.txt or pyproject.toml
        requirements_path = os.path.join(self.workspace_path, "requirements.txt")
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, "r") as f:
                    content = f.read()
                    if "fastapi" in content.lower():
                        return True
            except Exception as e:
                logger.error(f"Error reading requirements.txt: {str(e)}", exc_info=True)
                
        pyproject_path = os.path.join(self.workspace_path, "pyproject.toml")
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, "r") as f:
                    content = f.read()
                    if "fastapi" in content.lower():
                        return True
            except Exception as e:
                logger.error(f"Error reading pyproject.toml: {str(e)}", exc_info=True)
                
        return False
    
    def _detect_react(self) -> bool:
        """Check if React is used in the project"""
        # Look for React-specific files
        react_markers = [
            os.path.join(self.workspace_path, "package.json"),
            os.path.join(self.workspace_path, "node_modules", "react"),
            os.path.join(self.workspace_path, "src", "App.js"),
            os.path.join(self.workspace_path, "src", "index.js"),
            os.path.join(self.workspace_path, "public", "index.html")
        ]
        
        # Check if package.json contains React
        package_json_path = os.path.join(self.workspace_path, "package.json")
        if os.path.exists(package_json_path):
            try:
                with open(package_json_path, "r") as f:
                    package_data = json.load(f)
                    dependencies = package_data.get("dependencies", {})
                    dev_dependencies = package_data.get("devDependencies", {})
                    
                    if "react" in dependencies or "react" in dev_dependencies:
                        return True
            except Exception as e:
                logger.error(f"Error reading package.json: {str(e)}", exc_info=True)
        
        # Check for JSX files
        for root, _, files in os.walk(self.workspace_path):
            for file in files:
                if file.endswith(".jsx") or file.endswith(".tsx"):
                    return True
                    
        # Look for React imports in JS files
        for root, _, files in os.walk(self.workspace_path):
            for file in files:
                if file.endswith(".js") or file.endswith(".ts"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r") as f:
                            content = f.read()
                            if "import React" in content or "from 'react'" in content or 'from "react"' in content:
                                return True
                    except Exception as e:
                        logger.error(f"Error reading {file_path}: {str(e)}", exc_info=True)
                        
        return False


class FrameworkProvider(ABC):
    """
    Base class for framework-specific tooling providers
    
    This abstract class defines the interface for framework-specific
    tooling providers. Each supported framework should have its own
    implementation of this class.
    """
    
    def __init__(self, workspace_path: str, app: Optional[App] = None):
        """
        Initialize the framework provider
        
        Args:
            workspace_path: Root path of the project workspace
            app: Terminator app instance (optional)
        """
        self.workspace_path = workspace_path
        self.app = app
        self.output_callback: Optional[Callable[[str], None]] = None
    
    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Get the name of the framework"""
        pass
    
    @property
    @abstractmethod
    def framework_icon(self) -> str:
        """Get an icon representation for the framework"""
        pass
    
    @property
    @abstractmethod
    def framework_commands(self) -> List[Dict[str, Any]]:
        """
        Get a list of framework-specific commands
        
        Returns:
            List of command dictionaries with keys:
            - id: Command ID
            - label: Display label
            - description: Command description
            - action: Method name to call
        """
        pass
    
    @abstractmethod
    async def get_project_info(self) -> Dict[str, Any]:
        """Get framework-specific project information"""
        pass
    
    @abstractmethod
    async def run_command(self, command_id: str) -> str:
        """
        Run a framework-specific command
        
        Args:
            command_id: ID of the command to run
            
        Returns:
            Command output
        """
        pass
    
    def set_output_callback(self, callback: Callable[[str], None]) -> None:
        """
        Set a callback for command output
        
        Args:
            callback: Function to call with command output
        """
        self.output_callback = callback
    
    async def _run_shell_command(self, command: List[str]) -> str:
        """
        Run a shell command and return its output
        
        Args:
            command: Command to run as a list of arguments
            
        Returns:
            Command output
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error running command {command}: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class FrameworkToolbar(Container):
    """
    UI widget for framework-specific tooling
    
    This widget provides a toolbar of framework-specific commands
    and displays project information and command output.
    """
    
    DEFAULT_CSS = """
    FrameworkToolbar {
        width: 100%;
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
    
    def __init__(self, provider: FrameworkProvider):
        """
        Initialize the framework toolbar
        
        Args:
            provider: Framework provider instance
        """
        super().__init__(id="framework-panel")
        self.provider = provider
        self.provider.set_output_callback(self._update_output)
    
    def compose(self) -> ComposeResult:
        """Create the toolbar layout"""
        # Framework title
        yield Label(f"{self.provider.framework_icon} {self.provider.framework_name}", id="framework-title")
        
        # Framework commands
        commands_container = Container(id="framework-commands")
        for command in self.provider.framework_commands:
            commands_container.mount(Button(
                command["label"],
                id=f"framework-command-{command['id']}",
                classes="framework-command-button"
            ))
        yield commands_container
        
        # Framework info
        yield Label("Project Info:", classes="info-title")
        yield ScrollableContainer(id="framework-info")
        
        # Command output
        yield Label("Output:", classes="output-title")
        yield ScrollableContainer(id="framework-output")
    
    async def on_mount(self) -> None:
        """Called when the widget is mounted"""
        # Load framework info
        await self._load_project_info()
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        if button_id.startswith("framework-command-"):
            command_id = button_id[len("framework-command-"):]
            
            # Clear output
            output_container = self.query_one("#framework-output")
            output_container.remove_children()
            output_container.mount(Label("Running command..."))
            
            # Run the command
            asyncio.create_task(self._run_command(command_id))
    
    async def _load_project_info(self) -> None:
        """Load and display framework project information"""
        try:
            # Get project info
            info = await self.provider.get_project_info()
            
            # Display info
            info_container = self.query_one("#framework-info")
            info_container.remove_children()
            
            for key, value in info.items():
                info_container.mount(Label(f"{key}: {value}"))
                
        except Exception as e:
            logger.error(f"Error loading project info: {str(e)}", exc_info=True)
            
            info_container = self.query_one("#framework-info")
            info_container.remove_children()
            info_container.mount(Label(f"Error: {str(e)}"))
    
    async def _run_command(self, command_id: str) -> None:
        """Run a framework command"""
        try:
            # Run the command
            output = await self.provider.run_command(command_id)
            
            # Update output
            self._update_output(output)
                
        except Exception as e:
            logger.error(f"Error running command: {str(e)}", exc_info=True)
            
            output_container = self.query_one("#framework-output")
            output_container.remove_children()
            output_container.mount(Label(f"Error: {str(e)}"))
    
    def _update_output(self, output: str) -> None:
        """Update the output container with command output"""
        output_container = self.query_one("#framework-output")
        output_container.remove_children()
        
        # Split output into lines and create labels
        lines = output.splitlines()
        for line in lines:
            output_container.mount(Label(line))