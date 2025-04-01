"""
Flask Framework Module - Provides Flask-specific tooling
"""

import os
import sys
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional, Set, Tuple, Callable

from .base import FrameworkProvider

logger = logging.getLogger(__name__)

class FlaskFrameworkProvider(FrameworkProvider):
    """
    Provides Flask-specific tooling for Terminator IDE
    
    This class provides Flask-specific commands, project information,
    and code generation capabilities.
    """
    
    @property
    def framework_name(self) -> str:
        """Get the name of the framework"""
        return "Flask"
    
    @property
    def framework_icon(self) -> str:
        """Get an icon representation for Flask"""
        return "🧪"  # Flask icon (lab flask/beaker)
    
    @property
    def framework_commands(self) -> List[Dict[str, Any]]:
        """Get Flask-specific commands"""
        return [
            {
                "id": "run",
                "label": "Run Server",
                "description": "Start the Flask development server",
                "action": "run_server"
            },
            {
                "id": "shell",
                "label": "Flask Shell",
                "description": "Run the Flask shell",
                "action": "shell"
            },
            {
                "id": "routes",
                "label": "List Routes",
                "description": "List all registered routes",
                "action": "list_routes"
            },
            {
                "id": "db-init",
                "label": "Init DB",
                "description": "Initialize the database (requires Flask-Migrate)",
                "action": "db_init"
            },
            {
                "id": "db-migrate",
                "label": "DB Migrate",
                "description": "Create a database migration (requires Flask-Migrate)",
                "action": "db_migrate"
            },
            {
                "id": "db-upgrade",
                "label": "DB Upgrade",
                "description": "Apply database migrations (requires Flask-Migrate)",
                "action": "db_upgrade"
            },
            {
                "id": "test",
                "label": "Run Tests",
                "description": "Run tests (using pytest)",
                "action": "run_tests"
            },
            {
                "id": "blueprint",
                "label": "New Blueprint",
                "description": "Create a new Flask blueprint",
                "action": "new_blueprint"
            }
        ]
    
    async def get_project_info(self) -> Dict[str, Any]:
        """Get Flask project information"""
        info = {}
        
        try:
            # Look for app.py, main.py, or wsgi.py
            app_files = ["app.py", "main.py", "wsgi.py", "application.py"]
            app_file_path = None
            
            for file_name in app_files:
                path = os.path.join(self.workspace_path, file_name)
                if os.path.exists(path):
                    app_file_path = path
                    break
            
            if not app_file_path:
                # Try to find in subdirectories
                for root, _, files in os.walk(self.workspace_path):
                    for file_name in app_files:
                        if file_name in files:
                            app_file_path = os.path.join(root, file_name)
                            break
                    if app_file_path:
                        break
                        
            if app_file_path:
                info["App File"] = os.path.relpath(app_file_path, self.workspace_path)
                
                # Try to get Flask version
                version_output = await self._run_shell_command([
                    sys.executable, "-c", 
                    "import flask; print(flask.__version__)"
                ])
                
                if version_output.strip():
                    info["Flask Version"] = version_output.strip()
                    
                # Check for common Flask extensions
                extensions_output = await self._run_shell_command([
                    sys.executable, "-c", 
                    "import pkg_resources; print('\\n'.join([d.project_name for d in pkg_resources.working_set if 'flask-' in d.project_name.lower()]))"
                ])
                
                if extensions_output.strip():
                    extensions = extensions_output.strip().split('\n')
                    info["Extensions"] = ", ".join(extensions[:5])
                    if len(extensions) > 5:
                        info["Extensions"] += f" (and {len(extensions) - 5} more)"
                        
                # Check for database extensions
                db_extensions = [
                    "Flask-SQLAlchemy",
                    "Flask-Migrate",
                    "Flask-MongoEngine",
                    "Flask-Peewee"
                ]
                
                db_found = []
                for ext in db_extensions:
                    ext_check = await self._run_shell_command([
                        sys.executable, "-c", 
                        f"try: import {ext.lower().replace('-', '_')}; print('Found'); except ImportError: print('Not found')"
                    ])
                    if "Found" in ext_check:
                        db_found.append(ext)
                        
                if db_found:
                    info["Database"] = ", ".join(db_found)
                
        except Exception as e:
            logger.error(f"Error getting Flask project info: {str(e)}", exc_info=True)
            info["Error"] = str(e)
            
        return info
    
    async def run_command(self, command_id: str) -> str:
        """Run a Flask-specific command"""
        # Look for app.py, main.py, or wsgi.py
        app_files = ["app.py", "main.py", "wsgi.py", "application.py"]
        app_file_path = None
        
        for file_name in app_files:
            path = os.path.join(self.workspace_path, file_name)
            if os.path.exists(path):
                app_file_path = path
                break
        
        if not app_file_path and command_id != "blueprint":
            # Try to find in subdirectories
            for root, _, files in os.walk(self.workspace_path):
                for file_name in app_files:
                    if file_name in files:
                        app_file_path = os.path.join(root, file_name)
                        break
                if app_file_path:
                    break
                    
        if not app_file_path and command_id != "blueprint":
            return "Error: Could not find Flask application file (app.py, main.py, wsgi.py, or application.py)"
        
        # Call the appropriate method based on command_id
        command_map = {
            "run": self._run_server,
            "shell": self._shell,
            "routes": self._list_routes,
            "db-init": self._db_init,
            "db-migrate": self._db_migrate,
            "db-upgrade": self._db_upgrade,
            "test": self._run_tests,
            "blueprint": self._new_blueprint
        }
        
        if command_id in command_map:
            return await command_map[command_id](app_file_path)
        else:
            return f"Error: Unknown command '{command_id}'"
    
    async def _run_server(self, app_file_path: str) -> str:
        """Start the Flask development server"""
        # Set Flask environment variables
        env = os.environ.copy()
        env["FLASK_APP"] = os.path.basename(app_file_path)
        env["FLASK_ENV"] = "development"
        
        cmd = [sys.executable, "-m", "flask", "run", "--debugger", "--reload"]
        
        if self.output_callback:
            # Start the server in a new process and capture output incrementally
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(app_file_path),
                env=env
            )
            
            # Initial message
            initial_output = "Starting Flask development server...\n"
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
            
            return "Flask server stopped"
        else:
            # Run in blocking mode and return full output
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.path.dirname(app_file_path),
                    env=env
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    return stdout.decode("utf-8")
                else:
                    return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                    
            except Exception as e:
                logger.error(f"Error running Flask server: {str(e)}", exc_info=True)
                return f"Error: {str(e)}"
    
    async def _shell(self, app_file_path: str) -> str:
        """Run the Flask shell"""
        # Note: In a real implementation, this would launch an interactive shell
        return "Flask shell is not supported in this UI. Use the terminal instead."
    
    async def _list_routes(self, app_file_path: str) -> str:
        """List all registered routes"""
        # Set Flask environment variables
        env = os.environ.copy()
        env["FLASK_APP"] = os.path.basename(app_file_path)
        
        cmd = [sys.executable, "-m", "flask", "routes"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(app_file_path),
                env=env
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error listing routes: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _db_init(self, app_file_path: str) -> str:
        """Initialize the database (requires Flask-Migrate)"""
        # Set Flask environment variables
        env = os.environ.copy()
        env["FLASK_APP"] = os.path.basename(app_file_path)
        
        cmd = [sys.executable, "-m", "flask", "db", "init"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(app_file_path),
                env=env
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _db_migrate(self, app_file_path: str) -> str:
        """Create a database migration (requires Flask-Migrate)"""
        # Set Flask environment variables
        env = os.environ.copy()
        env["FLASK_APP"] = os.path.basename(app_file_path)
        
        cmd = [sys.executable, "-m", "flask", "db", "migrate", "-m", "Auto migration"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(app_file_path),
                env=env
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error creating migration: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _db_upgrade(self, app_file_path: str) -> str:
        """Apply database migrations (requires Flask-Migrate)"""
        # Set Flask environment variables
        env = os.environ.copy()
        env["FLASK_APP"] = os.path.basename(app_file_path)
        
        cmd = [sys.executable, "-m", "flask", "db", "upgrade"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(app_file_path),
                env=env
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error upgrading database: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _run_tests(self, app_file_path: str) -> str:
        """Run tests (using pytest)"""
        cmd = [sys.executable, "-m", "pytest", "-v"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(app_file_path)
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error running tests: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _new_blueprint(self, app_file_path: str) -> str:
        """Create a new Flask blueprint"""
        # Note: In a real implementation, this would prompt for the blueprint name
        # and create the necessary files
        return """Blueprint creation requires user input.
Use these steps in the terminal:

1. Create a directory for your blueprint:
   mkdir blueprints/new_blueprint

2. Create an __init__.py file:
   touch blueprints/new_blueprint/__init__.py

3. Create a routes.py file with the blueprint definition:
   
   from flask import Blueprint, render_template
   
   bp = Blueprint('new_blueprint', __name__)
   
   @bp.route('/')
   def index():
       return render_template('new_blueprint/index.html')
   
4. Register the blueprint in your app:
   
   from blueprints.new_blueprint import bp as new_blueprint_bp
   app.register_blueprint(new_blueprint_bp, url_prefix='/new')
"""