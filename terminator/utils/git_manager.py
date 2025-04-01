"""
Git Manager Module - Provides Git operations and utilities for Terminator IDE
"""

import os
import subprocess
from typing import Tuple, Dict, List, Any, Optional
import logging

class GitManager:
    """Class to manage Git operations for the Terminator IDE"""
    
    @staticmethod
    def check_git_repo(directory: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a directory is a git repository
        
        Args:
            directory: The directory to check
            
        Returns:
            Tuple of (is_repo, repo_root_path)
        """
        try:
            # Try to get the git root directory
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                # This is a git repo, return the root directory
                return True, result.stdout.strip()
            else:
                # Not a git repo
                return False, None
        except Exception as e:
            logging.error(f"Error checking git repository: {str(e)}", exc_info=True)
            return False, None
    
    @staticmethod
    def get_git_status(repo_path: str) -> Dict[str, Any]:
        """
        Get the current Git status
        
        Args:
            repo_path: Path to the git repository
            
        Returns:
            Dict with status information including staged and unstaged changes
        """
        try:
            # Get status in porcelain format for easy parsing
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get the current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the porcelain output
            staged_changes = []
            unstaged_changes = []
            untracked_files = []
            
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                    
                status = line[:2]
                file_path = line[3:]
                
                # Check status indicators
                if status[0] != ' ' and status[0] != '?':
                    # Staged changes
                    staged_changes.append({
                        "file": file_path,
                        "status": status[0]
                    })
                    
                if status[1] != ' ':
                    # Unstaged changes
                    unstaged_changes.append({
                        "file": file_path,
                        "status": status[1]
                    })
                    
                if status == '??':
                    # Untracked files
                    untracked_files.append(file_path)
            
            return {
                "branch": branch_result.stdout.strip(),
                "staged_changes": staged_changes,
                "unstaged_changes": unstaged_changes,
                "untracked_files": untracked_files,
                "clean": len(result.stdout.strip()) == 0
            }
        except Exception as e:
            logging.error(f"Error getting git status: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "branch": "unknown",
                "staged_changes": [],
                "unstaged_changes": [],
                "untracked_files": [],
                "clean": False
            }
    
    @staticmethod
    def commit(repo_path: str, message: str) -> Tuple[bool, str]:
        """
        Create a Git commit
        
        Args:
            repo_path: Path to the git repository
            message: Commit message
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Create the commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip()
        except Exception as e:
            logging.error(f"Error creating git commit: {str(e)}", exc_info=True)
            return False, str(e)
    
    @staticmethod
    def stage_file(repo_path: str, file_path: str) -> Tuple[bool, str]:
        """
        Stage a file for commit
        
        Args:
            repo_path: Path to the git repository
            file_path: Path to the file to stage, relative to repo_path
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Stage the file
            result = subprocess.run(
                ["git", "add", file_path],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                return True, f"Staged {file_path}"
            else:
                return False, result.stderr.strip()
        except Exception as e:
            logging.error(f"Error staging file: {str(e)}", exc_info=True)
            return False, str(e)
    
    @staticmethod
    def unstage_file(repo_path: str, file_path: str) -> Tuple[bool, str]:
        """
        Unstage a file
        
        Args:
            repo_path: Path to the git repository
            file_path: Path to the file to unstage, relative to repo_path
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Unstage the file
            result = subprocess.run(
                ["git", "reset", "HEAD", file_path],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                return True, f"Unstaged {file_path}"
            else:
                return False, result.stderr.strip()
        except Exception as e:
            logging.error(f"Error unstaging file: {str(e)}", exc_info=True)
            return False, str(e)
    
    @staticmethod
    def get_branch_graph(repo_path: str) -> Dict[str, Any]:
        """
        Get a visualization of the git branch structure
        
        Args:
            repo_path: Path to the git repository
            
        Returns:
            Dict with branch and commit information
        """
        try:
            # Get a graphical representation of the branch structure
            graph_result = subprocess.run(
                ["git", "log", "--graph", "--oneline", "--decorate", "--all", "-n", "20"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get a list of all branches
            branches_result = subprocess.run(
                ["git", "branch", "--all"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get the current branch
            current_branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse branch information
            current_branch = current_branch_result.stdout.strip()
            local_branches = []
            remote_branches = []
            
            for line in branches_result.stdout.splitlines():
                branch = line.strip()
                if branch.startswith("* "):
                    # Current branch, already handled
                    pass
                elif branch.startswith("remotes/"):
                    # Remote branch
                    remote_branch = branch.replace("remotes/", "", 1)
                    remote_branches.append(remote_branch)
                else:
                    # Local branch
                    local_branches.append(branch)
            
            # Get recent commits
            commits_result = subprocess.run(
                ["git", "log", "-n", "10", "--pretty=format:%h|%s|%an|%ar"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            commits = []
            for line in commits_result.stdout.splitlines():
                if not line.strip():
                    continue
                    
                parts = line.split("|")
                if len(parts) == 4:
                    commits.append({
                        "short_hash": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3]
                    })
            
            return {
                "graph_output": graph_result.stdout.strip(),
                "branches": {
                    "current_branch": current_branch,
                    "local_branches": local_branches,
                    "remote_branches": remote_branches
                },
                "commits": commits
            }
        except Exception as e:
            logging.error(f"Error getting branch graph: {str(e)}", exc_info=True)
            return {"error": str(e)}
    
    @staticmethod
    def create_branch(repo_path: str, branch_name: str) -> Tuple[bool, str]:
        """
        Create a new git branch
        
        Args:
            repo_path: Path to the git repository
            branch_name: Name of the new branch
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Create the branch
            result = subprocess.run(
                ["git", "branch", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                # Checkout the branch
                checkout_result = subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if checkout_result.returncode == 0:
                    return True, f"Created and switched to branch '{branch_name}'"
                else:
                    return False, checkout_result.stderr.strip()
            else:
                return False, result.stderr.strip()
        except Exception as e:
            logging.error(f"Error creating branch: {str(e)}", exc_info=True)
            return False, str(e)

class CommitDialog(ModalScreen):
    """Git commit dialog screen with Escape key support"""
    
    def __init__(self, repo_path: str):
        """
        Initialize the commit dialog
        
        Args:
            repo_path: Path to the git repository
        """
        super().__init__()
        self.repo_path = repo_path
    
    def compose(self) -> ComposeResult:
        """Create the commit dialog layout"""
        with Container(id="commit-dialog"):
            yield Label("Create Git Commit", id="commit-dialog-title")
            
            # Show files to be committed
            yield Label("Files to be committed:", classes="commit-label")
            yield TextArea(id="staged-files", read_only=True)
            
            # Commit message input
            yield Label("Commit message:", classes="commit-label")
            yield TextArea(id="commit-message", placeholder="Enter commit message...")
            
            with Horizontal(id="commit-buttons"):
                yield Button("Commit", id="commit-btn", variant="success")
                yield Button("Cancel (ESC)", id="cancel-commit-btn", variant="error")
    
    def on_mount(self) -> None:
        """Called when the screen is mounted"""
        # Load staged files
        self._load_staged_files()
        
        # Focus the commit message input
        self.query_one("#commit-message").focus()
        
        # Add key binding for escape key
        self.add_key_binding("escape", "cancel")
    
    def action_cancel(self) -> None:
        """Cancel the commit operation"""
        self.app.pop_screen()
    
    def _load_staged_files(self) -> None:
        """Load the list of staged files"""
        git_status = GitManager.get_git_status(self.repo_path)
        
        # Format staged files for display
        staged_files_text = ""
        
        if git_status.get("staged_changes"):
            for item in git_status.get("staged_changes", []):
                status_char = item.get("status")
                file_path = item.get("file")
                
                if status_char == "A":
                    status = "Added"
                elif status_char == "M":
                    status = "Modified"
                elif status_char == "D":
                    status = "Deleted"
                elif status_char == "R":
                    status = "Renamed"
                else:
                    status = status_char
                    
                staged_files_text += f"{status}: {file_path}\n"
        else:
            staged_files_text = "No files staged for commit"
            
        # Update the staged files display
        self.query_one("#staged-files").text = staged_files_text
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        if button_id == "commit-btn":
            self._do_commit()
        elif button_id == "cancel-commit-btn":
            self.app.pop_screen()
    
    def _do_commit(self) -> None:
        """Perform the git commit operation"""
        # Get the commit message
        message = self.query_one("#commit-message").text.strip()
        
        if not message:
            self.app.notify("Please enter a commit message", severity="warning")
            return
            
        # Create the commit
        success, result = GitManager.commit(self.repo_path, message)
        
        if success:
            self.app.notify(result, severity="success")
            self.app.pop_screen()
        else:
            self.app.notify(f"Commit failed: {result}", severity="error")

# CSS for the commit dialog
COMMIT_DIALOG_CSS = """
#commit-dialog {
    width: 60%;
    padding: 1;
    background: $surface;
    border: solid $accent;
}

#commit-dialog-title {
    text-align: center;
    background: $primary;
    color: $text;
    padding: 1;
    margin-bottom: 1;
    font-weight: bold;
}

#staged-files {
    height: 10;
    margin-bottom: 1;
    background: $surface-darken-1;
}

#commit-message {
    height: 5;
    margin-bottom: 1;
}

.commit-label {
    margin-top: 1;
    margin-bottom: 1;
    font-weight: bold;
}

#commit-buttons {
    width: 100%;
    align-horizontal: center;
    margin-top: 1;
}
"""