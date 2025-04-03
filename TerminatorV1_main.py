#!/usr/bin/env python3
"""
Terminator v1 - A terminal-based Python IDE with integrated AI assistant
Combines code editing, file management, Git integration, and Claude AI assistance
"""

import os
import sys
import asyncio
import aiofiles
import logging
import time
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
# Textual imports
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.events import MouseDown, MouseUp, MouseMove
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Input,
    TextArea,
    Tree,
    DirectoryTree,
    Label,
    Markdown,
    LoadingIndicator,
    TabbedContent,
    TabPane,
)
from textual.widgets.tree import TreeNode
from textual.screen import Screen, ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import DataTable
from textual.binding import Binding
from textual.reactive import reactive
from textual import events, work
from textual.message import Message
from textual.timer import Timer


# For older Textual versions
from textual.theme import Theme
import re

# Import agent and tools modules
from TerminatorV1_agents import initialize_agent_system, run_agent_query, AgentContext
from TerminatorV1_tools import (
    FileSystem,
    CodeAnalyzer,
    GitManager,
    PythonRunner,
    PythonDebugger,
    CollaborationManager,
    CollaborationSession,
)


# Git Commit Dialog Screen
class CommitDialog(ModalScreen):
    """Git commit dialog screen with Escape key support"""

    # Add key bindings for the dialog
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Create the dialog layout"""
        with Container(id="commit-dialog"):
            with Horizontal(id="commit-header"):
                yield Label("Commit Message", classes="title")
                yield Label("Press ESC to cancel", classes="escape-hint")
            # Use None instead of "text" for language to avoid tree-sitter error
            yield TextArea(language=None, id="commit-message")
            with Horizontal():
                yield Button("Cancel", id="cancel-commit", variant="error")
                yield Button("Commit", id="confirm-commit", variant="success")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "cancel-commit":
            self.app.pop_screen()
        elif event.button.id == "confirm-commit":
            # Get the commit message
            commit_message = self.query_one("#commit-message").text
            if not commit_message:
                self.notify("Please enter a commit message", severity="error")
                return

            # Trigger the commit and close the dialog
            self.app.git_commit(commit_message)
            self.app.pop_screen()

    async def action_cancel(self) -> None:
        """Cancel the commit dialog (called when ESC is pressed)"""
        self.app.pop_screen()

    async def on_key(self, event) -> None:
        """Handle key presses in the dialog"""
        # If the Escape key was already handled by bindings, we don't need to do anything
        # This is a fallback in case the binding doesn't work
        if event.key == "escape":
            await self.action_cancel()


# Code Analysis Dialog
class CodeAnalysisDialog(ModalScreen):
    """Code analysis results screen"""

    def compose(self) -> ComposeResult:
        """Create the dialog layout"""
        with Container(id="analysis-dialog"):
            yield Label("Code Analysis Results", classes="title")
            yield ScrollableContainer(
                Markdown("Analyzing code..."), id="analysis-result"
            )
            yield Button("Close", id="close-analysis")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "close-analysis":
            self.app.pop_screen()


# Theme Selection Screen
class ThemeSelectionScreen(ModalScreen):
    """Screen for selecting a TextArea theme"""

    def compose(self) -> ComposeResult:
        """Create the theme selection layout"""
        with Container(id="theme-dialog"):
            yield Label("Select Theme", classes="title")

            # Use a predefined list of known themes
            available_themes = [
                "css",
                "monokai",
                "dracula",
                "github_light",
                "vscode_dark",
            ]

            with ScrollableContainer(id="theme-list"):
                for theme in sorted(available_themes):
                    yield Button(theme, id=f"theme-{theme}", classes="theme-button")

            yield Button("Cancel", id="cancel-theme", variant="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "cancel-theme":
            self.app.pop_screen()
        elif button_id.startswith("theme-"):
            theme_name = button_id[6:]  # Remove "theme-" prefix
            # Call the async method
            await self.app.set_editor_theme(theme_name)
            self.app.pop_screen()


class DiffViewScreen(ModalScreen):
    """Modal screen for displaying code diffs"""

    def __init__(
        self,
        original_content: str,
        modified_content: str,
        title: str = "Code Changes",
        original_title: str = "Original",
        modified_title: str = "Modified",
        highlight_language: str = "python",
    ):
        """
        Initialize the diff view screen

        Args:
            original_content: Original content
            modified_content: Modified content
            title: Title of the diff view
            original_title: Title for the original content panel
            modified_title: Title for the modified content panel
            highlight_language: Language for syntax highlighting
        """
        super().__init__()
        self.original_content = original_content
        self.modified_content = modified_content
        self.screen_title = title
        self.original_title = original_title
        self.modified_title = modified_title
        self.language = highlight_language

        # Calculate the diff
        self.unified_diff = CodeAnalyzer.create_diff(original_content, modified_content)

        # Extract line changes from diff
        self.changed_lines = self._extract_line_changes(self.unified_diff)

    def _extract_line_changes(self, diff_text):
        """
        Extract line numbers that were added or removed in the diff

        Args:
            diff_text: The unified diff text

        Returns:
            Dictionary with original and modified line numbers that changed
        """
        original_changes = set()
        modified_changes = set()

        current_original_line = 0
        current_modified_line = 0

        for line in diff_text.splitlines():
            # Check if this is a hunk header line (e.g., @@ -1,7 +1,9 @@)
            if line.startswith("@@"):
                # Extract line numbers from the hunk header
                # Format is @@ -original_start,original_count +modified_start,modified_count @@
                match = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if match:
                    current_original_line = (
                        int(match.group(1)) - 1
                    )  # Adjust to 0-based indexing
                    current_modified_line = (
                        int(match.group(2)) - 1
                    )  # Adjust to 0-based indexing
            elif line.startswith("-"):
                original_changes.add(current_original_line)
                current_original_line += 1
            elif line.startswith("+"):
                modified_changes.add(current_modified_line)
                current_modified_line += 1
            else:
                # Context line or other (moves both counters)
                current_original_line += 1
                current_modified_line += 1

        return {"original": original_changes, "modified": modified_changes}

    def compose(self) -> ComposeResult:
        """Create the diff view layout"""
        yield Label(self.screen_title, id="diff-title", classes="title")

        with Container(id="diff-view-container"):
            with Horizontal(id="diff-split-view"):
                # Left panel: Original code
                with Vertical(id="diff-original-panel"):
                    yield Label(self.original_title, classes="subtitle")
                    # Use TextArea with line numbers for original content
                    original_editor = yield TextArea(
                        language=self.language,
                        theme="monokai",
                        show_line_numbers=True,
                        read_only=True,
                        id="diff-original-content",
                    )
                    original_editor.text = self.original_content

                # Right panel: Modified code
                with Vertical(id="diff-modified-panel"):
                    yield Label(self.modified_title, classes="subtitle")
                    # Use TextArea with line numbers for modified content
                    modified_editor = yield TextArea(
                        language=self.language,
                        theme="monokai",
                        show_line_numbers=True,
                        read_only=True,
                        id="diff-modified-content",
                    )
                    modified_editor.text = self.modified_content

            # Bottom panel: Unified diff view (optional, can be toggled)
            with Vertical(id="unified-diff-panel", classes="hidden"):
                yield Label("Unified Diff View", classes="subtitle")
                diff_editor = yield TextArea(
                    language="diff",
                    theme="monokai",
                    show_line_numbers=True,
                    read_only=True,
                    id="unified-diff-content",
                )
                diff_editor.text = self.unified_diff

            with Horizontal(id="diff-buttons"):
                yield Button("Apply Changes", id="apply-diff", variant="success")
                yield Button("Toggle Unified View", id="toggle-unified-view")
                yield Button("Close", id="close-diff", variant="error")

    def on_mount(self) -> None:
        """Called when the screen is mounted"""
        # Apply custom CSS classes to highlight changed lines
        self._highlight_changes()

    def _highlight_changes(self) -> None:
        """Highlight the lines that have changed in both panels"""
        # This is a basic implementation - for a production app,
        # you would use proper CSS styling to highlight changes
        try:
            # Create CSS for highlighting original lines that were changed
            original_editor = self.query_one("#diff-original-content")
            for line_num in self.changed_lines["original"]:
                # Apply highlighting to the lines that were changed in the original
                pass  # This would require custom rendering in a full implementation

            # Create CSS for highlighting modified lines that were changed
            modified_editor = self.query_one("#diff-modified-content")
            for line_num in self.changed_lines["modified"]:
                # Apply highlighting to the lines that were changed in the modified
                pass  # This would require custom rendering in a full implementation

        except Exception as e:
            logging.error(f"Error highlighting changes: {str(e)}", exc_info=True)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "close-diff":
            # Close without applying changes
            self.app.pop_screen()
        elif button_id == "apply-diff":
            # Apply the changes and close
            self.app.apply_diff_changes(self.modified_content)
            self.app.pop_screen()
        elif button_id == "toggle-unified-view":
            # Toggle visibility of unified diff panel
            unified_panel = self.query_one("#unified-diff-panel")
            if "hidden" in unified_panel.classes:
                unified_panel.remove_class("hidden")
            else:
                unified_panel.add_class("hidden")


# Debugger Screen
class DebuggerScreen(Screen):
    """Debugger interface screen"""

    def compose(self) -> ComposeResult:
        """Create the debugger layout"""
        yield Header()

        with Horizontal():
            # Left panel: Code with breakpoints
            with Vertical(id="debug-code-panel"):
                yield Label("Source Code", classes="title")
                yield TextArea(language="python", id="debug-code", read_only=True)
                with Horizontal():
                    yield Button("Step Over", id="debug-step-over-btn")
                    yield Button("Step Into", id="debug-step-into-btn")
                    yield Button("Step Out", id="debug-step-out-btn")
                    yield Button("Continue", id="debug-continue-btn")
                    yield Button("Stop", id="debug-stop-btn", variant="error")

            # Right panel: Variable inspector and output
            with Vertical(id="debug-info-panel"):
                yield Label("Variables", classes="title")
                yield DataTable(id="debug-variables")

                yield Label("Call Stack", classes="title")
                yield DataTable(id="debug-stack")

                yield Label("Output", classes="title")
                yield TextArea(id="debug-output", read_only=True)

    def on_mount(self):
        """Initialize the debugger UI"""
        # Set up variables table
        variables_table = self.query_one("#debug-variables")
        variables_table.add_columns("Name", "Type", "Value")

        # Set up call stack table
        stack_table = self.query_one("#debug-stack")
        stack_table.add_columns("Frame", "Function", "File", "Line")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle debug control buttons"""
        button_id = event.button.id

        if button_id == "debug-step-over-btn":
            self.app.debug_step_over()
        elif button_id == "debug-step-into-btn":
            self.app.debug_step_into()
        elif button_id == "debug-step-out-btn":
            self.app.debug_step_out()
        elif button_id == "debug-continue-btn":
            self.app.debug_continue()
        elif button_id == "debug-stop-btn":
            self.app.debug_stop()


