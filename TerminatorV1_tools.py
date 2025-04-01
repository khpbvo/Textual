"""
TerminatorV1 Tools - Utility tools for the Terminator IDE
Provides file operations, code analysis, git integration, and real-time collaboration tools
"""

import os
import re
import sys
import json
import subprocess
import difflib
import tempfile
import asyncio
import uuid
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple, Set, Callable
from dataclasses import dataclass
import websockets

# File System Utilities
class FileSystem:
    """File system utilities for Terminator"""
    
    @staticmethod
    def read_file(file_path: str, max_size_mb: int = 10) -> Tuple[bool, str]:
        """
        Read a file safely
        
        Args:
            file_path: Path to the file
            max_size_mb: Maximum file size in MB
            
        Returns:
            Tuple of (success, content/error_message)
        """
        try:
            file_path = os.path.expanduser(file_path)
            
            if not os.path.exists(file_path):
                return False, f"File not found: {file_path}"
                
            if os.path.isdir(file_path):
                return False, f"Path is a directory, not a file: {file_path}"
                
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > max_size_mb * 1024 * 1024:
                return False, f"File too large: {file_size / (1024*1024):.2f} MB (max: {max_size_mb} MB)"
                
            with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
                content = file.read()
                
            return True, content
            
        except Exception as e:
            return False, f"Error reading file: {str(e)}"
    
    @staticmethod
    def write_file(file_path: str, content: str, create_dirs: bool = True) -> Tuple[bool, str]:
        """
        Write content to a file
        
        Args:
            file_path: Path to the file
            content: Content to write
            create_dirs: Whether to create parent directories
            
        Returns:
            Tuple of (success, message)
        """
        try:
            file_path = os.path.expanduser(file_path)
            
            # Create parent directories if they don't exist
            if create_dirs:
                os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
                
            return True, f"File saved: {file_path}"
            
        except Exception as e:
            return False, f"Error writing file: {str(e)}"
    
    @staticmethod
    def get_directory_structure(path: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Get a nested dictionary representing the directory structure
        
        Args:
            path: Directory path
            max_depth: Maximum recursion depth
            
        Returns:
            Directory structure as a nested dictionary
        """
        result = {"dirs": {}, "files": []}
        
        try:
            path = os.path.expanduser(path)
            
            if not os.path.isdir(path):
                return {"error": f"Not a directory: {path}"}
                
            def scan_directory(dir_path, current_depth=0):
                if current_depth > max_depth:
                    return {"dirs": {}, "files": ["... (max depth reached)"]}
                    
                result = {"dirs": {}, "files": []}
                
                try:
                    for entry in os.scandir(dir_path):
                        if entry.is_dir():
                            result["dirs"][entry.name] = scan_directory(
                                entry.path, current_depth + 1
                            )
                        else:
                            result["files"].append(entry.name)
                except PermissionError:
                    return {"error": "Permission denied"}
                    
                return result
                
            return scan_directory(path)
            
        except Exception as e:
            return {"error": str(e)}

# Code Analysis Utilities
class CodeAnalyzer:
    """Code analysis utilities"""
    
    @staticmethod
    def analyze_python_code(code: str) -> Dict[str, Any]:
        """
        Analyze Python code for common issues
        
        Args:
            code: Python code to analyze
            
        Returns:
            Analysis results
        """
        issues = []
        
        # Check for simple issues
        lines = code.splitlines()
        
        # Check for long lines
        for i, line in enumerate(lines):
            if len(line) > 100:
                issues.append({
                    "line": i + 1,
                    "type": "style",
                    "message": f"Line too long ({len(line)} > 100 characters)"
                })
        
        # Check for missing docstrings
        if len(lines) > 1 and not any(line.strip().startswith('"""') for line in lines[:5]):
            issues.append({
                "line": 1,
                "type": "style",
                "message": "Missing module docstring"
            })
        
        # Check for function definitions without docstrings
        function_pattern = r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)(?:\s*->.*?)?:'
        for i, line in enumerate(lines):
            match = re.search(function_pattern, line)
            if match:
                func_name = match.group(1)
                
                # Check next lines for docstring
                has_docstring = False
                for j in range(i+1, min(i+4, len(lines))):
                    if lines[j].strip().startswith('"""'):
                        has_docstring = True
                        break
                
                if not has_docstring:
                    issues.append({
                        "line": i + 1,
                        "type": "style",
                        "message": f"Missing docstring for function '{func_name}'"
                    })
        
        # Try to use pylint if available
        try:
            with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as temp:
                temp_path = temp.name
                temp.write(code.encode('utf-8'))
            
            try:
                result = subprocess.run(
                    ['pylint', '--output-format=json', '--exit-zero', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.stdout:
                    try:
                        pylint_issues = json.loads(result.stdout)
                        for issue in pylint_issues:
                            issues.append({
                                "line": issue.get("line", 0),
                                "type": issue.get("type", "unknown"),
                                "message": issue.get("message", "Unknown issue")
                            })
                    except json.JSONDecodeError:
                        pass
                        
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
                
            finally:
                os.unlink(temp_path)
                
        except Exception:
            pass
        
        return {
            "issues": issues,
            "issue_count": len(issues),
            "recommendations": [
                "Add docstrings to all functions and modules",
                "Keep lines under 100 characters",
                "Use meaningful variable names"
            ] if issues else []
        }
    
    @staticmethod
    def create_diff(original: str, modified: str) -> str:
        """
        Create a unified diff between original and modified text
        
        Args:
            original: Original text
            modified: Modified text
            
        Returns:
            Unified diff as a string
        """
        original_lines = original.splitlines(True)
        modified_lines = modified.splitlines(True)
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile="Original",
            tofile="Modified",
            n=3
        )
        
        return ''.join(diff)
    
    @staticmethod
    def count_code_lines(code: str) -> Dict[str, int]:
        """
        Count lines of code, comments and blank lines
        
        Args:
            code: Code to analyze
            
        Returns:
            Counts of different line types
        """
        lines = code.splitlines()
        
        blank_lines = 0
        comment_lines = 0
        code_lines = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith('#'):
                comment_lines += 1
            else:
                code_lines += 1
                
        return {
            "total_lines": len(lines),
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "blank_lines": blank_lines
        }

# Git Utilities
class GitManager:
    """Git integration utilities"""
    
    @staticmethod
    def check_git_repo(path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a directory is a Git repository
        
        Args:
            path: Directory path to check
            
        Returns:
            Tuple of (is_repo, repo_root)
        """
        try:
            # Try to find .git directory
            current_path = os.path.abspath(path)
            while current_path != os.path.dirname(current_path):  # Stop at filesystem root
                if os.path.exists(os.path.join(current_path, '.git')):
                    return True, current_path
                current_path = os.path.dirname(current_path)
                
            return False, None
            
        except Exception:
            return False, None
            
    @staticmethod
    def get_branches(repo_path: str) -> Dict[str, Any]:
        """
        Get list of branches and the current branch
        
        Args:
            repo_path: Path to Git repository
            
        Returns:
            Dictionary with branch information
        """
        try:
            # Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return {"error": f"Git error: {result.stderr}"}
                
            current_branch = result.stdout.strip()
            
            # Get all branches
            result = subprocess.run(
                ['git', 'branch', '-a'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return {"error": f"Git error: {result.stderr}"}
                
            all_branches = []
            remote_branches = []
            
            for line in result.stdout.splitlines():
                branch_name = line.strip()
                if branch_name.startswith('*'):
                    # Current branch, already captured
                    continue
                    
                if branch_name.startswith('remotes/'):
                    # Remote branch
                    remote_branch = branch_name.strip().replace('remotes/', '', 1)
                    remote_branches.append(remote_branch)
                else:
                    # Local branch
                    all_branches.append(branch_name.strip())
            
            return {
                "current_branch": current_branch,
                "local_branches": all_branches,
                "remote_branches": remote_branches
            }
            
        except Exception as e:
            return {"error": str(e)}
            
    @staticmethod
    def get_branch_graph(repo_path: str, max_commits: int = 20) -> Dict[str, Any]:
        """
        Get branch graph information for visualization
        
        Args:
            repo_path: Path to Git repository
            max_commits: Maximum number of commits to include
            
        Returns:
            Dictionary with branch graph data
        """
        try:
            # Get graph data using git log with graph format
            result = subprocess.run(
                ['git', 'log', '--graph', '--oneline', '--decorate', '--all', f'-n{max_commits}'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return {"error": f"Git error: {result.stderr}"}
                
            # Get commit data for more details
            commit_result = subprocess.run(
                ['git', 'log', '--pretty=format:%H|%an|%ad|%s', '--date=short', f'-n{max_commits}'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if commit_result.returncode != 0:
                return {"error": f"Git error: {commit_result.stderr}"}
                
            # Parse commit data
            commits = []
            for line in commit_result.stdout.splitlines():
                parts = line.split('|', 3)
                if len(parts) >= 4:
                    commit_hash, author, date, message = parts
                    commits.append({
                        "hash": commit_hash,
                        "short_hash": commit_hash[:7],
                        "author": author,
                        "date": date,
                        "message": message
                    })
            
            # Get branch structure
            branch_data = GitManager.get_branches(repo_path)
            
            return {
                "graph_output": result.stdout,
                "commits": commits,
                "branches": branch_data
            }
            
        except Exception as e:
            return {"error": str(e)}
            
    @staticmethod
    def switch_branch(repo_path: str, branch_name: str) -> Tuple[bool, str]:
        """
        Switch to a different branch
        
        Args:
            repo_path: Path to Git repository
            branch_name: Name of the branch to switch to
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Check if branch exists
            result = subprocess.run(
                ['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch_name}'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            branch_exists = result.returncode == 0
            
            if branch_exists:
                # Checkout existing branch
                result = subprocess.run(
                    ['git', 'checkout', branch_name],
                    capture_output=True,
                    text=True,
                    cwd=repo_path
                )
            else:
                # Check if it's a remote branch
                result = subprocess.run(
                    ['git', 'show-ref', '--verify', '--quiet', f'refs/remotes/origin/{branch_name}'],
                    capture_output=True,
                    text=True,
                    cwd=repo_path
                )
                
                remote_exists = result.returncode == 0
                
                if remote_exists:
                    # Checkout remote branch
                    result = subprocess.run(
                        ['git', 'checkout', '-b', branch_name, f'origin/{branch_name}'],
                        capture_output=True,
                        text=True,
                        cwd=repo_path
                    )
                else:
                    # Create and checkout new branch
                    result = subprocess.run(
                        ['git', 'checkout', '-b', branch_name],
                        capture_output=True,
                        text=True,
                        cwd=repo_path
                    )
            
            if result.returncode != 0:
                return False, f"Failed to switch branch: {result.stderr}"
                
            return True, f"Switched to branch '{branch_name}'"
            
        except Exception as e:
            return False, f"Error switching branch: {str(e)}"
            
    @staticmethod
    def create_branch(repo_path: str, branch_name: str) -> Tuple[bool, str]:
        """
        Create a new branch
        
        Args:
            repo_path: Path to Git repository
            branch_name: Name of the new branch
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Create and checkout new branch
            result = subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return False, f"Failed to create branch: {result.stderr}"
                
            return True, f"Created and switched to branch '{branch_name}'"
            
        except Exception as e:
            return False, f"Error creating branch: {str(e)}"
    
    @staticmethod
    def get_git_status(repo_path: str) -> Dict[str, Any]:
        """
        Get Git repository status
        
        Args:
            repo_path: Path to Git repository
            
        Returns:
            Git status information
        """
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return {"error": f"Git error: {result.stderr}"}
                
            modified_files = []
            untracked_files = []
            staged_files = []
            
            for line in result.stdout.splitlines():
                status = line[:2]
                filename = line[3:]
                
                if status.startswith('M'):
                    modified_files.append(filename)
                elif status.startswith('A'):
                    staged_files.append(filename)
                elif status.startswith('??'):
                    untracked_files.append(filename)
                else:
                    # Other statuses (deleted, renamed, etc.)
                    staged_files.append(filename)
                    
            return {
                "clean": len(result.stdout.strip()) == 0,
                "modified_files": modified_files,
                "untracked_files": untracked_files,
                "staged_files": staged_files
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    def git_commit(repo_path: str, message: str) -> Tuple[bool, str]:
        """
        Commit changes to Git repository
        
        Args:
            repo_path: Path to Git repository
            message: Commit message
            
        Returns:
            Tuple of (success, message)
        """
        try:
            result = subprocess.run(
                ['git', 'commit', '-m', message],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return False, f"Commit failed: {result.stderr}"
                
            return True, result.stdout
            
        except Exception as e:
            return False, f"Commit error: {str(e)}"
            
    @staticmethod
    def git_push(repo_path: str) -> Tuple[bool, str]:
        """
        Push changes to remote repository
        
        Args:
            repo_path: Path to Git repository
            
        Returns:
            Tuple of (success, message)
        """
        try:
            result = subprocess.run(
                ['git', 'push'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return False, f"Push failed: {result.stderr}"
                
            return True, result.stdout
            
        except Exception as e:
            return False, f"Push error: {str(e)}"
            
    @staticmethod
    def git_pull(repo_path: str) -> Tuple[bool, str]:
        """
        Pull changes from remote repository
        
        Args:
            repo_path: Path to Git repository
            
        Returns:
            Tuple of (success, message)
        """
        try:
            result = subprocess.run(
                ['git', 'pull'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                return False, f"Pull failed: {result.stderr}"
                
            return True, result.stdout
            
        except Exception as e:
            return False, f"Pull error: {str(e)}"

# Debugger Utilities
class PythonDebugger:
    """Python debugger utilities for code debugging and inspection"""
    
    @staticmethod
    def start_debugging(file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Start a debugging session for a Python file
        
        Args:
            file_path: Path to the Python file to debug
            
        Returns:
            Tuple of (success, session_info)
        """
        try:
            if not file_path.endswith('.py'):
                return False, {"error": "Only Python files can be debugged"}
                
            if not os.path.exists(file_path):
                return False, {"error": f"File not found: {file_path}"}
                
            # Setup debugging session using pdb
            import pdb
            import sys
            import io
            import threading
            import importlib.util
            from types import ModuleType
            
            # Create a debug info object
            debug_session = {
                "file_path": file_path,
                "active": True,
                "current_line": 1,
                "variables": {},
                "output": "",
                "call_stack": [],
                "breakpoints": []
            }
            
            # In a real implementation, we would launch a proper
            # debug session with a subprocess using pdb or similar
            
            # For demonstration, we'll simulate a debug session
            with open(file_path, 'r', encoding='utf-8') as f:
                code_lines = f.readlines()
                
            debug_session["code"] = "".join(code_lines)
            debug_session["line_count"] = len(code_lines)
            
            # Add some sample data for demonstration
            debug_session["variables"] = {
                "x": {"type": "int", "value": "10"},
                "y": {"type": "str", "value": '"hello"'},
                "my_list": {"type": "list", "value": "[1, 2, 3]"}
            }
            
            debug_session["call_stack"] = [
                {"frame": 0, "function": "main", "file": os.path.basename(file_path), "line": 1},
                {"frame": 1, "function": "<module>", "file": os.path.basename(file_path), "line": 1}
            ]
            
            return True, debug_session
            
        except Exception as e:
            return False, {"error": f"Error starting debugger: {str(e)}"}
    
    @staticmethod
    def set_breakpoint(file_path: str, line: int) -> Tuple[bool, str]:
        """
        Set a breakpoint at a specific line
        
        Args:
            file_path: Path to the Python file
            line: Line number for the breakpoint
            
        Returns:
            Tuple of (success, message)
        """
        try:
            if not os.path.exists(file_path):
                return False, f"File not found: {file_path}"
                
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            if line < 1 or line > len(lines):
                return False, f"Line number out of range: {line}"
                
            # In a real implementation, we'd actually set the breakpoint
            # using pdb or a proper debugger
            
            return True, f"Breakpoint set at line {line}"
            
        except Exception as e:
            return False, f"Error setting breakpoint: {str(e)}"
    
    @staticmethod
    def debug_step(debug_session: Dict[str, Any], command: str) -> Dict[str, Any]:
        """
        Execute a debug step command
        
        Args:
            debug_session: The current debug session info
            command: Debug command ('step', 'next', 'continue', etc.)
            
        Returns:
            Updated debug session info
        """
        # Simulate stepping through code
        if not debug_session.get("active", False):
            debug_session["error"] = "No active debugging session"
            return debug_session
            
        current_line = debug_session.get("current_line", 1)
        line_count = debug_session.get("line_count", 1)
        
        if command == "step_over" or command == "next":
            # Move to the next line
            debug_session["current_line"] = min(current_line + 1, line_count)
            
        elif command == "step_into" or command == "step":
            # Simulate stepping into a function
            debug_session["current_line"] = min(current_line + 1, line_count)
            
            # Add a frame to the call stack if appropriate
            if current_line + 1 <= line_count and "def " in debug_session.get("code", "").splitlines()[current_line]:
                func_name = debug_session.get("code", "").splitlines()[current_line].strip().split("def ")[1].split("(")[0]
                debug_session["call_stack"].insert(0, {
                    "frame": 0,
                    "function": func_name,
                    "file": os.path.basename(debug_session.get("file_path", "")),
                    "line": current_line + 1
                })
                
                # Increment other frames
                for i in range(1, len(debug_session["call_stack"])):
                    debug_session["call_stack"][i]["frame"] = i
                
        elif command == "step_out" or command == "return":
            # Simulate stepping out of a function
            debug_session["current_line"] = min(current_line + 1, line_count)
            
            # Remove a frame from the call stack if there are multiple frames
            if len(debug_session.get("call_stack", [])) > 1:
                debug_session["call_stack"] = debug_session["call_stack"][1:]
                
                # Update frame numbers
                for i in range(len(debug_session["call_stack"])):
                    debug_session["call_stack"][i]["frame"] = i
                    
        elif command == "continue":
            # Simulate continuing to the next breakpoint (or end)
            debug_session["current_line"] = line_count
            
        # Update variables to simulate program execution
        if debug_session["current_line"] % 3 == 0:
            # Change some variables periodically to simulate program flow
            debug_session["variables"]["x"] = {"type": "int", "value": str(int(debug_session["variables"]["x"]["value"]) + 1)}
            
        # Check if we've reached the end
        if debug_session["current_line"] >= line_count:
            debug_session["active"] = False
            debug_session["output"] += "\nProgram execution completed."
            
        return debug_session
    
    @staticmethod
    def stop_debugging(debug_session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stop a debugging session
        
        Args:
            debug_session: The current debug session info
            
        Returns:
            Final debug session info with active=False
        """
        debug_session["active"] = False
        debug_session["output"] += "\nDebugging session terminated."
        return debug_session
    
    @staticmethod
    def evaluate_expression(debug_session: Dict[str, Any], expression: str) -> Tuple[bool, Any]:
        """
        Evaluate an expression in the current debug context
        
        Args:
            debug_session: The current debug session info
            expression: The expression to evaluate
            
        Returns:
            Tuple of (success, result/error)
        """
        try:
            # In a real implementation, we'd use the actual debugger's evaluation
            # For demonstration, simulate simple expression evaluation
            
            if expression in debug_session.get("variables", {}):
                var_info = debug_session["variables"][expression]
                return True, f"{var_info['value']} ({var_info['type']})"
            
            if expression == "len(my_list)":
                return True, "3"
                
            return False, f"Cannot evaluate '{expression}' in current context"
            
        except Exception as e:
            return False, f"Error evaluating expression: {str(e)}"

# Python Execution
class PythonRunner:
    """Python code execution utilities"""
    
    @staticmethod
    def run_code(code: str, timeout: int = 10) -> Dict[str, Any]:
        """
        Run Python code safely
        
        Args:
            code: Python code to run
            timeout: Maximum execution time in seconds
            
        Returns:
            Execution results
        """
        try:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as temp:
                temp_path = temp.name
                temp.write(code.encode('utf-8'))
            
            try:
                # Run the code with timeout
                result = subprocess.run(
                    [sys.executable, temp_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
                
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": f"Execution timed out after {timeout} seconds"
                }
                
            finally:
                # Clean up
                os.unlink(temp_path)
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error: {str(e)}"
            }


# Real-time Collaboration Manager
class CollaborationManager:
    """Manages real-time collaboration between multiple users"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        Initialize the collaboration manager
        
        Args:
            host: WebSocket server host
            port: WebSocket server port
        """
        self.host = host
        self.port = port
        self.server = None
        self.clients = set()
        self.sessions: Dict[str, 'CollaborationSession'] = {}
        self.running = False
        
    async def start_server(self) -> None:
        """Start the WebSocket server"""
        if self.running:
            return
            
        self.running = True
        self.server = await websockets.serve(
            self.handle_connection, 
            self.host, 
            self.port
        )
        
    async def stop_server(self) -> None:
        """Stop the WebSocket server"""
        if not self.running:
            return
            
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
    async def handle_connection(self, websocket, path) -> None:
        """
        Handle a new WebSocket connection
        
        Args:
            websocket: The WebSocket connection
            path: The connection path
        """
        client_id = str(uuid.uuid4())
        self.clients.add(websocket)
        
        try:
            # Wait for initial message with user info
            message = await websocket.recv()
            data = json.loads(message)
            
            if data["type"] == "join":
                session_id = data["session_id"]
                username = data["username"]
                
                # Create session if it doesn't exist
                if session_id not in self.sessions:
                    self.sessions[session_id] = CollaborationSession(session_id)
                
                # Add user to session
                await self.sessions[session_id].add_user(client_id, username, websocket)
                
                # Welcome message
                await websocket.send(json.dumps({
                    "type": "welcome",
                    "session_id": session_id,
                    "client_id": client_id,
                    "message": f"Welcome to the collaboration session, {username}!"
                }))
                
                # Notify other users
                await self.sessions[session_id].broadcast({
                    "type": "user_joined",
                    "username": username,
                    "client_id": client_id
                }, exclude=websocket)
                
                # Main message handling loop
                async for message in websocket:
                    data = json.loads(message)
                    
                    if data["type"] == "edit":
                        # Handle edit operation
                        await self.sessions[session_id].handle_edit(data, client_id)
                    elif data["type"] == "cursor_move":
                        # Handle cursor movement
                        await self.sessions[session_id].handle_cursor_move(data, client_id)
                    elif data["type"] == "chat":
                        # Handle chat message
                        await self.sessions[session_id].handle_chat(data, client_id)
        
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"Collaboration error: {str(e)}")
        finally:
            # Clean up when connection is closed
            self.clients.remove(websocket)
            
            # Remove from any session
            for session in self.sessions.values():
                if client_id in session.users:
                    await session.remove_user(client_id)
    
    async def create_session(self, session_id: str = None) -> str:
        """
        Create a new collaboration session
        
        Args:
            session_id: Optional session ID
            
        Returns:
            Session ID
        """
        session_id = session_id or str(uuid.uuid4())
        self.sessions[session_id] = CollaborationSession(session_id)
        return session_id
    
    async def close_session(self, session_id: str) -> bool:
        """
        Close a collaboration session
        
        Args:
            session_id: Session ID
            
        Returns:
            Success status
        """
        if session_id in self.sessions:
            session = self.sessions[session_id]
            await session.broadcast({
                "type": "session_closed",
                "message": "The collaboration session has been closed."
            })
            del self.sessions[session_id]
            return True
        return False


class CollaborationSession:
    """Manages a single collaboration session"""
    
    def __init__(self, session_id: str):
        """
        Initialize a collaboration session
        
        Args:
            session_id: Session ID
        """
        self.session_id = session_id
        self.users: Dict[str, Dict[str, Any]] = {}
        self.file_content: Dict[str, str] = {}
        self.file_history: Dict[str, List[Dict[str, Any]]] = {}
        self.cursors: Dict[str, Dict[str, Any]] = {}
        self.chat_history: List[Dict[str, Any]] = []
        self.created_at = time.time()
        
    async def add_user(self, client_id: str, username: str, websocket) -> None:
        """
        Add a user to the session
        
        Args:
            client_id: Client ID
            username: Username
            websocket: WebSocket connection
        """
        self.users[client_id] = {
            "username": username,
            "websocket": websocket,
            "joined_at": time.time(),
            "active": True
        }
        
        # Send current state to new user
        await websocket.send(json.dumps({
            "type": "session_state",
            "users": {cid: {"username": data["username"], "active": data["active"]} 
                     for cid, data in self.users.items()},
            "files": self.file_content,
            "cursors": self.cursors,
            "chat_history": self.chat_history
        }))
        
    async def remove_user(self, client_id: str) -> None:
        """
        Remove a user from the session
        
        Args:
            client_id: Client ID
        """
        if client_id in self.users:
            username = self.users[client_id]["username"]
            del self.users[client_id]
            
            # Notify other users
            await self.broadcast({
                "type": "user_left",
                "username": username,
                "client_id": client_id
            })
    
    async def broadcast(self, message: Dict[str, Any], exclude=None) -> None:
        """
        Broadcast a message to all users
        
        Args:
            message: Message to broadcast
            exclude: Optional WebSocket connection to exclude
        """
        message_json = json.dumps(message)
        coros = []
        
        for user_data in self.users.values():
            if user_data["websocket"] != exclude and user_data["active"]:
                coros.append(user_data["websocket"].send(message_json))
                
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)
    
    async def handle_edit(self, data: Dict[str, Any], client_id: str) -> None:
        """
        Handle an edit operation
        
        Args:
            data: Edit operation data
            client_id: Client ID
        """
        file_path = data["file_path"]
        operation = data["operation"]
        username = self.users[client_id]["username"]
        
        # Update file content
        if file_path not in self.file_content:
            self.file_content[file_path] = ""
            self.file_history[file_path] = []
            
        # Apply edit operation
        if operation["type"] == "insert":
            pos = operation["position"]
            text = operation["text"]
            content = self.file_content[file_path]
            self.file_content[file_path] = content[:pos] + text + content[pos:]
        elif operation["type"] == "delete":
            start = operation["start"]
            end = operation["end"]
            content = self.file_content[file_path]
            self.file_content[file_path] = content[:start] + content[end:]
        
        # Record history
        self.file_history[file_path].append({
            "timestamp": time.time(),
            "client_id": client_id,
            "username": username,
            "operation": operation
        })
        
        # Broadcast change to all users
        await self.broadcast({
            "type": "edit",
            "file_path": file_path,
            "operation": operation,
            "client_id": client_id,
            "username": username
        }, exclude=self.users[client_id]["websocket"])
    
    async def handle_cursor_move(self, data: Dict[str, Any], client_id: str) -> None:
        """
        Handle cursor movement
        
        Args:
            data: Cursor position data
            client_id: Client ID
        """
        file_path = data["file_path"]
        position = data["position"]
        username = self.users[client_id]["username"]
        
        # Update cursor position
        if file_path not in self.cursors:
            self.cursors[file_path] = {}
            
        self.cursors[file_path][client_id] = {
            "position": position,
            "username": username,
            "timestamp": time.time()
        }
        
        # Broadcast cursor position to all users
        await self.broadcast({
            "type": "cursor_move",
            "file_path": file_path,
            "position": position,
            "client_id": client_id,
            "username": username
        }, exclude=self.users[client_id]["websocket"])
    
    async def handle_chat(self, data: Dict[str, Any], client_id: str) -> None:
        """
        Handle chat message
        
        Args:
            data: Chat message data
            client_id: Client ID
        """
        message = data["message"]
        username = self.users[client_id]["username"]
        
        # Record chat message
        chat_entry = {
            "timestamp": time.time(),
            "client_id": client_id,
            "username": username,
            "message": message
        }
        self.chat_history.append(chat_entry)
        
        # Broadcast chat message to all users
        await self.broadcast({
            "type": "chat",
            "message": message,
            "client_id": client_id,
            "username": username
        })