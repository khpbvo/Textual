"""
FastAPI Framework Module - Provides FastAPI-specific tooling
"""

import os
import sys
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional, Set, Tuple, Callable

from .base import FrameworkProvider

logger = logging.getLogger(__name__)

class FastAPIFrameworkProvider(FrameworkProvider):
    """
    Provides FastAPI-specific tooling for Terminator IDE
    
    This class provides FastAPI-specific commands, project information,
    and code generation capabilities.
    """
    
    @property
    def framework_name(self) -> str:
        """Get the name of the framework"""
        return "FastAPI"
    
    @property
    def framework_icon(self) -> str:
        """Get an icon representation for FastAPI"""
        return "⚡"  # FastAPI icon (lightning bolt for "fast")
    
    @property
    def framework_commands(self) -> List[Dict[str, Any]]:
        """Get FastAPI-specific commands"""
        return [
            {
                "id": "run",
                "label": "Run Server",
                "description": "Start the FastAPI development server",
                "action": "run_server"
            },
            {
                "id": "docs",
                "label": "Open Docs",
                "description": "Open the FastAPI documentation in a browser",
                "action": "open_docs"
            },
            {
                "id": "redoc",
                "label": "Open ReDoc",
                "description": "Open the ReDoc documentation in a browser",
                "action": "open_redoc"
            },
            {
                "id": "generate-client",
                "label": "Generate Client",
                "description": "Generate a TypeScript client",
                "action": "generate_client"
            },
            {
                "id": "alembic-init",
                "label": "Init DB",
                "description": "Initialize Alembic for migrations",
                "action": "alembic_init"
            },
            {
                "id": "alembic-migrate",
                "label": "DB Migrate",
                "description": "Create an Alembic migration",
                "action": "alembic_migrate"
            },
            {
                "id": "alembic-upgrade",
                "label": "DB Upgrade",
                "description": "Apply Alembic migrations",
                "action": "alembic_upgrade"
            },
            {
                "id": "test",
                "label": "Run Tests",
                "description": "Run tests with pytest",
                "action": "run_tests"
            }
        ]
    
    async def get_project_info(self) -> Dict[str, Any]:
        """Get FastAPI project information"""
        info = {}
        
        try:
            # Look for main.py, app.py, or api.py
            app_files = ["main.py", "app.py", "api.py"]
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
                
                # Try to get FastAPI version
                version_output = await self._run_shell_command([
                    sys.executable, "-c", 
                    "import fastapi; print(fastapi.__version__)"
                ])
                
                if version_output.strip():
                    info["FastAPI Version"] = version_output.strip()
                    
                # Check for common FastAPI dependencies
                deps_output = await self._run_shell_command([
                    sys.executable, "-c", 
                    "import pkg_resources; print('\\n'.join([d.project_name for d in pkg_resources.working_set if d.project_name.lower() in ['uvicorn', 'pydantic', 'starlette', 'sqlalchemy', 'alembic']]))"
                ])
                
                if deps_output.strip():
                    deps = deps_output.strip().split('\n')
                    info["Dependencies"] = ", ".join(deps)
                
                # Check for database
                has_sqlalchemy = await self._run_shell_command([
                    sys.executable, "-c", 
                    "try: import sqlalchemy; print('Yes'); except ImportError: print('No')"
                ])
                
                if "Yes" in has_sqlalchemy:
                    info["Database"] = "SQLAlchemy"
                    
                    # Check for Alembic
                    has_alembic = await self._run_shell_command([
                        sys.executable, "-c", 
                        "try: import alembic; print('Yes'); except ImportError: print('No')"
                    ])
                    
                    if "Yes" in has_alembic:
                        info["Migrations"] = "Alembic"
                
        except Exception as e:
            logger.error(f"Error getting FastAPI project info: {str(e)}", exc_info=True)
            info["Error"] = str(e)
            
        return info
    
    async def run_command(self, command_id: str) -> str:
        """Run a FastAPI-specific command"""
        # Look for main.py, app.py, or api.py
        app_files = ["main.py", "app.py", "api.py"]
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
                    
        if not app_file_path:
            return "Error: Could not find FastAPI application file (main.py, app.py, or api.py)"
        
        # Call the appropriate method based on command_id
        command_map = {
            "run": self._run_server,
            "docs": self._open_docs,
            "redoc": self._open_redoc,
            "generate-client": self._generate_client,
            "alembic-init": self._alembic_init,
            "alembic-migrate": self._alembic_migrate,
            "alembic-upgrade": self._alembic_upgrade,
            "test": self._run_tests
        }
        
        if command_id in command_map:
            return await command_map[command_id](app_file_path)
        else:
            return f"Error: Unknown command '{command_id}'"
    
    async def _run_server(self, app_file_path: str) -> str:
        """Start the FastAPI development server"""
        app_module = os.path.basename(app_file_path).replace(".py", "")
        cmd = [sys.executable, "-m", "uvicorn", f"{app_module}:app", "--reload"]
        
        if self.output_callback:
            # Start the server in a new process and capture output incrementally
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(app_file_path)
            )
            
            # Initial message
            initial_output = "Starting FastAPI development server...\n"
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
            
            return "FastAPI server stopped"
        else:
            # Run in blocking mode and return full output
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
                logger.error(f"Error running FastAPI server: {str(e)}", exc_info=True)
                return f"Error: {str(e)}"
    
    async def _open_docs(self, app_file_path: str) -> str:
        """Open the FastAPI documentation in a browser"""
        # Start the server first
        app_module = os.path.basename(app_file_path).replace(".py", "")
        
        # Get a free port
        port = await self._get_free_port()
        
        # Start the server in the background
        cmd = [sys.executable, "-m", "uvicorn", f"{app_module}:app", f"--port={port}"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(app_file_path)
        )
        
        # Wait a moment for the server to start
        await asyncio.sleep(2)
        
        # Open the docs URL
        docs_url = f"http://localhost:{port}/docs"
        
        # Use webbrowser module to open the URL
        await self._run_shell_command([
            sys.executable, "-c", f"import webbrowser; webbrowser.open('{docs_url}')"
        ])
        
        # Wait for a moment before killing the server
        await asyncio.sleep(5)
        process.terminate()
        
        return f"Opened FastAPI docs at {docs_url}"
    
    async def _open_redoc(self, app_file_path: str) -> str:
        """Open the ReDoc documentation in a browser"""
        # Start the server first
        app_module = os.path.basename(app_file_path).replace(".py", "")
        
        # Get a free port
        port = await self._get_free_port()
        
        # Start the server in the background
        cmd = [sys.executable, "-m", "uvicorn", f"{app_module}:app", f"--port={port}"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(app_file_path)
        )
        
        # Wait a moment for the server to start
        await asyncio.sleep(2)
        
        # Open the ReDoc URL
        redoc_url = f"http://localhost:{port}/redoc"
        
        # Use webbrowser module to open the URL
        await self._run_shell_command([
            sys.executable, "-c", f"import webbrowser; webbrowser.open('{redoc_url}')"
        ])
        
        # Wait for a moment before killing the server
        await asyncio.sleep(5)
        process.terminate()
        
        return f"Opened FastAPI ReDoc at {redoc_url}"
    
    async def _generate_client(self, app_file_path: str) -> str:
        """Generate a TypeScript client"""
        # Check if openapi-generator-cli is installed
        openapi_check = await self._run_shell_command([
            "which", "openapi-generator-cli"
        ])
        
        if not openapi_check.strip():
            return """Error: openapi-generator-cli not found.
            
Install it with:
npm install @openapitools/openapi-generator-cli -g"""
        
        # Start the server first to get the OpenAPI schema
        app_module = os.path.basename(app_file_path).replace(".py", "")
        
        # Get a free port
        port = await self._get_free_port()
        
        # Start the server in the background
        cmd = [sys.executable, "-m", "uvicorn", f"{app_module}:app", f"--port={port}"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(app_file_path)
        )
        
        # Wait a moment for the server to start
        await asyncio.sleep(2)
        
        # Get the OpenAPI schema URL
        openapi_url = f"http://localhost:{port}/openapi.json"
        
        # Create a clients directory
        clients_dir = os.path.join(self.workspace_path, "clients")
        os.makedirs(clients_dir, exist_ok=True)
        
        # Run the openapi-generator to generate a TypeScript client
        result = await self._run_shell_command([
            "openapi-generator-cli", "generate",
            "-i", openapi_url,
            "-g", "typescript-fetch",
            "-o", os.path.join(clients_dir, "typescript-client")
        ])
        
        # Kill the server
        process.terminate()
        
        return f"TypeScript client generated in ./clients/typescript-client\n\n{result}"
    
    async def _alembic_init(self, app_file_path: str) -> str:
        """Initialize Alembic for migrations"""
        cmd = [sys.executable, "-m", "alembic", "init", "migrations"]
        
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
            logger.error(f"Error initializing Alembic: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _alembic_migrate(self, app_file_path: str) -> str:
        """Create an Alembic migration"""
        cmd = [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "Auto migration"]
        
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
            logger.error(f"Error creating Alembic migration: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _alembic_upgrade(self, app_file_path: str) -> str:
        """Apply Alembic migrations"""
        cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
        
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
            logger.error(f"Error applying Alembic migrations: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _run_tests(self, app_file_path: str) -> str:
        """Run tests with pytest"""
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
    
    async def _get_free_port(self) -> int:
        """Get a free port to use for the server"""
        import socket
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', 0))
        addr = s.getsockname()
        s.close()
        
        return addr[1]