# Git Branch Visualization Screen
class BranchVisualizationScreen(Screen):
    """Screen for visualizing Git branches and history"""

    def compose(self) -> ComposeResult:
        """Create the branch visualization layout"""
        yield Header()

        with Horizontal():
            # Left panel: Branch tree
            with Vertical(id="branch-tree-panel"):
                yield Label("Branch Structure", classes="title")
                yield TextArea(language="git", id="branch-graph", read_only=True)
                with Horizontal():
                    yield Button("Refresh", id="refresh-branches-btn")
                    yield Button("Back", id="back-to-main-btn", variant="primary")

            # Right panel: Branch and commit info
            with Vertical(id="branch-info-panel"):
                yield Label("Current Branch", classes="title")
                yield Static("", id="current-branch-info")

                yield Label("All Branches", classes="title")
                yield ScrollableContainer(id="all-branches-container")

                yield Label("Recent Commits", classes="title")
                yield ScrollableContainer(id="recent-commits-container")

                with Horizontal():
                    yield Input(placeholder="New branch name...", id="new-branch-input")
                    yield Button("Create Branch", id="create-branch-btn")

    def on_mount(self):
        """Set up the branch visualization screen"""
        # Load branches and commit data
        self.load_branch_data()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "refresh-branches-btn":
            self.load_branch_data()
        elif button_id == "back-to-main-btn":
            self.app.pop_screen()
        elif button_id == "create-branch-btn":
            self.create_new_branch()

    def load_branch_data(self):
        """Load and display branch and commit data"""
        if not self.app.git_repository:
            self.app.notify("Not a Git repository", severity="error")
            return

        # Get branch graph data
        branch_data = GitManager.get_branch_graph(self.app.git_repository)

        if "error" in branch_data:
            self.app.notify(
                f"Failed to load branch data: {branch_data['error']}", severity="error"
            )
            return

        # Update branch graph visualization
        branch_graph = self.query_one("#branch-graph")
        branch_graph.text = branch_data.get("graph_output", "")

        # Update current branch info
        current_branch_info = self.query_one("#current-branch-info")
        current_branch = branch_data.get("branches", {}).get(
            "current_branch", "unknown"
        )
        current_branch_info.update(f"Current branch: [bold]{current_branch}[/bold]")

        # Update all branches list
        all_branches_container = self.query_one("#all-branches-container")
        all_branches_container.remove_children()

        local_branches = branch_data.get("branches", {}).get("local_branches", [])
        remote_branches = branch_data.get("branches", {}).get("remote_branches", [])

        if local_branches:
            all_branches_container.mount(Label("Local Branches:"))
            for branch in local_branches:
                # Create a button for each branch to switch to it
                all_branches_container.mount(
                    Button(
                        branch, id=f"switch-branch-{branch}", classes="branch-button"
                    )
                )

        if remote_branches:
            all_branches_container.mount(Label("Remote Branches:"))
            for branch in remote_branches:
                # Create a button for each remote branch to check it out
                all_branches_container.mount(
                    Button(
                        branch,
                        id=f"checkout-remote-{branch}",
                        classes="remote-branch-button",
                    )
                )

        # Update recent commits list
        commits_container = self.query_one("#recent-commits-container")
        commits_container.remove_children()

        commits = branch_data.get("commits", [])
        for commit in commits:
            commit_message = commit.get("message", "")
            short_hash = commit.get("short_hash", "")
            author = commit.get("author", "")
            date = commit.get("date", "")

            # Create a button for the commit
            commit_label = f"{short_hash} ({date}) - {commit_message}"
            commits_container.mount(
                Button(
                    commit_label,
                    id=f"view-commit-{short_hash}",
                    classes="commit-button",
                )
            )

    def create_new_branch(self):
        """Create a new branch"""
        if not self.app.git_repository:
            self.app.notify("Not a Git repository", severity="error")
            return

        # Get the branch name
        branch_input = self.query_one("#new-branch-input")
        branch_name = branch_input.value.strip()

        if not branch_name:
            self.app.notify("Please enter a branch name", severity="warning")
            return

        # Create the branch
        success, message = GitManager.create_branch(
            self.app.git_repository, branch_name
        )

        if success:
            self.app.notify(message, severity="success")
            # Refresh the branch data
            self.load_branch_data()
            # Clear the input
            branch_input.value = ""
        else:
            self.app.notify(message, severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "refresh-branches-btn":
            self.load_branch_data()
        elif button_id == "back-to-main-btn":
            self.app.pop_screen()
        elif button_id == "create-branch-btn":
            self.create_new_branch()
        elif button_id.startswith("switch-branch-"):
            # Switch to local branch
            branch_name = button_id[14:]  # Remove "switch-branch-" prefix
            self.switch_branch(branch_name)
        elif button_id.startswith("checkout-remote-"):
            # Checkout remote branch
            branch_name = button_id[16:]  # Remove "checkout-remote-" prefix
            self.switch_branch(branch_name)

    def switch_branch(self, branch_name: str):
        """Switch to a different branch"""
        if not self.app.git_repository:
            self.app.notify("Not a Git repository", severity="error")
            return

        # Switch branch
        success, message = GitManager.switch_branch(
            self.app.git_repository, branch_name
        )

        if success:
            self.app.notify(message, severity="success")
            # Refresh the branch data
            self.load_branch_data()
            # Update Git status in main app
            self.app.update_git_status()
        else:
            self.app.notify(message, severity="error")


# Remote Connection Dialog
class RemoteConnectionDialog(ModalScreen):
    """Dialog for setting up a remote development connection"""

    def compose(self) -> ComposeResult:
        """Create the dialog layout"""
        with Container(id="remote-dialog"):
            yield Label("Remote Connection", classes="title")

            yield Label("Connection Type:")
            with Horizontal():
                yield Button("SSH", id="connection-ssh", variant="primary")
                yield Button("SFTP", id="connection-sftp")

            yield Label("Server Details:")
            yield Input(placeholder="hostname or IP", id="remote-host")
            yield Input(placeholder="username", id="remote-username")
            yield Input(placeholder="port (default: 22)", id="remote-port", value="22")
            yield Input(
                placeholder="password (leave empty for key auth)",
                id="remote-password",
                password=True,
            )

            yield Label("Remote Directory:")
            yield Input(placeholder="/path/to/project", id="remote-path")

            with Horizontal():
                yield Button("Cancel", id="cancel-remote", variant="error")
                yield Button("Connect", id="confirm-remote", variant="success")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "cancel-remote":
            self.app.pop_screen()
        elif button_id == "confirm-remote":
            self.setup_remote_connection()
        elif button_id == "connection-ssh":
            # Highlight SSH button
            self.query_one("#connection-ssh").variant = "primary"
            self.query_one("#connection-sftp").variant = "default"
        elif button_id == "connection-sftp":
            # Highlight SFTP button
            self.query_one("#connection-sftp").variant = "primary"
            self.query_one("#connection-ssh").variant = "default"

    def setup_remote_connection(self):
        """Set up the remote connection"""
        # Get connection details
        host = self.query_one("#remote-host").value
        username = self.query_one("#remote-username").value
        port = self.query_one("#remote-port").value
        password = self.query_one("#remote-password").value
        remote_path = self.query_one("#remote-path").value

        # Validate inputs
        if not host or not username or not remote_path:
            self.app.notify("Please fill in all required fields", severity="error")
            return

        # Determine connection type
        connection_type = "ssh"
        if self.query_one("#connection-sftp").variant == "primary":
            connection_type = "sftp"

        # Configure the remote connection
        self.app.configure_remote(
            connection_type=connection_type,
            host=host,
            username=username,
            port=int(port) if port.isdigit() else 22,
            password=password,
            remote_path=remote_path,
        )

        # Close the dialog
        self.app.pop_screen()


# Remote Files Browser Screen
class RemoteFilesBrowser(Screen):
    """Browser for remote files"""

    def compose(self) -> ComposeResult:
        """Create the remote files browser layout"""
        yield Header()

        with Horizontal():
            # Left panel: Remote files tree
            with Vertical(id="remote-files-panel"):
                with Horizontal():
                    yield Label("Remote Files", classes="title")
                    yield Button("Refresh", id="refresh-remote-btn")
                yield Tree("Remote Files", id="remote-files-tree")
                with Horizontal():
                    yield Button("Download", id="download-remote-btn")
                    yield Button("Upload", id="upload-remote-btn")
                    yield Button(
                        "Disconnect", id="disconnect-remote-btn", variant="error"
                    )
                    yield Button("Back", id="back-from-remote-btn")

            # Right panel: File preview
            with Vertical(id="remote-preview-panel"):
                yield Label("File Preview", classes="title")
                yield TextArea(id="remote-file-preview", read_only=True)

    def on_mount(self):
        """Initialize the remote files browser"""
        # Populate the remote files tree
        self.populate_remote_files()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "refresh-remote-btn":
            self.populate_remote_files()
        elif button_id == "download-remote-btn":
            self.download_selected_file()
        elif button_id == "upload-remote-btn":
            self.app.action_upload_to_remote()
        elif button_id == "disconnect-remote-btn":
            self.app.disconnect_remote()
            self.app.pop_screen()
        elif button_id == "back-from-remote-btn":
            self.app.pop_screen()

    def populate_remote_files(self):
        """Populate the remote files tree"""
        if not self.app.remote_connected:
            self.app.notify("Not connected to remote server", severity="error")
            return

        # In a real implementation, fetch the remote files
        # For now, we'll use a placeholder
        tree = self.query_one("#remote-files-tree")
        tree.clear()

        # Add some dummy remote files
        remote_files = [
            "project/",
            "project/main.py",
            "project/utils.py",
            "project/data/",
            "project/data/config.json",
        ]

        # Create tree nodes
        root = tree.root
        root.expand()

        directories = {}

        for path in sorted(remote_files):
            parts = path.strip("/").split("/")

            if len(parts) == 1:
                # Top-level item
                if path.endswith("/"):
                    # Directory
                    directories[path] = root.add(path, expand=True)
                else:
                    # File
                    root.add_leaf(path)
            else:
                # Nested item
                parent_path = "/".join(parts[:-1]) + "/"
                if parent_path in directories:
                    parent = directories[parent_path]

                    if path.endswith("/"):
                        # Subdirectory
                        directories[path] = parent.add(parts[-1], expand=True)
                    else:
                        # File in directory
                        parent.add_leaf(parts[-1])

        self.app.notify("Remote files refreshed", severity="information")

    def download_selected_file(self):
        """Download the selected remote file"""
        # In a real implementation, download the selected file
        tree = self.query_one("#remote-files-tree")
        node = tree.cursor_node

        if node is None or not node.is_leaf:
            self.app.notify("Please select a file to download", severity="warning")
            return

        # Get the full path of the selected file
        file_path = self.get_node_path(node)

        self.app.notify(
            f"Downloading {file_path}... (simulation)", severity="information"
        )

        # Simulate download
        preview = self.query_one("#remote-file-preview")
        preview.text = f"# Content of {file_path}\n\nThis is a simulated file content."

    def get_node_path(self, node):
        """Get the full path of a tree node"""
        path_parts = []

        # Traverse up to build the path
        current = node
        while (
            current is not None and current != self.query_one("#remote-files-tree").root
        ):
            path_parts.append(current.label)
            current = current.parent

        path_parts.reverse()
        return "/".join(path_parts)

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        """Handle node selection in the tree"""
        node = event.node

        if node.is_leaf:
            # Preview file
            file_path = self.get_node_path(node)

            # In a real implementation, get the file content
            preview = self.query_one("#remote-file-preview")
            preview.text = f"# Content of {file_path}\n\nThis is a simulated file content for a remote file."


# Semantic Search Screen
class SemanticSearchScreen(ModalScreen):
    """Screen for performing semantic code search using natural language"""

    def compose(self) -> ComposeResult:
        """Create the semantic search layout"""
        with Container(id="semantic-search-dialog"):
            yield Label("Semantic Code Search", classes="title")
            yield Input(
                placeholder="Describe what you're looking for...",
                id="semantic-search-input",
            )

            yield Label("Search Results:", id="search-results-label")
            yield ScrollableContainer(id="semantic-results-container")

            with Horizontal():
                yield Button("Search", id="semantic-search-btn", variant="primary")
                yield Button("Cancel", id="cancel-semantic-search", variant="error")

    def on_mount(self):
        """Set up the search screen"""
        self.query_one("#semantic-search-input").focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "semantic-search-btn":
            asyncio.create_task(self.perform_semantic_search())
        elif button_id == "cancel-semantic-search":
            asyncio.create_task(self.app.pop_screen())

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission"""
        if event.input.id == "semantic-search-input":
            asyncio.create_task(self.perform_semantic_search())

    @work
    async def perform_semantic_search(self) -> None:
        """Perform semantic code search using the AI"""
        search_query = self.query_one("#semantic-search-input").value.strip()

        if not search_query:
            self.app.notify("Please enter a search query", severity="warning")
            return

        # Show a loading message
        results_container = self.query_one("#semantic-results-container")
        results_container.remove_children()
        results_container.mount(Static("Searching...", classes="search-loading"))

        # Craft a prompt for the AI to convert the natural language query into semantic search results
        prompt = f"""Perform a semantic code search for the following query:
        
        "{search_query}"
        
        You need to:
        1. Interpret what files or code snippets would best match this natural language query
        2. Analyze the code in the project to find the most relevant matches
        3. Return a list of files and relevant code snippets that match the search intent
        4. Include a brief explanation of why each result matches the query
        
        FORMAT YOUR RESPONSE AS JSON with the following structure:
        {{
            "results": [
                {{
                    "file": "file_path",
                    "snippet": "code snippet",
                    "explanation": "why this matches"
                }}
            ]
        }}
        """

        # Call the AI to perform the search
        try:
            # Get the response from the AI
            result = await run_agent_query(prompt, self.app.agent_context)
            response = result.get("response", "")

            # Extract the JSON from the response
            json_pattern = r"\{[\s\S]*\}"
            matches = re.search(json_pattern, response)

            if matches:
                json_str = matches.group(0)
                search_results = json.loads(json_str)

                # Display the results
                results_container.remove_children()

                if not search_results.get("results"):
                    results_container.mount(
                        Static("No results found.", classes="search-no-results")
                    )
                    return

                # Display each result
                for idx, result in enumerate(search_results.get("results", [])):
                    file_path = result.get("file", "Unknown file")
                    snippet = result.get("snippet", "")
                    explanation = result.get("explanation", "")

                    # Create a button for the file
                    result_container = Container(classes="search-result")
                    result_container.mount(
                        Label(
                            f"Result {idx+1}: {file_path}",
                            classes="search-result-title",
                        )
                    )
                    result_container.mount(
                        Static(explanation, classes="search-result-explanation")
                    )
                    result_container.mount(
                        TextArea(
                            snippet,
                            language="python",
                            classes="search-result-snippet",
                            read_only=True,
                        )
                    )
                    result_container.mount(
                        Button(
                            f"Open {os.path.basename(file_path)}",
                            id=f"open-result-{idx}",
                            classes="search-result-open-btn",
                        )
                    )

                    results_container.mount(result_container)
            else:
                # No JSON found in the response
                results_container.remove_children()
                results_container.mount(
                    Static(
                        "Failed to parse search results. Please try again.",
                        classes="search-error",
                    )
                )

        except Exception as e:
            # Handle search errors
            results_container.remove_children()
            results_container.mount(
                Static(f"Search error: {str(e)}", classes="search-error")
            )


# Collaboration Session Dialog Screen
class CollaborationSessionDialog(ModalScreen):
    """Dialog for starting or joining a collaboration session"""

    def compose(self) -> ComposeResult:
        """Create the collaboration dialog layout"""
        with Container(id="collab-dialog"):
            yield Label("Real-time Collaboration", classes="title")

            with Vertical():
                with Horizontal():
                    yield Label("Username:", classes="label")
                    yield Input(
                        placeholder="Your display name", id="collab-username-input"
                    )

                with Vertical():
                    yield Button(
                        "Create New Session", id="collab-create-btn", variant="primary"
                    )

                    with Horizontal():
                        yield Label("Join Session:", classes="label")
                        yield Input(
                            placeholder="Session ID", id="collab-session-id-input"
                        )
                        yield Button("Join", id="collab-join-btn")

                with Horizontal():
                    yield Button("Cancel", id="collab-cancel-btn", variant="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        username_input = self.query_one("#collab-username-input", Input)
        username = username_input.value

        if not username:
            self.notify("Please enter a username", severity="warning")
            return

        if button_id == "collab-cancel-btn":
            self.dismiss()
        elif button_id == "collab-create-btn":
            # Create a new session
            self.dismiss({"action": "create", "username": username})
        elif button_id == "collab-join-btn":
            # Join an existing session
            session_id_input = self.query_one("#collab-session-id-input", Input)
            session_id = session_id_input.value

            if not session_id:
                self.notify("Please enter a session ID", severity="warning")
                return

            self.dismiss(
                {"action": "join", "username": username, "session_id": session_id}
            )


# Collaboration Screen
class CollaborationScreen(Screen):
    """Real-time collaboration interface screen"""

    def __init__(self, session_details: Dict[str, Any]):
        """
        Initialize the collaboration screen

        Args:
            session_details: Session details including username and session ID
        """
        super().__init__()
        self.session_details = session_details
        self.session_id = session_details.get("session_id", "")
        self.username = session_details.get("username", "")
        self.active_file = ""
        self.collaboration_status = "connecting"
        self.user_list = []

    def compose(self) -> ComposeResult:
        """Create the collaboration layout"""
        yield Header()

        with Horizontal():
            # Left panel: Users and chat
            with Vertical(id="collab-left-panel"):
                yield Label("Collaboration Session", classes="title")
                with Horizontal():
                    yield Label(
                        f"Session ID: {self.session_id}", id="collab-session-id"
                    )
                    yield Button("Copy", id="collab-copy-id-btn")

                yield Label("Connected Users", classes="subtitle")
                yield ScrollableContainer(id="collab-users-container")

                yield Label("Chat", classes="subtitle")
                with Vertical(id="collab-chat-container"):
                    yield ScrollableContainer(id="collab-chat-messages")
                    with Horizontal():
                        yield Input(
                            placeholder="Type a message...", id="collab-chat-input"
                        )
                        yield Button("Send", id="collab-chat-send-btn")

            # Right panel: Shared editor
            with Vertical(id="collab-editor-panel"):
                with Horizontal():
                    yield Label("Shared Editor", classes="title")
                    yield Label("Status: ", classes="label")
                    yield Label("Connecting...", id="collab-status")

                with Horizontal(id="collab-file-select"):
                    yield Label("File:", classes="label")
                    with Container(id="collab-file-dropdown-container"):
                        yield Input(
                            placeholder="Select or open a file", id="collab-file-input"
                        )
                        yield Button("Open", id="collab-open-file-btn")

                yield TextArea(language="python", id="collab-editor")

                with Horizontal():
                    yield Button("Save", id="collab-save-btn")
                    yield Button("End Session", id="collab-end-btn", variant="error")

    def on_mount(self) -> None:
        """Set up the collaboration screen"""
        # Set up the users container
        users_container = self.query_one("#collab-users-container", ScrollableContainer)

        # Add self as first user
        users_container.mount(
            Static(f"👤 {self.username} (You)", classes="collab-user-item self")
        )

        # Initialize the chat container
        chat_container = self.query_one("#collab-chat-messages", ScrollableContainer)
        chat_container.mount(
            Static(
                "📢 Welcome to the collaboration session! You can chat with other users here.",
                classes="collab-chat-system",
            )
        )

        # Set initial status
        self.update_status("Connecting to session...")

        # Connect to collaboration server
        self.connect_to_session()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "collab-copy-id-btn":
            # Copy session ID to clipboard
            # (Textual doesn't have clipboard API, so just notify)
            self.notify(f"Session ID copied: {self.session_id}")
        elif button_id == "collab-chat-send-btn":
            # Send chat message
            self.send_chat_message()
        elif button_id == "collab-open-file-btn":
            # Open file for collaboration
            self.open_file_for_collaboration()
        elif button_id == "collab-save-btn":
            # Save changes
            self.save_collaborative_file()
        elif button_id == "collab-end-btn":
            # End collaboration session
            self.end_collaboration_session()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submitted events"""
        input_id = event.input.id

        if input_id == "collab-chat-input":
            # Send chat message
            self.send_chat_message()

    @work
    async def connect_to_session(self) -> None:
        """Connect to the collaboration session"""
        try:
            # In a real app, this would connect to the WebSocket server
            await asyncio.sleep(1)  # Simulate connection

            self.update_status("Connected")

            # Add some fake users for demo
            self.add_user("Alice", "user1")
            self.add_user("Bob", "user2")

            # Add welcome system message
            chat_container = self.query_one(
                "#collab-chat-messages", ScrollableContainer
            )
            chat_container.mount(
                Static(
                    "📢 Alice and Bob have joined the session.",
                    classes="collab-chat-system",
                )
            )

        except Exception as e:
            self.update_status(f"Connection error: {str(e)}")

    def update_status(self, status: str) -> None:
        """
        Update the collaboration status

        Args:
            status: New status message
        """
        status_label = self.query_one("#collab-status", Label)
        status_label.update(status)
        self.collaboration_status = status

    def add_user(self, username: str, client_id: str) -> None:
        """
        Add a user to the collaboration session

        Args:
            username: User's display name
            client_id: Client ID
        """
        users_container = self.query_one("#collab-users-container", ScrollableContainer)
        users_container.mount(
            Static(f"👤 {username}", classes=f"collab-user-item {client_id}")
        )
        self.user_list.append({"username": username, "client_id": client_id})

    def remove_user(self, client_id: str) -> None:
        """
        Remove a user from the collaboration session

        Args:
            client_id: Client ID
        """
        users_container = self.query_one("#collab-users-container", ScrollableContainer)

        # Find and remove the user element
        for user_element in users_container.query(f".{client_id}"):
            user_element.remove()

        # Remove from user list
        self.user_list = [
            user for user in self.user_list if user["client_id"] != client_id
        ]

    def send_chat_message(self) -> None:
        """Send a chat message"""
        chat_input = self.query_one("#collab-chat-input", Input)
        message = chat_input.value

        if not message:
            # Add notification for empty message
            self.notify("Please enter a message", severity="warning")
            return

        # Add message to chat container
        chat_container = self.query_one("#collab-chat-messages", ScrollableContainer)
        chat_container.mount(Static(f"💬 You: {message}", classes="collab-chat-self"))

        # Clear input
        chat_input.value = ""

        # In a real app, this would send the message to the WebSocket server
        # For demo, add fake responses
        self.add_fake_chat_response(message)

    @work
    async def add_fake_chat_response(self, message: str) -> None:
        """
        Add a fake chat response for demo purposes

        Args:
            message: Original message
        """
        await asyncio.sleep(1)

        # Fake response
        chat_container = self.query_one("#collab-chat-messages", ScrollableContainer)

        if "hello" in message.lower():
            chat_container.mount(
                Static(
                    "💬 Alice: Hi there! How's the coding going?",
                    classes="collab-chat-other",
                )
            )
        elif "help" in message.lower():
            chat_container.mount(
                Static(
                    "💬 Bob: I can help with that! What do you need?",
                    classes="collab-chat-other",
                )
            )
        else:
            chat_container.mount(
                Static(
                    "💬 Alice: Interesting! Let's work on this together.",
                    classes="collab-chat-other",
                )
            )

    def open_file_for_collaboration(self) -> None:
        """Open a file for collaboration"""
        file_input = self.query_one("#collab-file-input", Input)
        file_path = file_input.value

        if not file_path:
            self.notify("Please enter a file path", severity="warning")
            return

        # Update active file
        self.active_file = file_path

        # Update editor with file contents (simulated)
        editor = self.query_one("#collab-editor", TextArea)

        # Simulate loading file
        editor.load_text(
            f"# Collaborative editing of {file_path}\n\ndef main():\n    print('Hello, Collaborators!')\n\nif __name__ == '__main__':\n    main()"
        )

        # In a real app, this would load the file and sync it to all users
        self.notify(f"Opened {file_path} for collaboration")

    def save_collaborative_file(self) -> None:
        """Save the collaborative file"""
        if not self.active_file:
            self.notify("No file is currently active", severity="warning")
            return

        editor = self.query_one("#collab-editor", TextArea)
        content = editor.text

        # In a real app, this would save the file
        self.notify(f"Saved {self.active_file} successfully")

    def end_collaboration_session(self) -> None:
        """End the collaboration session"""
        # In a real app, this would notify all users and close the WebSocket connection
        self.notify("Ending collaboration session...")
        self.app.pop_screen()


# Collaboration User Presence Indicator Widget
class UserPresenceIndicator(Static):
    """Widget to show user cursor position in collaborative editing"""

    def __init__(self, username: str, client_id: str, color: str = "#3498db"):
        """
        Initialize the user presence indicator

        Args:
            username: User's display name
            client_id: Client ID
            color: User's color
        """
        super().__init__()
        self.username = username
        self.client_id = client_id
        self.color = color
        self.position = (0, 0)  # (line, column)

    def on_mount(self) -> None:
        """Set up the user presence indicator"""
        self.update_style()

    def update_position(self, position: tuple[int, int]) -> None:
        """
        Update the cursor position

        Args:
            position: New position (line, column)
        """
        self.position = position
        self.update_style()

    def update_style(self) -> None:
        """Update the indicator's style based on position"""
        # In a real app, this would calculate the actual UI position from editor coordinates
        self.styles.background = self.color
        self.styles.color = "#ffffff"
        self.update(f"👤 {self.username}")

    def render(self) -> str:
        """Render the indicator"""
        return f"👤 {self.username}"


# Command Palette Screen
class CommandPalette(ModalScreen):
    """Command palette screen for quick access to commands"""

    def __init__(self):
        super().__init__()
        self.commands = {
            "Save": "save",
            "Open": "open",
            "Run": "run",
            "Format Code": "format_code",
            "Git Commit": "git_commit",
            "Git Pull": "git_pull",
            "Git Push": "git_push",
            "Toggle Split View": "toggle_split_view",
            "Switch Editor": "switch_editor",
            "Toggle Terminal": "toggle_terminal",
            "Analyze Code": "analyze_code",
            "AI Request": "ai_request",
            "Quit": "quit",
        }

    def compose(self) -> ComposeResult:
        """Create the command palette layout"""
        with Container(id="command-palette"):
            yield Label("Command Palette", classes="title")
            yield Input(
                placeholder="Search commands...",
                id="command-search",
                suggester=SuggestFromList(list(self.commands.keys())),
            )
            yield ScrollableContainer(id="command-list")

    def on_mount(self):
        """Called when screen is mounted"""
        # Focus the search box
        self.query_one("#command-search").focus()

        # Display all commands initially
        self.display_commands(list(self.commands.keys()))

    def display_commands(self, commands: List[str]):
        """Display a filtered list of commands"""
        command_list = self.query_one("#command-list")
        command_list.remove_children()

        for command in commands:
            command_list.mount(Button(command, id=f"cmd-{self.commands[command]}"))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes to filter commands"""
        search_text = event.value.lower()

        # Filter commands
        if search_text:
            filtered_commands = [
                cmd for cmd in self.commands.keys() if search_text in cmd.lower()
            ]
        else:
            filtered_commands = list(self.commands.keys())

        # Update the display
        self.display_commands(filtered_commands)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle command selection"""
        button_id = event.button.id

        if button_id.startswith("cmd-"):
            command = button_id[4:]  # Remove "cmd-" prefix
            self.app.action(command)
            self.app.pop_screen()


# Main application class
class TerminatorApp(App):
    """
    Terminator - A terminal-based Python IDE with AI superpowers
    """

    # Event classes
    class CodeAnalysisComplete(Message):
        """Event fired when code analysis is complete"""

        def __init__(self, analysis_result: str) -> None:
            self.analysis_result = analysis_result
            super().__init__()

    # CSS section for the app

    CSS = """
        /* Panel layout */
        #main-layout {
            height: 100%;
        }
        
        #sidebar {
            width: 20%;
            min-width: 20;
            max-width: 40%;
            background: $surface-darken-1;
        }
        
        #editor-container {
            width: 60%;
            min-width: 30%;
            max-width: 80%;
        }
        
        #ai-panel {
            width: 20%;
            min-width: 15%;
            max-width: 40%;
        }
        
        /* Gutter styles for resizing */
        .gutter {
            width: 1;
            background: $accent-darken-2;
            color: $text-muted;
            text-align: center;
            transition: background 0.1s;
        }
        
        .gutter:hover {
            background: $accent;
            color: $text;
        }
        
        /* Real-time Collaboration Styles */
        #collab-dialog {
            background: $surface;
            padding: 1;
            border: solid $accent;
            min-width: 50%;
            max-width: 80%;
            margin: 0 1;
        }
        
        #collab-left-panel {
            width: 30%;
            min-width: 20;
            background: $surface-darken-1;
            padding: 1;
        }
        
        #collab-editor-panel {
            width: 70%;
            padding: 1;
        }
        
        #collab-users-container {
            height: 20%;
            border: solid $panel-darken-1;
            padding: 1;
            margin-bottom: 1;
        }
        
        #collab-chat-messages {
            height: 60%;
            border: solid $panel-darken-1;
            padding: 1;
            margin-bottom: 1;
        }
        
        #collab-editor {
            height: 80%;
            border: solid $panel-darken-1;
        }
        
        .collab-user-item {
            padding: 1 2;
            margin: 1 0;
            border: solid $accent;
        }
        
        .collab-user-item.self {
            background: $accent-darken-2;
            color: $text;
        }
        
        .collab-chat-system {
            color: $text-muted;
            padding: 1;
        }
        
        .collab-chat-self {
            background: $accent-darken-2;
            padding: 1 2;
            margin: 1 0;
            border: solid $accent;
            text-align: right;
        }
        
        .collab-chat-other {
            background: $panel-darken-2;
            padding: 1 2;
            margin: 1 0;
            border: solid $panel-darken-1;
        }
        
        #ai-panel {
            width: 30%;
            min-width: 30;
            border-left: solid $primary;
        }
        
        #file-explorer {
            height: 60%;
            border-bottom: solid $primary;
        }
        
        #git-status {
            height: 40%;
        }
        
        #editor-split-view {
            height: 100%;
        }
        
        #editor-primary {
            height: 100%;
            width: 100%;
        }
        
        #editor-secondary {
            height: 100%;
            width: 50%;
            border-left: solid $primary;
        }
        
        #editor-secondary.hidden {
            display: none;
        }
        
        .split-view #editor-primary {
            width: 50%;
        }
        
        .multi-cursor .cursor {
            background: $accent;
        }
        
        #editor-tabs {
            height: 3;
        }
        
        #editor-content, #terminal-content {
            height: 100%;
        }
        
        #terminal-content.hidden {
            display: none;
        }
        
        #terminal-output {
            height: 85%;
            background: $surface-darken-2;
            color: $text;
        }
        
        #terminal-input {
            width: 80%;
        }
        
        #terminal-execute-btn {
            width: 20%;
            background: $success;
        }
        
        #ai-output {
            height: 75%;
            border-bottom: solid $primary;
            overflow-y: scroll;
        }
        
        #ai-input {
            height: 25%;
        }
        
        .title {
            background: $primary;
            color: $text;
            padding: 1 2;
            text-align: center;
            text-style: bold;
        }
        
        Button {
            margin: 1 1;
        }
        
        #run-btn {
            background: $success;
        }
        
        #ai-submit {
            background: $accent;
        }
        
        /* Modal dialog styling */
        #commit-dialog, #analysis-dialog, #command-palette {
            background: $surface;
            padding: 1;
            border: solid $primary;
            height: 60%;
            width: 60%;
            margin: 2 2;
        }
        
        #command-palette {
            height: 50%;
            width: 50%;
        }
        
        #command-search {
            margin-bottom: 1;
            border: solid $primary;
        }
        
        #command-list {
            height: 100%;
            overflow-y: auto;
        }
        
        #command-list Button {
            width: 100%;
            margin: 0 0 1 0;
            text-align: left;
        }
        
        /* Debugger styling */
        #debug-code-panel {
            width: 60%;
            height: 100%;
        }
        
        #debug-info-panel {
            width: 40%;
            height: 100%;
            border-left: solid $primary;
        }
        
        #debug-code {
            height: 80%;
        }
        
        #debug-variables, #debug-stack {
            height: 30%;
            margin-bottom: 1;
        }
        
        #debug-output {
            height: 35%;
        }
        
        .current-debug-line {
            background: $accent-lighten-2;
        }
        
        .breakpoint-line {
            background: $error-lighten-2;
        }
        
        /* Branch visualization styling */
        #branch-tree-panel {
            width: 60%;
            height: 100%;
        }
        
        #branch-info-panel {
            width: 40%;
            height: 100%;
            border-left: solid $primary;
        }
        
        #branch-graph {
            height: 85%;
            background: $surface-darken-2;
        }
        
        #all-branches-container, #recent-commits-container {
            height: 30%;
            margin-bottom: 1;
            overflow-y: auto;
        }
        
        .branch-button {
            background: $success-darken-1;
            margin: 0 0 1 0;
            width: 100%;
            text-align: left;
        }
        
        .remote-branch-button {
            background: $accent-darken-1;
            margin: 0 0 1 0;
            width: 100%;
            text-align: left;
        }
        
        .commit-button {
            background: $surface-darken-1;
            margin: 0 0 1 0;
            width: 100%;
            text-align: left;
        }
        
        /* Remote development styling */
        #remote-dialog {
            background: $surface;
            padding: 1;
            border: solid $primary;
            height: 70%;
            width: 60%;
            margin: 2 2;
        }
        
        #remote-files-panel {
            width: 60%;
            height: 100%;
        }
        
        #remote-preview-panel {
            width: 40%;
            height: 100%;
            border-left: solid $primary;
        }
        
        #remote-files-tree {
            height: 80%;
            margin-bottom: 1;
            overflow-y: auto;
        }
        
        #remote-file-preview {
            height: 95%;
        }
        
        /* Semantic search styling */
        #semantic-search-dialog {
            background: $surface;
            padding: 1;
            border: solid $primary;
            height: 80%;
            width: 80%;
            margin: 2 2;
        }
        
        #semantic-search-input {
            margin-bottom: 1;
            border: solid $primary;
        }
        
        #semantic-results-container {
            height: 85%;
            margin-bottom: 1;
            overflow-y: auto;
        }
        
        .search-result {
            margin-bottom: 2;
            border: solid $primary;
            padding: 1;
        }
        
        .search-result-title {
            background: $primary-darken-1;
            padding: 0 1;
            margin-bottom: 1;
        }
        
        .search-result-explanation {
            margin-bottom: 1;
            padding: 0 1;
            color: $text-muted;
        }
        
        .search-result-snippet {
            height: 10;
            margin-bottom: 1;
            background: $surface-darken-1;
        }
        
        .search-result-open-btn {
            background: $success;
        }
        
        .search-loading {
            text-align: center;
            margin-top: 2;
            color: $text-muted;
        }
        
        .search-error {
            text-align: center;
            margin-top: 2;
            color: $error;
        }
        
        /* Diff view styling */
        #diff-view-container {
            background: $surface;
            padding: 1;
            border: solid $primary;
            height: 90%;
            width: 95%;
            margin: 1 2;
        }
        
        #diff-split-view {
            height: 80%;
            margin-bottom: 1;
        }
        
        #diff-original-panel {
            width: 50%;
            height: 100%;
            border-right: solid $primary;
            padding-right: 1;
        }
        
        #diff-modified-panel {
            width: 50%;
            height: 100%;
            padding-left: 1;
        }
        
        #unified-diff-panel {
            height: 30%;
            margin-top: 1;
            border-top: solid $primary;
            padding-top: 1;
        }
        
        #diff-buttons {
            margin-top: 1;
            height: 3;
            align: center middle;
        }
        
        #diff-original-content .line-deleted {
            background: rgba(255, 0, 0, 0.2);
            color: $error;
        }
        
        #diff-modified-content .line-added {
            background: rgba(0, 255, 0, 0.2);
            color: $success;
        }
        
        #diff-title {
            text-align: center;
            background: $primary;
            color: $text;
            margin-bottom: 1;
        }
        
        .subtitle {
            background: $primary-darken-2;
            color: $text;
            text-align: center;
            margin-bottom: 1;
        }
        
        /* Git commit dialog styling */
        #commit-header {
            width: 100%;
            margin-bottom: 1;
        }
        
        .escape-hint {
            color: $text-muted;
            text-align: right;
            padding-right: 1;
            width: 50%;
        }
        
        /* Resizable panel styling */
        #main-layout {
            width: 100%;
            height: 100%;
        }
        
        #sidebar {
            width: 20%;
            min-width: 10%;
            max-width: 40%;
        }
        
        #editor-container {
            width: 60%;
            min-width: 30%;
            max-width: 80%;
        }
        
        #ai-panel {
            width: 20%;
            min-width: 10%;
            max-width: 40%;
        }
        
        .panel {
            overflow: auto;
        }
        
        .gutter {
            background: $primary;
            color: $text;
            width: 1;
            text-align: center;
            margin: 0 1;
        }
                
        .search-no-results {
            text-align: center;
            margin-top: 2;
            color: $warning;
        }
        
        #commit-message {
            height: 80%;
            margin: 1;
        }
        
        #analysis-result {
            height: 85%;
            margin: 1;
            overflow-y: scroll;
        }
        
        /* Status indicators */
        .git-status {
            color: $success;
        }
        
        .git-modified {
            color: $warning;
        }
        
        .git-untracked {
            color: $error;
        }
        
        /* AI styling */
        .ai-thinking {
            color: $accent;
            text-style: italic;
        }
        
        .ai-response {
            border-left: solid $primary;
            padding-left: 1;
        }
        
        .code-block {
            background: $surface-darken-2;
            margin: 1;
            padding: 1;
        }
        /* Add these to your CSS section */

        #theme-dialog {
            background: $surface;
            padding: 1;
            border: solid $primary;
            height: 60%;
            width: 40%;
            margin: 2 2;
        }

        #theme-list {
            height: 80%;
            overflow-y: auto;
        }

        .theme-button {
            width: 100%;
            margin: 0 0 1 0;
            text-align: left;
        }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+o", "open", "Open"),
        Binding("f5", "run", "Run"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+g", "git_commit", "Git"),
        Binding("ctrl+r", "ai_request", "AI"),
        Binding("ctrl+d", "add_multi_cursor", "Multi-cursor"),
        Binding("ctrl+k", "toggle_split_view", "Split View"),
        Binding("ctrl+tab", "switch_editor", "Switch Editor"),
        Binding("ctrl+t", "toggle_terminal", "Terminal"),
        Binding("ctrl+p", "show_command_palette", "Command Palette"),
        Binding("ctrl+space", "code_completion", "AI Code Completion"),
        Binding("f9", "toggle_breakpoint", "Toggle Breakpoint"),
        Binding("f10", "debug_current_file", "Debug"),
        Binding("ctrl+b", "show_branch_visualization", "Git Branches"),
        Binding("ctrl+shift+p", "toggle_pair_programming", "AI Pair Programming"),
        Binding("ctrl+shift+r", "connect_remote", "Remote Development"),
        Binding("ctrl+shift+c", "start_collaboration", "Collaborate"),
    ]

    # Track application state
    current_file = reactive(None)
    git_repository = reactive(None)
    editor_theme = reactive("monokai")

    # Add these variables to your class
    _last_status_update_time = 0
    _status_update_debounce = 0.5  # seconds

    # Define screens
    SCREENS = {
        "commit": CommitDialog,
        "analysis": CodeAnalysisDialog,
        "command_palette": CommandPalette,
        "debugger": DebuggerScreen,
        "branch_visualization": BranchVisualizationScreen,
        "remote_connection": RemoteConnectionDialog,
        "remote_browser": RemoteFilesBrowser,
        "theme_selection": ThemeSelectionScreen,
        "diff_view": DiffViewScreen,
    }

    def compose(self) -> ComposeResult:
        """Create the UI layout with resizable panels"""
        yield Header()

        # Main layout with resizable panels using the gutter parameter
        # This horizontal container will have resizable children
        with Horizontal(id="main-layout"):
            # Left sidebar with file explorer and git status - initially 20% width
            with Vertical(id="sidebar", classes="panel"):
                yield Label("File Explorer", classes="title")
                yield DirectoryTree(".", id="file-explorer")

                yield Label("Git Status", classes="title")
                with Vertical(id="git-status"):
                    yield Static("", id="git-output")
                    with Horizontal():
                        yield Button("Commit", id="commit-btn")
                        yield Button("Pull", id="pull-btn")
                        yield Button("Push", id="push-btn")
                        yield Button("Branches", id="branches-btn")

            # Resizer element between sidebar and editor
            yield Static("|", classes="gutter")

            # Center code editor and terminal - initially 60% width
            with Vertical(id="editor-container", classes="panel"):
                # Use TabPane directly instead of add_pane method
                with TabbedContent(id="editor-tabs"):
                    with TabPane("Editor", id="editor-tab-pane"):
                        yield Static(id="editor-tab")
                    with TabPane("Terminal", id="terminal-tab-pane"):
                        yield Static(id="terminal-tab")

                # Editor Tab
                with Container(id="editor-content"):
                    yield Label("Code Editor", classes="title")
                    with Horizontal(id="editor-split-view"):
                        
                        # Check if we have syntax extras before trying to use code_editor
                        try:
                            import tree_sitter_languages

                            # If syntax highlighting is available, use code_editor
                            # Create a Theme object for the editors
                            try:
                                theme_obj = Theme("monokai")
                            except Exception:
                                # Fallback for newer Textual versions that might use string directly
                                theme_obj = "monokai"

                            theme_str = "monokai"  # Default theme name as string

                            yield TextArea.code_editor(
                                language="python",
                                theme=theme_str,
                                show_line_numbers=True,
                                tab_behavior="indent",
                                id="editor-primary",
                            )
                            yield TextArea.code_editor(
                                language="python",
                                theme=theme_str,
                                show_line_numbers=True,
                                tab_behavior="indent",
                                id="editor-secondary",
                                classes="hidden",
                            )
                        except ImportError:
                            # Fall back to standard TextArea if syntax highlighting isn't available
                            yield TextArea(language="python", id="editor-primary")
                            yield TextArea(
                                language="python",
                                id="editor-secondary",
                                classes="hidden",
                            )
                    with Horizontal():
                        yield Button("Run", id="run-btn")
                        yield Button("Debug", id="debug-btn")
                        yield Button("Save", id="save-btn")
                        yield Button("Format", id="format-btn")
                        yield Button("Split View", id="split-view-btn")
                        yield Button("Theme", id="theme-btn")
                        yield Button(
                            "Pair Program", id="pair-program-btn", variant="primary"
                        )

                # Terminal Tab
                with Container(id="terminal-content", classes="hidden"):
                    yield Label("Integrated Terminal", classes="title")
                    yield TextArea(
                        language="bash", id="terminal-output", read_only=True
                    )
                    with Horizontal():
                        yield Input(
                            placeholder="Enter terminal command...", id="terminal-input"
                        )
                        yield Button("Execute", id="terminal-execute-btn")
                        yield Button("Remote", id="open-remote-btn")

            # Resizer element between editor and AI panel
            yield Static("|", classes="gutter")

            # Right AI panel - initially 20% width
            with Vertical(id="ai-panel", classes="panel"):
                yield Label("AI Assistant", classes="title")
                yield Markdown(
                    "Welcome to Terminator v1! Ask me anything about your code.",
                    id="ai-output",
                )
                with Vertical(id="ai-input"):
                    yield Input(placeholder="Ask the AI...", id="ai-prompt")
                    yield Button("Submit", id="ai-submit")

        yield Footer()

    def get_language_from_extension(self, extension):
        """Map file extension to language for syntax highlighting"""
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".md": "markdown",
            ".markdown": "markdown",
            ".txt": None,  # Use None for plain text files
            ".xml": "xml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".rs": "rust",
            ".go": "go",
            ".sh": "bash",
            ".bash": "bash",
            ".sql": "sql",
            ".java": "java",
            # Add more mappings as needed
        }
        # Return None for text files instead of "text" to avoid tree-sitter error
        return extension_map.get(extension, None)

    @work(thread=False)
    async def set_editor_theme(self, theme_name: str) -> None:
        """Set the theme for all editors asynchronously"""
        try:
            # Store the theme name as string
            self.current_theme_name = theme_name

            # Apply theme to primary editor
            primary_editor = self.query_one("#editor-primary")
            primary_editor.theme = theme_name

            # Apply theme to secondary editor if it exists
            try:
                secondary_editor = self.query_one("#editor-secondary")
                secondary_editor.theme = theme_name
            except Exception:
                pass  # Secondary editor might not exist yet

            self.notify(f"Theme changed to: {theme_name}", severity="information")
        except Exception as e:
            self.notify(f"Error setting theme: {str(e)}", severity="error")

    def show_diff_view(
        self,
        original_content: str,
        modified_content: str,
        title: str = "Code Changes",
        language: str = "python",
        original_title: str = "Original",
        modified_title: str = "Modified",
    ) -> None:
        """
        Show the diff view popup for comparing original and modified content

        Args:
            original_content: The original content
            modified_content: The modified content
            title: Title for the diff view
            language: Language for syntax highlighting
            original_title: Title for the original content panel
            modified_title: Title for the modified content panel
        """
        try:
            # Create a wrapper function for the async callback
            async def apply_callback(content):
                await self.apply_diff_changes(content)

            # Create the diff screen with the async callback
            diff_screen = DiffViewScreen(
                original_content=original_content,
                modified_content=modified_content,
                title=title,
                original_title=original_title,
                modified_title=modified_title,
                highlight_language=language,
                on_apply_callback=apply_callback,  # Pass the async wrapper
            )

            # Push the screen
            self.push_screen(diff_screen)

        except Exception as e:
            self.notify(f"Error showing diff view: {str(e)}", severity="error")
            logging.error(f"Error showing diff view: {str(e)}", exc_info=True)

    def show_code_suggestion(
        self,
        original_content: str,
        new_content: str,
        title: str = "AI Suggested Changes",
    ) -> None:
        """
        Show code suggestions from the AI agent with a diff view
    
        Args:
            original_content: The original file content
            new_content: The suggested new content
            title: Title for the diff view popup
        """
        try:
            # Create a wrapper function for the async callback
            async def apply_callback(content):
                await self.apply_diff_changes(content)
                
            # Create a diff view screen with the provided content
            diff_screen = DiffViewScreen(
                original_content=original_content,
                modified_content=new_content,
                title=title,
                original_title="Current Code",
                modified_title="AI Suggestion",
                highlight_language=self._get_language_from_filename(self.current_file)
                if self.current_file
                else "python",
                on_apply_callback=apply_callback
            )
    
            # Push the screen
            self.push_screen(diff_screen)
    
            # Show a notification about the suggestion
            self.notify(
                "AI has suggested changes. Review and apply if desired.",
                severity="information",
            )
    
        except Exception as e:
            self.notify(f"Error showing code suggestion: {str(e)}", severity="error")
            logging.error(f"Error showing code suggestion: {str(e)}", exc_info=True)

    def _get_language_from_filename(self, filename: str) -> str:
        """
        Get the language for syntax highlighting based on file extension

        Args:
            filename: The filename to check

        Returns:
            Language identifier for syntax highlighting
        """
        if not filename:
            return "python"

        ext = os.path.splitext(filename)[1].lower()

        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".md": "markdown",
            ".xml": "xml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".sh": "bash",
            ".c": "c",
            ".cpp": "cpp",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
        }

        return language_map.get(ext, "python")

    @work(thread=True)
    async def apply_diff_changes(self, new_content: str) -> None:
        """
        Apply changes from diff view to the current file
    
        Args:
            new_content: The new content to apply
        """
        if not self.current_file:
            self.notify("No file selected to save changes to", severity="error")
            return
    
        try:
            # Get the active editor
            if self.active_editor == "primary":
                editor = self.query_one("#editor-primary")
            else:
                editor = self.query_one("#editor-secondary")
    
            # Update the editor content
            if hasattr(editor, "load_text"):
                editor.load_text(new_content)
            else:
                editor.text = new_content
    
            # Save the changes to the file asynchronously
            async with aiofiles.open(self.current_file, "w", encoding="utf-8") as file:
                await file.write(new_content)
    
            self.notify(
                f"Changes applied and saved to {os.path.basename(self.current_file)}",
                severity="success",
            )
    
            # Update git status if applicable
            if hasattr(self, "git_repository") and self.git_repository:
                asyncio.create_task(self.update_git_status())
    
        except Exception as e:
            self.notify(f"Error applying changes: {str(e)}", severity="error")
            logging.error(f"Error applying changes: {str(e)}", exc_info=True)

    def ensure_syntax_dependencies(self):
        """Ensure the syntax highlighting dependencies are installed"""
        try:
            # Try to import tree_sitter_languages, which is part of textual[syntax]
            import importlib

            importlib.import_module("tree_sitter_languages")
            return True
        except ImportError:
            # Don't try to highlight the word 'syntax' in the notification
            self.notify(
                "Syntax highlighting requires textual[syntax] package",
                severity="warning",
            )
            return False

    def initialize_agent_context(self):
        """Initialize the agent context with proper validation"""
        try:
            # Ensure current_directory is valid
            if not hasattr(self, "current_directory") or not self.current_directory:
                self.current_directory = os.getcwd()
                logging.info(
                    f"Set default current directory to: {self.current_directory}"
                )

            # Validate the directory exists
            if not os.path.exists(self.current_directory):
                logging.error(
                    f"Current directory doesn't exist: {self.current_directory}"
                )
                self.notify(
                    f"Invalid working directory: {self.current_directory}",
                    severity="error",
                )
                self.current_directory = os.getcwd()
                logging.info(
                    f"Falling back to current working directory: {self.current_directory}"
                )

            # Create agent context with validated directory
            self.agent_context = AgentContext(current_dir=self.current_directory)
            logging.info(
                f"Agent context initialized with directory: {self.current_directory}"
            )

            # Verify context was created correctly
            if not self.agent_context or not hasattr(self.agent_context, "current_dir"):
                logging.error("Failed to create valid agent context")
                self.notify("Failed to initialize AI agent context", severity="error")
                return False

            return True

        except Exception as e:
            logging.error(f"Error initializing agent context: {str(e)}", exc_info=True)
            self.notify(
                f"Error initializing AI agent context: {str(e)}", severity="error"
            )
            return False

    def on_mount(self):
        """Called when the app is mounted"""
        # Set up initial directory
        self.current_directory = os.getcwd()

        # Initialize editor state tracking
        self.active_editor = "primary"
        self.split_view_active = False
        self.multi_cursor_positions = []
        self.active_tab = "editor"
        self.terminal_history = []

        # Initialize resizable panel tracking
        self.resizing = False
        self.resizing_panel = None
        self.start_x = 0
        self.current_widths = {
            "sidebar": 20,  # Default sidebar width 20%
            "editor-container": 60,  # Default editor width 60%
            "ai-panel": 20,  # Default AI panel width 20%
        }

        # Check for syntax highlighting dependencies
        self.ensure_syntax_dependencies()

        # Initialize debugger state
        self.debug_session = None
        self.breakpoints = {}  # Format: {file_path: [line_numbers]}

        # Initialize AI pair programming state
        self.pair_programming_active = False
        self.pair_programming_timer = None
        self.last_edit_time = time.time()

        # Initialize remote development state
        self.remote_connected = False
        self.remote_config = {
            "connection_type": None,
            "host": None,
            "username": None,
            "port": 22,
            "password": None,
            "remote_path": None,
        }

        # Initialize logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("terminator.log"), logging.StreamHandler()],
        )

        # Initialize the agent system
        self.notify("Initializing AI agents...")
        agent_initialized = initialize_agent_system()
        if agent_initialized:
            self.notify("AI agents ready", severity="information")
        else:
            self.notify(
                "Failed to initialize AI agents. Check OpenAI API key.",
                severity="error",
            )

        # Initialize agent context
        if self.initialize_agent_context():
            self.notify("AI agent context ready", severity="information")
        else:
            self.notify(
                "Failed to initialize AI agent context - some AI features may not work correctly",
                severity="error",
            )

        # Focus the file explorer by default
        self.query_one("#file-explorer").focus()

        # Check for git repository
        self.check_git_repository()

        # Initialize AI panel
        self.initialize_ai_panel()

        # Apply initial panel widths
        self._apply_panel_widths()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission events for all inputs in the app"""
        input_id = event.input.id

        if input_id == "ai-prompt":
            # Execute AI request when Enter is pressed in the prompt input
            asyncio.create_task(self.action_ai_request())
        elif input_id == "terminal-input":
            # Execute terminal command when Enter is pressed
            asyncio.create_task(self.execute_terminal_command())
        elif input_id == "command-search":
            # Handle command palette search submission
            commands = self.screen.query_one("#command-list").query(Button)
            if commands:
                # Execute the first command in the filtered list
                command_id = commands[0].id
                if command_id.startswith("cmd-"):
                    command = command_id[4:]  # Remove "cmd-" prefix
                    self.action(command)
                    self.pop_screen()

    def check_git_repository(self):
        """Check if the current directory is a git repository"""
        is_repo, repo_root = GitManager.check_git_repo(self.current_directory)

        if is_repo:
            self.git_repository = repo_root
            self.update_git_status()
        else:
            self.git_repository = None
            git_output = self.query_one("#git-output")
            git_output.update("No Git repository found")

    def _apply_panel_widths(self):
        """Apply the current panel widths to the UI"""
        try:
            # Apply widths to each panel
            sidebar = self.query_one("#sidebar")
            editor = self.query_one("#editor-container")
            ai_panel = self.query_one("#ai-panel")

            sidebar.styles.width = f"{self.current_widths['sidebar']}%"
            editor.styles.width = f"{self.current_widths['editor-container']}%"
            ai_panel.styles.width = f"{self.current_widths['ai-panel']}%"
        except Exception as e:
            logging.error(f"Error applying panel widths: {str(e)}", exc_info=True)

    async def on_static_click(self, event) -> None:
        """Handle click events on static elements, including gutters"""
        if event.static.has_class("gutter"):
            # Determine which panel is being resized
            if event.static.query_one("#sidebar", default=None) is not None:
                self.resizing_panel = "sidebar"
            elif event.static.query_one("#editor-container", default=None) is not None:
                self.resizing_panel = "editor-container"
            else:
                self.resizing_panel = None
                return

            # Start resizing
            self.resizing = True
            self.start_x = event.screen_x

    async def on_mouse_down(self, event: MouseDown) -> None:
        """Handle mouse down events for gutter resizing"""
        # Check if we clicked on a gutter element
        target = self.get_widget_at(event.screen_x, event.screen_y)

        if target and isinstance(target, Static) and target.has_class("gutter"):
            # Find the adjacent panels for this gutter
            gutter_idx = list(self.query(".gutter")).index(target)

            if gutter_idx == 0:
                # First gutter - between sidebar and editor
                self.resizing_panel = "sidebar"
            elif gutter_idx == 1:
                # Second gutter - between editor and AI panel
                self.resizing_panel = "editor-container"

            # Start resizing
            self.resizing = True
            self.start_x = event.screen_x

            # Capture the mouse to receive events outside the gutter
            self.capture_mouse()

    async def on_mouse_up(self, event: MouseUp) -> None:
        """Handle mouse up events to stop resizing"""
        if self.resizing:
            self.resizing = False
            self.resizing_panel = None

            # Release the mouse capture
            self.release_mouse()

    async def on_mouse_move(self, event: MouseMove) -> None:
        """Handle mouse move events for panel resizing"""
        if not self.resizing or not self.resizing_panel:
            return

        # Calculate movement
        delta_x = event.screen_x - self.start_x
        if delta_x == 0:
            return

        # Convert to percentage of total width based on app width
        app_width = self.size.width
        delta_percent = (delta_x / app_width) * 100

        # Update panel widths with constraints
        if self.resizing_panel == "sidebar":
            # Resizing sidebar affects editor width
            new_sidebar_width = self.current_widths["sidebar"] + delta_percent
            new_editor_width = self.current_widths["editor-container"] - delta_percent

            # Apply constraints
            if 10 <= new_sidebar_width <= 40 and 30 <= new_editor_width <= 80:
                self.current_widths["sidebar"] = new_sidebar_width
                self.current_widths["editor-container"] = new_editor_width

                # Apply new widths
                sidebar = self.query_one("#sidebar")
                editor = self.query_one("#editor-container")
                sidebar.styles.width = f"{new_sidebar_width}%"
                editor.styles.width = f"{new_editor_width}%"

        elif self.resizing_panel == "editor-container":
            # Resizing editor affects AI panel width
            new_editor_width = self.current_widths["editor-container"] + delta_percent
            new_ai_width = self.current_widths["ai-panel"] - delta_percent

            # Apply constraints
            if 30 <= new_editor_width <= 80 and 15 <= new_ai_width <= 40:
                self.current_widths["editor-container"] = new_editor_width
                self.current_widths["ai-panel"] = new_ai_width

                # Apply new widths
                editor = self.query_one("#editor-container")
                ai_panel = self.query_one("#ai-panel")
                editor.styles.width = f"{new_editor_width}%"
                ai_panel.styles.width = f"{new_ai_width}%"

        # Update the start position for the next move
        self.start_x = event.screen_x

    def get_widget_at(self, x: int, y: int):
        """
        Get the widget at a specific screen coordinate

        Args:
            x: The x screen coordinate
            y: The y screen coordinate

        Returns:
            The widget at the given coordinates, or None if no widget is found
        """
        # Convert screen coordinates to app coordinates
        app_x = x
        app_y = y

        # Find the widget at the given position
        for widget in self.query("*"):
            # Get widget's region
            region = widget.region
            if region and region.contains(app_x, app_y):
                # Calculate offset within the widget
                offset = (app_x - region.x, app_y - region.y)
                return widget, offset

        return None, (0, 0)

    def initialize_ai_panel(self):
        """Initialize AI panel elements"""
        try:
            ai_prompt = self.query_one("#ai-prompt")
            ai_submit = self.query_one("#ai-submit")

            # Make sure the input can receive focus
            ai_prompt.can_focus = True

            # Make sure the button can be clicked and has the right styling
            ai_submit.can_focus = True
            ai_submit.variant = "primary"

            # Log successful initialization
            logging.info("AI panel initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing AI panel: {str(e)}", exc_info=True)

    @work
    async def update_git_status(self):
        """Update the git status display"""
        current_time = time.time()
        if current_time - self._last_status_update_time < self._status_update_debounce:
            return
        self._last_status_update_time = current_time
        if not self.git_repository:
            return

        git_output = self.query_one("#git-output")
        git_output.update("Checking Git status...")

        try:
            # Use GitManager to get status
            status = GitManager.get_git_status(self.git_repository)

            if "error" in status:
                git_output.update(f"Git error: {status['error']}")
                return

            if status.get("clean", False):
                git_output.update("Working tree clean")
                return

            # Format the status output
            status_text = ""

            if status.get("modified_files"):
                status_text += "📝 Modified files:\n"
                for file in status["modified_files"]:
                    status_text += f"  {file}\n"

            if status.get("untracked_files"):
                if status_text:
                    status_text += "\n"
                status_text += "❓ Untracked files:\n"
                for file in status["untracked_files"]:
                    status_text += f"  {file}\n"

            if status.get("staged_files"):
                if status_text:
                    status_text += "\n"
                status_text += "➕ Staged files:\n"
                for file in status["staged_files"]:
                    status_text += f"  {file}\n"

            git_output.update(status_text)

        except Exception as e:
            git_output.update(f"Error: {str(e)}")

    @work(thread=True)
    async def git_commit(self, message: str):
        """Commit changes to the Git repository asynchronously"""
        if not self.git_repository:
            self.notify("Not a Git repository", severity="error")
            return
    
        try:
            # Use asyncio.subprocess for async process execution
            import asyncio.subprocess
    
            # First add all changes
            process = await asyncio.subprocess.create_subprocess_exec(
                "git", "add", ".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.git_repository
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.notify(f"Git add failed: {stderr.decode()}", severity="error")
                return
    
            # Then commit with GitManager (assuming it supports async)
            success, result_msg = await GitManager.git_commit_async(self.git_repository, message)
    
            if success:
                self.notify("Changes committed successfully", severity="success")
                # Update status after commit
                await self.update_git_status()
            else:
                self.notify(f"Commit failed: {result_msg}", severity="error")
    
        except Exception as e:
            self.notify(f"Error making commit: {str(e)}", severity="error")

    @work(thread=True)
    async def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        """Handle file selection in the directory tree"""
        try:
            # Safely extract the path using proper error handling
            path = getattr(event, "path", None)
            if not path:
                # Try to access path through event.node.data (for newer Textual versions)
                node = getattr(event, "node", None)
                if node:
                    path = getattr(node, "data", None)

            # If still no path, use event as fallback (some Textual versions pass path directly)
            if not path and isinstance(event, (str, Path)):
                path = str(event)

            # Last resort - try to get path from the message itself
            if not path and hasattr(event, "_Message__data"):
                data = getattr(event, "_Message__data", {})
                path = data.get("path", None)

            if not path:
                raise ValueError("Could not determine file path from event")

            # Store the path and update window title
            self.current_file = path
            self.title = f"Terminator - {path}"

            # Load the file content
            async with aiofiles.open(path, "r", encoding="utf-8") as file:
                content = await file.read()

            # Get file extension for language detection
            extension = os.path.splitext(path)[1].lower()
            language = self.get_language_from_extension(extension)

            # Update the active editor
            if self.active_editor == "primary":
                editor = self.query_one("#editor-primary")
            else:
                editor = self.query_one("#editor-secondary")

            # Set the language and content
            editor.language = language

            # Use load_text if available (newer Textual versions)
            if hasattr(editor, "load_text"):
                editor.load_text(content)
            else:
                # Fallback to direct text assignment
                editor.text = content

            # Apply the current theme
            if hasattr(self, "current_theme_name") and self.current_theme_name is not None:
            # Use the theme name string directly
                editor.theme = self.current_theme_name
            elif hasattr(self, "editor_theme") and self.editor_theme is not None:
            # Use the editor_theme string directly
                editor.theme = self.editor_theme
            else:
                # Fallback to default theme
                editor.theme = "monokai"

            # Focus the editor
            editor.focus()

            # Add the file to recent files list if we maintain one
            if hasattr(self, "recent_files") and isinstance(self.recent_files, list):
                if path in self.recent_files:
                    self.recent_files.remove(path)
                self.recent_files.insert(0, path)
                # Keep list at reasonable size
                self.recent_files = self.recent_files[:10]

            # Notify about the detected language
            self.notify(
                f"File opened with {language} highlighting", severity="information"
            )

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error opening file: {error_msg}", exc_info=True)
            self.notify(f"Error opening file: {error_msg}", severity="error")

    async def toggle_split_view(self):
        """Toggle split view mode"""
        editor_split = self.query_one("#editor-split-view")
        secondary_editor = self.query_one("#editor-secondary")

        if self.split_view_active:
            # Disable split view
            secondary_editor.add_class("hidden")
            editor_split.remove_class("split-view")
            self.split_view_active = False
            self.active_editor = "primary"
            self.notify("Split view disabled")
        else:
            # Enable split view
            secondary_editor.remove_class("hidden")
            editor_split.add_class("split-view")
            self.split_view_active = True

            # Copy content from primary to secondary if secondary is empty
            primary_editor = self.query_one("#editor-primary")
            if not secondary_editor.text:
                secondary_editor.language = primary_editor.language
                secondary_editor.text = primary_editor.text

            self.notify("Split view enabled")

    def get_language_from_extension(self, extension):
        """Map file extension to language for syntax highlighting"""
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".md": "markdown",
            ".txt": None,  # Use None for plain text files
            # Add more as needed
        }
        # Return None for text files instead of "text" to avoid tree-sitter error
        return extension_map.get(extension, None)

    @work(thread=True)
    async def action_save(self):
        """Save the current file asynchronously"""
        if not self.current_file:
            self.notify("No file selected to save", severity="warning")
            return
    
        try:
            # Get the active editor
            if self.active_editor == "primary":
                editor = self.query_one("#editor-primary")
            else:
                editor = self.query_one("#editor-secondary")
    
            # Get content
            content = editor.text
    
            # Use aiofiles for async file I/O
            async with aiofiles.open(self.current_file, "w", encoding="utf-8") as file:
                await file.write(content)
    
            # Notify success
            self.notify(f"Saved {self.current_file}")
    
            # Schedule git status update as a separate task
            asyncio.create_task(self.update_git_status())
    
        except Exception as e:
            self.notify(f"Error saving file: {str(e)}", severity="error")

    @work(thread=True)
    async def action_run(self):
        """Run the current Python file"""
        if not self.current_file:
            self.notify("No file selected to run", severity="warning")
            return

        if not self.current_file.endswith(".py"):
            self.notify("Only Python files can be executed", severity="warning")
            return

        # Save before running
        self.action_save()

        try:
            # Show running indicator
            ai_output = self.query_one("#ai-output")
            ai_output.update(f"Running {os.path.basename(self.current_file)}...\n\n")

            # Execute the Python file
            import subprocess

            result = subprocess.run(
                [sys.executable, self.current_file],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.current_file),
            )

            # Display the output
            output = (
                f"## Execution Results for {os.path.basename(self.current_file)}\n\n"
            )

            if result.stdout:
                output += f"### Output:\n```\n{result.stdout}\n```\n\n"

            if result.stderr:
                output += f"### Errors:\n```\n{result.stderr}\n```\n\n"

            if result.returncode == 0:
                output += f"✅ Program completed successfully (exit code: 0)"
            else:
                output += f"❌ Program failed with exit code: {result.returncode}"

            ai_output.update(output)

        except Exception as e:
            self.notify(f"Error running file: {str(e)}", severity="error")
            ai_output = self.query_one("#ai-output")
            ai_output.update(f"## Execution Error\n\n```\n{str(e)}\n```")

    async def action_ai_request(self):
        """Process an AI request"""
        # Get the prompt from the input field
        prompt_input = self.query_one("#ai-prompt")
        prompt = prompt_input.value.strip()

        # For debugging, add a notification to confirm this method is called
        self.notify(f"Processing AI request: {prompt}", severity="information")

        if not prompt:
            self.notify("Please enter a prompt for the AI", severity="warning")
            return

        # Clear the input field
        prompt_input.value = ""

        # Get current code from active editor for context
        try:
            if self.active_editor == "primary":
                editor = self.query_one("#editor-primary")
            else:
                editor = self.query_one("#editor-secondary")

            code_context = editor.text
        except Exception as e:
            self.notify(f"Error getting editor context: {str(e)}", severity="error")
            code_context = ""

        # Update the AI output with the query
        try:
            ai_output = self.query_one("#ai-output")
            # Get current content as a string - Markdown widgets use str() in newer Textual
            current_content = str(ai_output)

            # Update the markdown with the query
            ai_output.update(
                f"{current_content}\n\n### Your Question:\n{prompt}\n\n### AI Assistant:\n*Thinking...*"
            )
        except Exception as e:
            self.notify(f"Error updating AI output: {str(e)}", severity="error")

        # Call the AI agent
        try:
            worker = self.call_ai_agent(prompt, code_context)
            # Don't await here - worker will process in the background
        except Exception as e:
            self.notify(f"Error calling AI agent: {str(e)}", severity="error")
            logging.error(f"AI agent error: {str(e)}", exc_info=True)

    def _prepare_agent_prompt(self, prompt, code_context):
        """Prepare the full prompt for the AI agent"""
        is_code_completion = False
        if (
            prompt.lower().startswith("complete")
            or "autocomplete" in prompt.lower()
            or "finish this code" in prompt.lower()
        ):
            is_code_completion = True

        if code_context:
            if is_code_completion:
                return f"""Complete or suggest the next part of this code. 
                Analyze the code patterns and provide a detailed completion that follows the style and logic of the existing code.
                Return complete functions or code blocks, not just a single line.

                Code to complete:
                ```python
                {code_context}
                ```

                Provide the completed code only, without explanations."""
            else:
                return f"I'm working with this code:\n```python\n{code_context}\n```\n\nMy question: {prompt}"
        return prompt

    @work(thread=True)
    async def call_ai_agent(self, prompt, code_context):
        """Call the AI agent with the prompt and code context"""
        # Must return a value from work decorator
        return await self._process_ai_agent_call(prompt, code_context)

    async def _process_ai_agent_call(self, prompt, code_context):
        """Internal method to process AI agent call"""
        try:
            full_prompt = self._prepare_agent_prompt(prompt, code_context)
            result = await run_agent_query(full_prompt, self.agent_context)
            response = result.get("response", "I couldn't process that request.")
            self.call_after_refresh(self._update_ai_output_with_response, response)
            return response
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            self.call_after_refresh(self._update_ai_output_with_response, error_message)
            return error_message

    def _update_ai_output_with_response(self, response):
        """Update the AI output widget with the response"""
        try:
            ai_output = self.query_one("#ai-output")
            # Get current content as a string - Markdown widgets use .update() in newer Textual
            current_content = str(ai_output)

            # Remove the "Thinking..." placeholder and add the real response
            if "*Thinking...*" in current_content:
                # Find everything before "Thinking..."
                thinking_pos = current_content.find("*Thinking...*")
                if thinking_pos > 0:
                    current_content = current_content[:thinking_pos]
                else:
                    # Just use a clean slate if we can't find the position
                    current_content = ""

            # Add the response and update the markdown
            ai_output.update(f"{current_content}{response}")

            # Check for code edits in the response
            self._check_for_code_suggestions(response)

        except Exception as e:
            self.notify(f"Error updating AI output: {str(e)}", severity="error")
            logging.error(f"Error updating AI output: {str(e)}", exc_info=True)

    async def on_mouse_down(self, event: MouseDown) -> None:
        """Handle mouse down events for gutter resizing"""
        # Check if we clicked on a gutter element
        target, _ = self.get_widget_at(event.screen_x, event.screen_y)

        if target and isinstance(target, Static) and target.has_class("gutter"):
            # Find the adjacent panels for this gutter
            gutter_idx = list(self.query(".gutter")).index(target)

            if gutter_idx == 0:
                # First gutter - between sidebar and editor
                self.resizing_panel = "sidebar"
            elif gutter_idx == 1:
                # Second gutter - between editor and AI panel
                self.resizing_panel = "editor-container"

            # Start resizing
            self.resizing = True
            self.start_x = event.screen_x

            # Capture the mouse to receive events outside the gutter
            self.capture_mouse()

            # Set the cursor to indicate resizing
            event.prevent_default()

    async def on_mouse_up(self, event) -> None:
        """Handle mouse up events to end panel resizing"""
        if self.resizing:
            self.resizing = False
            self.resizing_panel = None

    async def on_mouse_move(self, event) -> None:
        """Handle mouse move events for panel resizing"""
        if not self.resizing or not self.resizing_panel:
            return

        # Calculate movement
        delta_x = event.screen_x - self.start_x
        if delta_x == 0:
            return

        # Convert to percentage of total width based on app width
        app_width = self.size.width
        delta_percent = (delta_x / app_width) * 100

        # Update panel widths with constraints
        if self.resizing_panel == "sidebar":
            # Resizing sidebar affects editor width
            new_sidebar_width = self.current_widths["sidebar"] + delta_percent
            new_editor_width = self.current_widths["editor-container"] - delta_percent

            # Apply constraints
            if 10 <= new_sidebar_width <= 40 and 30 <= new_editor_width <= 80:
                self.current_widths["sidebar"] = new_sidebar_width
                self.current_widths["editor-container"] = new_editor_width

                # Apply new widths
                sidebar = self.query_one("#sidebar")
                editor = self.query_one("#editor-container")
                sidebar.styles.width = f"{new_sidebar_width}%"
                editor.styles.width = f"{new_editor_width}%"

        elif self.resizing_panel == "editor-container":
            # Resizing editor affects AI panel width
            new_editor_width = self.current_widths["editor-container"] + delta_percent
            new_ai_width = self.current_widths["ai-panel"] - delta_percent

            # Apply constraints
            if 30 <= new_editor_width <= 80 and 10 <= new_ai_width <= 40:
                self.current_widths["editor-container"] = new_editor_width
                self.current_widths["ai-panel"] = new_ai_width

                # Apply new widths
                editor = self.query_one("#editor-container")
                ai_panel = self.query_one("#ai-panel")
                editor.styles.width = f"{new_editor_width}%"
                ai_panel.styles.width = f"{new_ai_width}%"

        # Update start position for next movement
        self.start_x = event.screen_x

    def _check_for_code_suggestions(self, response):
        """
        Check if the AI response contains code suggestions and offer to show diff

        Args:
            response: The AI response text
        """
        try:
            # Only proceed if we have an active file
            if not self.current_file:
                return

            # Get the active editor content for comparison
            if self.active_editor == "primary":
                editor = self.query_one("#editor-primary")
            else:
                editor = self.query_one("#editor-secondary")

            current_content = editor.text

            # Check if the response contains code blocks
            code_blocks = re.findall(r"```(\w*)\n(.*?)```", response, re.DOTALL)

            if code_blocks:
                # Find the first Python code block that's a significant edit
                for lang, code in code_blocks:
                    # Skip if not Python code or if it's just a short snippet
                    if lang.lower() not in ["python", "py"] or len(code.strip()) < 10:
                        continue

                    # Skip if the code is too different from the current file
                    # This is a simple heuristic to avoid comparing unrelated code
                    if len(current_content) > 0 and len(code) > 0:
                        # If the suggested code is less than 20% similar to current content,
                        # it's probably unrelated
                        similarity = difflib.SequenceMatcher(
                            None, current_content, code
                        ).ratio()
                        if similarity < 0.2:
                            continue

                    # Calculate how different the code is
                    diff = CodeAnalyzer.create_diff(current_content, code)

                    # If there are actual differences, offer to preview and apply them
                    if diff and "+" in diff and "-" in diff:
                        # Start a background task to show a notification with action buttons
                        asyncio.create_task(
                            self._show_code_suggestion_notification(
                                current_content, code
                            )
                        )
                        break

        except Exception as e:
            logging.error(
                f"Error checking for code suggestions: {str(e)}", exc_info=True
            )

    async def _show_code_suggestion_notification(self, current_content, suggested_code):
        """
        Show notification for code suggestions with action buttons

        Args:
            current_content: Current file content
            suggested_code: Suggested code from AI
        """
        # Slight delay to ensure notification appears after the main response
        await asyncio.sleep(0.5)

        # Create a notification with action buttons
        extension = os.path.splitext(self.current_file)[1].lower()
        language = self.get_language_from_extension(extension)

        from textual.notifications import Notification

        class CodeSuggestionNotification(Notification):
            def __init__(self, app, current, suggested):
                self.app = app
                self.current = current
                self.suggested = suggested
                super().__init__(
                    title="AI Code Suggestion",
                    message="The AI has suggested code changes. Would you like to view them?",
                    timeout=20,
                )

            def on_button_pressed(self, event):
                button_id = event.button.id
                if button_id == "view-diff":
                    self.app.show_diff_view(
                        self.current,
                        self.suggested,
                        title="AI Suggested Changes",
                        language=language,
                    )
                elif button_id == "apply-directly":
                    self.app.apply_diff_changes(self.suggested)

            def compose(self):
                yield from super().compose()
                with self.content:
                    yield Button("View Changes", id="view-diff", variant="primary")
                    yield Button(
                        "Apply Directly", id="apply-directly", variant="warning"
                    )

        # Show the custom notification
        self.notify(
            CodeSuggestionNotification(self, current_content, suggested_code),
            severity="information",
        )

    # Handle tab changes
    async def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Handle tab activation"""
        tab_id = event.tab.id

        self.notify(f"Tab activated: {tab_id}", severity="information")
        if tab_id == "editor-tab-pane":
            self.active_tab = "editor"
            self.query_one("#editor-content").remove_class("hidden")
            self.query_one("#terminal-content").add_class("hidden")
            # Focus the active editor
            if self.active_editor == "primary":
                self.query_one("#editor-primary").focus()
            else:
                self.query_one("#editor-secondary").focus()
        elif tab_id == "terminal-tab-pane":
            self.active_tab = "terminal"
            self.query_one("#terminal-content").remove_class("hidden")
            self.query_one("#editor-content").add_class("hidden")
            # Focus the terminal input
            self.query_one("#terminal-input").focus()

    # Handle button events
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events"""
        button_id = event.button.id

        if button_id == "commit-btn":
            self.action_git_commit()
        elif button_id == "pull-btn":
            self.action_git_pull()
        elif button_id == "push-btn":
            self.action_git_push()
        elif button_id == "branches-btn":
            self.action_show_branch_visualization()
        elif button_id == "run-btn":
            self.action_run()
        elif button_id == "debug-btn":
            self.action_debug_current_file()
        elif button_id == "save-btn":
            self.action_save()
        elif button_id == "format-btn":
            self.action_format_code()
        elif button_id == "split-view-btn":
            self.toggle_split_view()
        elif button_id == "theme-btn":
            self.push_screen(ThemeSelectionScreen())
        elif button_id == "pair-program-btn":
            self.action_toggle_pair_programming()
        elif button_id == "ai-submit":
            # Create a task to run the async method
            asyncio.create_task(self.action_ai_request())
        elif button_id == "terminal-execute-btn":
            self.execute_terminal_command()
        elif button_id == "open-remote-btn":
            self.action_connect_remote()

    async def action_show_branch_visualization(self) -> None:
        """Show the branch visualization screen"""
        if not self.git_repository:
            self.notify("Not a Git repository", severity="error")
            return

        self.push_screen("branch_visualization")

    async def action_git_commit(self) -> None:
        """Show the commit dialog screen"""
        if not self.git_repository:
            self.notify("Not a Git repository", severity="error")
            return

        self.push_screen(CommitDialog())

    @work
    async def action_git_pull(self) -> None:
        """Pull changes from remote repository"""
        if not self.git_repository:
            self.notify("Not a Git repository", severity="error")
            return

        git_output = self.query_one("#git-output")
        git_output.update("Pulling changes...")

        try:
            # Use GitManager to pull changes
            success, result = GitManager.git_pull(self.git_repository)

            if success:
                self.notify("Changes pulled successfully", severity="success")
                git_output.update(f"Pull successful:\n{result}")
                # Update status after pull
                self.update_git_status()
            else:
                self.notify(f"Pull failed", severity="error")
                git_output.update(f"Pull failed:\n{result}")

        except Exception as e:
            self.notify(f"Error pulling changes: {str(e)}", severity="error")
            git_output.update(f"Error: {str(e)}")

    @work
    async def action_git_push(self) -> None:
        """Push changes to remote repository"""
        if not self.git_repository:
            self.notify("Not a Git repository", severity="error")
            return

        git_output = self.query_one("#git-output")
        git_output.update("Pushing changes...")

        try:
            # Use GitManager to push changes
            success, result = GitManager.git_push(self.git_repository)

            if success:
                self.notify("Changes pushed successfully", severity="success")
                git_output.update(f"Push successful:\n{result}")
            else:
                self.notify(f"Push failed", severity="error")
                git_output.update(f"Push failed:\n{result}")

        except Exception as e:
            self.notify(f"Error pushing changes: {str(e)}", severity="error")
            git_output.update(f"Error: {str(e)}")

    @work
    async def action_format_code(self) -> None:
        """Format the current code using autopep8 or black if available"""
        if not self.current_file:
            self.notify("No file selected for formatting", severity="warning")
            return

        if not self.current_file.endswith(".py"):
            self.notify("Only Python files can be formatted", severity="warning")
            return

        # Get the active editor content
        if self.active_editor == "primary":
            editor = self.query_one("#editor-primary")
        else:
            editor = self.query_one("#editor-secondary")

        code = editor.text

        # Use an agent query to format the code
        if hasattr(self, "agent_context"):
            self.notify("Formatting code with AI...", severity="information")

            try:
                # Format code query
                result = await run_agent_query(
                    "Format this Python code according to PEP 8 without changing functionality:\n```python\n"
                    + code
                    + "\n```",
                    self.agent_context,
                )

                response = result.get("response", "")

                # Extract the code from markdown code blocks
                code_block_pattern = r"```python\s*\n(.*?)```"
                matches = re.findall(code_block_pattern, response, re.DOTALL)

                if matches:
                    formatted_code = matches[0].strip()
                    editor.text = formatted_code
                    self.notify("Code formatted successfully", severity="success")
                else:
                    # Try without language specifier
                    code_block_pattern = r"```\s*\n(.*?)```"
                    matches = re.findall(code_block_pattern, response, re.DOTALL)
                    if matches:
                        formatted_code = matches[0].strip()
                        editor.text = formatted_code
                        self.notify("Code formatted successfully", severity="success")
                    else:
                        self.notify("Failed to format code", severity="error")

            except Exception as e:
                self.notify(f"Error formatting code: {str(e)}", severity="error")
        else:
            self.notify(
                "AI agent not initialized, cannot format code", severity="error"
            )

    @work(thread=True)
    async def action_analyze_code(self) -> None:
        """Analyze the current code for issues"""
        if not self.current_file:
            self.notify("No file selected for analysis", severity="warning")
            return
    
        if not self.current_file.endswith(".py"):
            self.notify("Only Python files can be analyzed", severity="warning")
            return
    
        # Get the active editor content
        if self.active_editor == "primary":
            editor = self.query_one("#editor-primary")
        else:
            editor = self.query_one("#editor-secondary")
    
        code = editor.text
    
        # Show the analysis dialog
        self.push_screen(CodeAnalysisDialog())
    
        try:
            # Use CodeAnalyzer with async features
            analysis = await CodeAnalyzer.analyze_python_code_async(code)
    
            # Format the result as markdown
            result_md = f"# Analysis of {os.path.basename(self.current_file)}\n\n"
    
            # Add issues
            if analysis.get("issues"):
                result_md += f"## Issues Found ({len(analysis['issues'])})\n\n"
                for issue in analysis["issues"]:
                    result_md += f"- **Line {issue.get('line', '?')}**: {issue.get('message', 'Unknown issue')} ({issue.get('type', 'unknown')})\n"
            else:
                result_md += "## No Issues Found\n\n"
    
            # Add recommendations
            if analysis.get("recommendations"):
                result_md += f"\n## Recommendations\n\n"
                for rec in analysis["recommendations"]:
                    result_md += f"- {rec}\n"
    
            # Also add code stats
            stats = await CodeAnalyzer.count_code_lines_async(code)
            result_md += f"\n## Code Statistics\n\n"
            result_md += f"- Total lines: {stats.get('total_lines', 0)}\n"
            result_md += f"- Code lines: {stats.get('code_lines', 0)}\n"
            result_md += f"- Comment lines: {stats.get('comment_lines', 0)}\n"
            result_md += f"- Blank lines: {stats.get('blank_lines', 0)}\n"
    
            # Post the completion event with the result
            self.post_message(self.CodeAnalysisComplete(result_md))
    
        except Exception as e:
            error_msg = f"# Error During Analysis\n\n{str(e)}"
            self.post_message(self.CodeAnalysisComplete(error_msg))

    async def on_code_analysis_complete(self, event: CodeAnalysisComplete) -> None:
        """Handle code analysis completion"""
        # Update the analysis result in the dialog
        analysis_dialog = self.query_one(CodeAnalysisDialog)
        analysis_result = analysis_dialog.query_one("#analysis-result")
        analysis_result.query_one(Markdown).update(event.analysis_result)

    def action_toggle_pair_programming(self) -> None:
        """Toggle AI pair programming mode"""
        # Toggle the pair programming mode
        self.pair_programming_active = not self.pair_programming_active

        # Update the button visual state
        pair_btn = self.query_one("#pair-program-btn")

        if self.pair_programming_active:
            # Start pair programming mode
            self.notify("AI Pair Programming mode activated", severity="success")
            pair_btn.variant = "error"  # Red button when active
            pair_btn.label = "Stop Pair Programming"

            # Create a timer to check for inactivity and provide suggestions
            if self.pair_programming_timer:
                self.pair_programming_timer.stop()

            # Start a timer that checks for inactivity every 5 seconds
            self.pair_programming_timer = self.set_interval(
                5, self.check_for_pair_programming_suggestion
            )

            # Start tracking edit time
            self.last_edit_time = time.time()

            # Add event handlers for text editing
            self.watch_text_area()
        else:
            # Stop pair programming mode
            self.notify("AI Pair Programming mode deactivated", severity="information")
            pair_btn.variant = "primary"  # Normal button when inactive
            pair_btn.label = "Pair Program"

            # Stop the timer
            if self.pair_programming_timer:
                self.pair_programming_timer.stop()
                self.pair_programming_timer = None

    def watch_text_area(self) -> None:
        """Start watching text area for changes in pair programming mode"""
        # In a full implementation, we would set up event handlers to track edits
        # We'll simulate this by updating the last_edit_time in certain methods
        pass

    def check_for_pair_programming_suggestion(self) -> None:
        """Check if it's time to provide a pair programming suggestion"""
        if not self.pair_programming_active:
            return

        # Check if the user has been inactive for more than 5 seconds
        current_time = time.time()
        if current_time - self.last_edit_time >= 5:
            # Time to generate a suggestion
            self.generate_pair_programming_suggestion()

    @work
    async def generate_pair_programming_suggestion(self) -> None:
        """Generate a pair programming suggestion based on current code"""
        if not self.current_file:
            return

        # Get the current code
        if self.active_editor == "primary":
            editor = self.query_one("#editor-primary")
        else:
            editor = self.query_one("#editor-secondary")

        code_context = editor.text

        if not code_context:
            return

        self.notify("AI suggesting improvements...", severity="information")

        # Create a specific prompt for pair programming suggestions
        prompt = """As your AI pair programmer, I'm analyzing your code. 
        Please provide detailed suggestions for improvements, optimizations, 
        potential bugs, or code style enhancements. Focus on being helpful but 
        concise. Don't rewrite everything, just suggest targeted improvements."""

        # Call the AI with the pair programming prompt
        worker = self.call_ai_agent(prompt, code_context)

        # Reset the timer to avoid constant suggestions
        self.last_edit_time = time.time()

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Handle text area changes"""
        # Update the last edit time when the user makes changes
        self.last_edit_time = time.time()

    def action_connect_remote(self) -> None:
        """Show the remote connection dialog"""
        self.push_screen("remote_connection")

    def configure_remote(self, **config) -> None:
        """Configure the remote connection"""
        # Update the remote config
        for key, value in config.items():
            if key in self.remote_config:
                self.remote_config[key] = value

        # Simulate connection
        self.notify(
            f"Connecting to {self.remote_config['host']}...", severity="information"
        )

        # In a real implementation, we would actually connect
        # For now, we'll just simulate a successful connection
        self.remote_connected = True

        # Show connection success message
        self.notify(
            f"Connected to {self.remote_config['host']} as {self.remote_config['username']}",
            severity="success",
        )

        # Show the remote files browser
        self.push_screen("remote_browser")

    def disconnect_remote(self) -> None:
        """Disconnect from the remote server"""
        if not self.remote_connected:
            self.notify("Not connected to a remote server", severity="warning")
            return

        # Simulate disconnection
        self.notify("Disconnecting from remote server...", severity="information")

        # Reset connection state
        self.remote_connected = False

        # Show disconnection message
        self.notify("Disconnected from remote server", severity="success")

    def action_upload_to_remote(self) -> None:
        """Upload a file to the remote server"""
        if not self.remote_connected:
            self.notify("Not connected to a remote server", severity="warning")
            return

        if not self.current_file:
            self.notify("No file selected for upload", severity="warning")
            return

        # Simulate file upload
        self.notify(
            f"Uploading {self.current_file} to remote server...", severity="information"
        )

        # In a real implementation, we would actually upload the file
        # For now, we'll just simulate a successful upload
        self.notify(
            f"Uploaded {os.path.basename(self.current_file)} to {self.remote_config['remote_path']}",
            severity="success",
        )

    def action_switch_editor(self) -> None:
        """Switch focus between primary and secondary editors in split view"""
        if not self.split_view_active:
            self.notify("Split view is not active", severity="warning")
            return

        if self.active_editor == "primary":
            self.active_editor = "secondary"
            self.query_one("#editor-secondary").focus()
            self.notify("Switched to secondary editor")
        else:
            self.active_editor = "primary"
            self.query_one("#editor-primary").focus()
            self.notify("Switched to primary editor")

    def action_add_multi_cursor(self) -> None:
        """Add a cursor at the current position or word"""
        # Get the active editor
        if self.active_editor == "primary":
            editor = self.query_one("#editor-primary")
        else:
            editor = self.query_one("#editor-secondary")

        # Get the current cursor position
        cursor_position = editor.cursor_position
        cursor_row, cursor_column = cursor_position

        # In a real implementation, this would add a cursor
        # For this example, we'll just notify about the cursor position
        self.notify(
            f"Multi-cursor added at row {cursor_row+1}, column {cursor_column+1}",
            severity="information",
        )

        # Track multi-cursor positions for future implementation
        self.multi_cursor_positions.append(cursor_position)

        # Add multi-cursor class to the editor
        editor.add_class("multi-cursor")

    async def action_toggle_split_view(self) -> None:
        """Toggle split view mode using keyboard shortcut"""
        self.toggle_split_view()

    async def action_show_command_palette(self) -> None:
        """Show the command palette for quick access to commands"""
        self.push_screen("command_palette")

    async def action_code_completion(self) -> None:
        """Trigger AI code completion on the current cursor position"""
        if not self.current_file:
            self.notify("No file open for code completion", severity="warning")
            return

        # Get the active editor
        if self.active_editor == "primary":
            editor = self.query_one("#editor-primary")
        else:
            editor = self.query_one("#editor-secondary")

        # Get the code context
        code_context = editor.text

        # Show a notification
        self.notify("Generating code completion...", severity="information")

        # Request code completion from AI
        worker = self.call_ai_agent("Complete this code", code_context)

    def action_toggle_breakpoint(self) -> None:
        """Toggle a breakpoint at the current line in the editor"""
        if not self.current_file:
            self.notify("No file open for setting breakpoints", severity="warning")
            return

        if not self.current_file.endswith(".py"):
            self.notify(
                "Breakpoints can only be set in Python files", severity="warning"
            )
            return

        # Get the active editor
        if self.active_editor == "primary":
            editor = self.query_one("#editor-primary")
        else:
            editor = self.query_one("#editor-secondary")

        # Get the current cursor position
        cursor_row, _ = editor.cursor_position
        line_number = cursor_row + 1  # Convert to 1-based line number

        # Initialize breakpoints for this file if not already present
        if self.current_file not in self.breakpoints:
            self.breakpoints[self.current_file] = []

        # Toggle the breakpoint
        if line_number in self.breakpoints[self.current_file]:
            self.breakpoints[self.current_file].remove(line_number)
            self.notify(
                f"Breakpoint removed at line {line_number}", severity="information"
            )
        else:
            # Verify that we can set a breakpoint at this line
            success, message = PythonDebugger.set_breakpoint(
                self.current_file, line_number
            )

            if success:
                self.breakpoints[self.current_file].append(line_number)
                self.notify(
                    f"Breakpoint set at line {line_number}", severity="information"
                )
            else:
                self.notify(f"Cannot set breakpoint: {message}", severity="error")

    def action_debug_current_file(self) -> None:
        """Start debugging the current file"""
        if not self.current_file:
            self.notify("No file open for debugging", severity="warning")
            return

        if not self.current_file.endswith(".py"):
            self.notify("Only Python files can be debugged", severity="warning")
            return

        # Save the file before debugging
        self.action_save()

        # Start a debugging session
        success, debug_session = PythonDebugger.start_debugging(self.current_file)

        if not success:
            error = debug_session.get("error", "Unknown error starting debugger")
            self.notify(f"Debug failed: {error}", severity="error")
            return

        # Store the debug session
        self.debug_session = debug_session

        # Add any existing breakpoints
        if self.current_file in self.breakpoints:
            self.debug_session["breakpoints"] = self.breakpoints[self.current_file]

        # Switch to the debugger screen
        self.push_screen("debugger")

        # Update the debugger UI
        self.update_debugger_ui()

    def update_debugger_ui(self) -> None:
        """Update the debugger UI with the current debug session info"""
        if not self.debug_session or not self.app.screen_stack[-1].id == "debugger":
            return

        # Update code view
        debug_code = self.app.screen_stack[-1].query_one("#debug-code")
        debug_code.text = self.debug_session.get("code", "")

        # Highlight current line
        current_line = self.debug_session.get("current_line", 1)

        # This would require extending TextArea to support line highlighting
        # For now, we'd just notify about the current line position
        self.notify(f"Debugging at line {current_line}", severity="information")

        # Update variables table
        variables_table = self.app.screen_stack[-1].query_one("#debug-variables")
        variables_table.clear()

        for var_name, var_info in self.debug_session.get("variables", {}).items():
            variables_table.add_row(
                var_name, var_info.get("type", "unknown"), var_info.get("value", "")
            )

        # Update call stack
        stack_table = self.app.screen_stack[-1].query_one("#debug-stack")
        stack_table.clear()

        for frame in self.debug_session.get("call_stack", []):
            stack_table.add_row(
                str(frame.get("frame", "")),
                frame.get("function", ""),
                frame.get("file", ""),
                str(frame.get("line", "")),
            )

        # Update output
        debug_output = self.app.screen_stack[-1].query_one("#debug-output")
        debug_output.text = self.debug_session.get("output", "")

    def debug_step_over(self) -> None:
        """Execute a step over command in the debugger"""
        if not self.debug_session:
            self.notify("No active debugging session", severity="error")
            return

        if not self.debug_session.get("active", False):
            self.notify("Debugging session has ended", severity="information")
            return

        # Execute step over
        self.debug_session = PythonDebugger.debug_step(self.debug_session, "step_over")

        # Update the UI
        self.update_debugger_ui()

    def debug_step_into(self) -> None:
        """Execute a step into command in the debugger"""
        if not self.debug_session:
            self.notify("No active debugging session", severity="error")
            return

        if not self.debug_session.get("active", False):
            self.notify("Debugging session has ended", severity="information")
            return

        # Execute step into
        self.debug_session = PythonDebugger.debug_step(self.debug_session, "step_into")

        # Update the UI
        self.update_debugger_ui()

    def debug_step_out(self) -> None:
        """Execute a step out command in the debugger"""
        if not self.debug_session:
            self.notify("No active debugging session", severity="error")
            return

        if not self.debug_session.get("active", False):
            self.notify("Debugging session has ended", severity="information")
            return

        # Execute step out
        self.debug_session = PythonDebugger.debug_step(self.debug_session, "step_out")

        # Update the UI
        self.update_debugger_ui()

    def debug_continue(self) -> None:
        """Execute a continue command in the debugger"""
        if not self.debug_session:
            self.notify("No active debugging session", severity="error")
            return

        if not self.debug_session.get("active", False):
            self.notify("Debugging session has ended", severity="information")
            return

        # Execute continue
        self.debug_session = PythonDebugger.debug_step(self.debug_session, "continue")

        # Update the UI
        self.update_debugger_ui()

    def debug_stop(self) -> None:
        """Stop the current debugging session"""
        if not self.debug_session:
            self.notify("No active debugging session", severity="error")
            return

        # Stop debugging
        self.debug_session = PythonDebugger.stop_debugging(self.debug_session)

        # Update the UI
        self.update_debugger_ui()

        # Return to the main screen if debugging has ended
        if not self.debug_session.get("active", False):
            self.pop_screen()
            self.notify("Debugging session terminated", severity="information")

    async def action_toggle_terminal(self) -> None:
        """Toggle between editor and terminal tabs"""
        editor_tabs = self.query_one("#editor-tabs")

        if self.active_tab == "editor":
            # Activate terminal tab
            editor_tabs.active = "terminal-tab"
            self.active_tab = "terminal"
            self.query_one("#terminal-content").remove_class("hidden")
            self.query_one("#editor-content").add_class("hidden")
            self.query_one("#terminal-input").focus()
        else:
            # Activate editor tab
            editor_tabs.active = "editor-tab"
            self.active_tab = "editor"
            self.query_one("#editor-content").remove_class("hidden")
            self.query_one("#terminal-content").add_class("hidden")
            if self.active_editor == "primary":
                self.query_one("#editor-primary").focus()
            else:
                self.query_one("#editor-secondary").focus()

    async def action_start_collaboration(self) -> None:
        """Start or join a real-time collaboration session"""
        # Show collaboration dialog
        self.push_screen(
            CollaborationSessionDialog(), callback=self.handle_collaboration_dialog
        )

    def handle_collaboration_dialog(self, result: Optional[Dict[str, Any]]) -> None:
        """
        Handle the result from the collaboration dialog

        Args:
            result: Dialog result
        """
        if result is None:
            # Dialog was canceled
            return

        action = result.get("action")

        if action == "create":
            # Create a new session
            username = result.get("username", "User")
            # Generate a random session ID
            import random

            session_id = "".join(
                random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6)
            )

            session_details = {
                "username": username,
                "session_id": session_id,
                "is_host": True,
            }

            # Start the collaboration server in a background task
            self.start_collaboration_server()

            # Open the collaboration screen
            self.push_screen(CollaborationScreen(session_details))

        elif action == "join":
            # Join an existing session
            username = result.get("username", "User")
            session_id = result.get("session_id", "")

            session_details = {
                "username": username,
                "session_id": session_id,
                "is_host": False,
            }

            # Open the collaboration screen
            self.push_screen(CollaborationScreen(session_details))

    @work
    async def start_collaboration_server(self) -> None:
        """Start the WebSocket server for real-time collaboration"""
        try:
            # Initialize collaboration manager if not already created
            if not hasattr(self, "collaboration_manager"):
                self.collaboration_manager = CollaborationManager()

            # Start the server
            await self.collaboration_manager.start_server()
            self.notify("Collaboration server started", severity="information")

        except Exception as e:
            self.notify(
                f"Failed to start collaboration server: {str(e)}", severity="error"
            )

    async def stop_collaboration_server(self) -> None:
        """Stop the WebSocket server for real-time collaboration"""
        if (
            hasattr(self, "collaboration_manager")
            and self.collaboration_manager.running
        ):
            await self.collaboration_manager.stop_server()
            self.notify("Collaboration server stopped", severity="information")

    async def on_text_area_cursor_moved(self, event) -> None:
        """
        Handle cursor movement events for collaborative editing

        Args:
            event: Cursor moved event
        """
        # Only process if we're in a collaboration session
        if not self.app.is_screen_active(CollaborationScreen):
            return

        # Get current position and forward to collaboration session
        text_area = event.text_area
        position = (text_area.cursor_location.row, text_area.cursor_location.column)

        # In a real implementation, this would send the cursor position to other users
        # For now, we just log it
        if (
            hasattr(self, "last_cursor_position")
            and self.last_cursor_position == position
        ):
            return

        self.last_cursor_position = position
        self.query_one("#terminal-content").add_class("hidden")
        if self.active_editor == "primary":
            self.query_one("#editor-primary").focus()
        else:
            self.query_one("#editor-secondary").focus()

    @work
    async def execute_terminal_command(self) -> None:
        """Execute command in the terminal"""
        terminal_input = self.query_one("#terminal-input")
        command = terminal_input.value.strip()

        if not command:
            self.notify("Please enter a command", severity="warning")
            return

        # Clear the input
        terminal_input.value = ""

        # Add command to terminal output
        terminal_output = self.query_one("#terminal-output")
        current_output = terminal_output.text
        terminal_output.text = f"{current_output}\n$ {command}\n"

        # Add to history
        self.terminal_history.append(command)

        try:
            # Execute the command in the current directory
            import subprocess

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.current_directory,
            )

            # Add output to terminal
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += result.stderr

            # Update terminal with output
            terminal_output.text = f"{terminal_output.text}{output}"

            # Auto-scroll to bottom
            terminal_output.scroll_to_line(len(terminal_output.text.splitlines()) - 1)

        except Exception as e:
            # Show error
            terminal_output.text = f"{terminal_output.text}Error: {str(e)}\n"

        # Focus input for next command
        terminal_input.focus()


if __name__ == "__main__":
    app = TerminatorApp()
    app.run()
