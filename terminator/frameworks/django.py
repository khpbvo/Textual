"""
Django Framework Module - Provides Django-specific tooling
"""

import os
import sys
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional, Set, Tuple, Callable

from .base import FrameworkProvider

logger = logging.getLogger(__name__)

class DjangoFrameworkProvider(FrameworkProvider):
    """
    Provides Django-specific tooling for Terminator IDE
    
    This class provides Django-specific commands, project information,
    and code generation capabilities.
    """
    
    @property
    def framework_name(self) -> str:
        """Get the name of the framework"""
        return "Django"
    
    @property
    def framework_icon(self) -> str:
        """Get an icon representation for Django"""
        return "🎸"  # Django icon (music note since Django is named after Django Reinhardt)
    
    @property
    def framework_commands(self) -> List[Dict[str, Any]]:
        """Get Django-specific commands"""
        return [
            {
                "id": "runserver",
                "label": "Run Server",
                "description": "Start the Django development server",
                "action": "run_server"
            },
            {
                "id": "makemigrations",
                "label": "Make Migrations",
                "description": "Create database migrations",
                "action": "make_migrations"
            },
            {
                "id": "migrate",
                "label": "Migrate",
                "description": "Apply database migrations",
                "action": "migrate"
            },
            {
                "id": "shell",
                "label": "Django Shell",
                "description": "Run the Django shell",
                "action": "shell"
            },
            {
                "id": "createsuperuser",
                "label": "Create Superuser",
                "description": "Create a Django admin superuser",
                "action": "create_superuser"
            },
            {
                "id": "collectstatic",
                "label": "Collect Static",
                "description": "Collect static files",
                "action": "collect_static"
            },
            {
                "id": "test",
                "label": "Run Tests",
                "description": "Run Django tests",
                "action": "run_tests"
            },
            {
                "id": "startapp",
                "label": "Start App",
                "description": "Create a new Django app",
                "action": "start_app"
            }
        ]
    
    async def get_project_info(self) -> Dict[str, Any]:
        """Get Django project information"""
        info = {}
        
        try:
            # Find manage.py
            manage_py_path = os.path.join(self.workspace_path, "manage.py")
            if not os.path.exists(manage_py_path):
                # Try to find it in subdirectories
                for root, _, files in os.walk(self.workspace_path):
                    if "manage.py" in files:
                        manage_py_path = os.path.join(root, "manage.py")
                        break
            
            if os.path.exists(manage_py_path):
                info["Manage.py Path"] = os.path.relpath(manage_py_path, self.workspace_path)
                
                # Get Django version
                version_output = await self._run_shell_command(
                    [sys.executable, manage_py_path, "version"]
                )
                if version_output.strip():
                    info["Django Version"] = version_output.strip()
                    
                # Get installed apps
                apps_output = await self._run_shell_command([
                    sys.executable, "-c", 
                    "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from django.conf import settings; print('\\n'.join(settings.INSTALLED_APPS))"
                ])
                
                if apps_output.strip():
                    app_list = apps_output.strip().split('\n')
                    info["Installed Apps"] = f"{len(app_list)} apps"
                    
                # Get database info
                db_output = await self._run_shell_command([
                    sys.executable, "-c", 
                    "import os, django, json; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from django.conf import settings; db = settings.DATABASES.get('default', {}); print(db.get('ENGINE', 'unknown'))"
                ])
                
                if db_output.strip():
                    db_engine = db_output.strip()
                    db_name = "unknown"
                    
                    if "sqlite3" in db_engine:
                        db_name = "SQLite"
                    elif "postgresql" in db_engine:
                        db_name = "PostgreSQL"
                    elif "mysql" in db_engine:
                        db_name = "MySQL"
                    
                    info["Database"] = db_name
            
        except Exception as e:
            logger.error(f"Error getting Django project info: {str(e)}", exc_info=True)
            info["Error"] = str(e)
            
        return info
    
    async def run_command(self, command_id: str) -> str:
        """Run a Django-specific command"""
        # Find manage.py
        manage_py_path = os.path.join(self.workspace_path, "manage.py")
        if not os.path.exists(manage_py_path):
            # Try to find it in subdirectories
            for root, _, files in os.walk(self.workspace_path):
                if "manage.py" in files:
                    manage_py_path = os.path.join(root, "manage.py")
                    break
        
        if not os.path.exists(manage_py_path):
            return "Error: manage.py not found in the project"
            
        # Call the appropriate method based on command_id
        command_map = {
            "runserver": self._run_server,
            "makemigrations": self._make_migrations,
            "migrate": self._migrate,
            "shell": self._shell,
            "createsuperuser": self._create_superuser,
            "collectstatic": self._collect_static,
            "test": self._run_tests,
            "startapp": self._start_app
        }
        
        if command_id in command_map:
            return await command_map[command_id](manage_py_path)
        else:
            return f"Error: Unknown command '{command_id}'"
    
    async def _run_server(self, manage_py_path: str) -> str:
        """Start the Django development server"""
        # Note: In a real implementation, this would use a non-blocking approach
        # to keep the server running in the background
        cmd = [sys.executable, manage_py_path, "runserver"]
        
        if self.output_callback:
            # Start the server in a new process and capture output incrementally
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            # Initial message
            initial_output = "Starting Django development server...\n"
            if self.output_callback:
                self.output_callback(initial_output)
                
            # Read stdout incrementally
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                    
                line_str = line.decode("utf-8")
                if self.output_callback:
                    self.output_callback(initial_output + line_str)
                    initial_output = ""  # Only include it once
            
            return "Django server stopped"
        else:
            # Run in blocking mode and return full output
            return await self._run_shell_command(cmd)
    
    async def _make_migrations(self, manage_py_path: str) -> str:
        """Create database migrations"""
        return await self._run_shell_command([
            sys.executable, manage_py_path, "makemigrations"
        ])
    
    async def _migrate(self, manage_py_path: str) -> str:
        """Apply database migrations"""
        return await self._run_shell_command([
            sys.executable, manage_py_path, "migrate"
        ])
    
    async def _shell(self, manage_py_path: str) -> str:
        """Run the Django shell"""
        # Note: In a real implementation, this would launch an interactive shell
        return "Django shell is not supported in this UI. Use the terminal instead."
    
    async def _create_superuser(self, manage_py_path: str) -> str:
        """Create a Django admin superuser"""
        # Note: In a real implementation, this would prompt for username, email, and password
        return "Creating a superuser requires interaction. Use the terminal instead."
    
    async def _collect_static(self, manage_py_path: str) -> str:
        """Collect static files"""
        return await self._run_shell_command([
            sys.executable, manage_py_path, "collectstatic", "--noinput"
        ])
    
    async def _run_tests(self, manage_py_path: str) -> str:
        """Run Django tests"""
        return await self._run_shell_command([
            sys.executable, manage_py_path, "test"
        ])
    
    async def _start_app(self, manage_py_path: str) -> str:
        """Create a new Django app"""
        # Note: In a real implementation, this would prompt for the app name
        return "Creating a new app requires input. Use the terminal instead."