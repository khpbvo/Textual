"""
Diff View Module - Provides UI components for displaying code diffs in Terminator IDE
"""

import difflib
import asyncio
from typing import Dict, List, Tuple, Optional, Callable, Awaitable, Any

from textual.screen import ModalScreen
from textual.widgets import (
    Button, Static, Label, TextArea
)
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal

class CodeDiff:
    """Utility class for creating and analyzing code diffs"""
    
    @staticmethod
    def create_diff(original: str, modified: str) -> str:
        """Create a unified diff between original and modified text"""
        original_lines = original.splitlines()
        modified_lines = modified.splitlines()
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            lineterm='',
            n=3  # Context lines
        )
        
        return '\n'.join(diff)
    
    @staticmethod
    def extract_line_changes(unified_diff: str) -> Dict[str, List[int]]:
        """
        Extract changed line numbers from a unified diff
        
        Returns:
            Dict with keys 'original' and 'modified', each containing a list of line numbers
        """
        changes = {
            'original': [],
            'modified': []
        }
        
        current_original_line = 0
        current_modified_line = 0
        
        for line in unified_diff.splitlines():
            # Skip header lines
            if line.startswith('---') or line.startswith('+++'):
                continue
                
            if line.startswith('@@'):
                # Parse hunk header to get starting line numbers
                try:
                    _, original_range, modified_range = line.split(' ', 2)
                    current_original_line = int(original_range.split(',')[0].replace('-', '')) - 1
                    current_modified_line = int(modified_range.split(',')[0].replace('+', '')) - 1
                except Exception:
                    # If we can't parse the hunk header, just continue
                    continue
                continue
                
            if line.startswith('-'):
                # Line removed from original
                changes['original'].append(current_original_line)
                current_original_line += 1
            elif line.startswith('+'):
                # Line added in modified
                changes['modified'].append(current_modified_line)
                current_modified_line += 1
            else:
                # Context line (unchanged)
                current_original_line += 1
                current_modified_line += 1
                
        return changes


class DiffViewScreen(ModalScreen):
    """Modal screen for displaying code diffs"""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "apply", "Apply Changes"),
        Binding("tab", "toggle_view", "Toggle View")
    ]
    
    show_unified = reactive(False)
    
    def __init__(
        self, 
        original_content: str, 
        modified_content: str, 
        title: str = "Code Changes",
        original_title: str = "Original",
        modified_title: str = "Modified",
        highlight_language: str = "python",
        on_apply_callback: Optional[Callable[[str], Awaitable[Any]]] = None
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
            on_apply_callback: Async function to call when changes are applied
        """
        super().__init__()
        self.original_content = original_content
        self.modified_content = modified_content
        self.screen_title = title
        self.original_title = original_title
        self.modified_title = modified_title
        self.language = highlight_language
        self.on_apply_callback = on_apply_callback
        
        # Calculate the diff
        self.unified_diff = CodeDiff.create_diff(original_content, modified_content)
        
        # Extract line changes from diff
        self.changed_lines = CodeDiff.extract_line_changes(self.unified_diff)
    
    def compose(self) -> ComposeResult:
        """Create the diff view layout"""
        with Container(id="diff-view-container"):
            yield Label(self.screen_title, id="diff-title")

            # Always build both views; toggle visibility via class
            unified_classes = "" if self.show_unified else "hidden"
            split_classes = "hidden" if self.show_unified else ""

            yield TextArea(
                self.unified_diff,
                language=None,
                id="unified-diff",
                read_only=True,
                classes=unified_classes,
            )

            with Horizontal(id="diff-split-view", classes=split_classes):
                with Container(id="diff-original-container"):
                    yield Label(self.original_title, id="diff-original-title")
                    yield TextArea(
                        self.original_content,
                        language=self.language,
                        id="diff-original-content",
                        read_only=True,
                    )

                with Container(id="diff-modified-container"):
                    yield Label(self.modified_title, id="diff-modified-title")
                    yield TextArea(
                        self.modified_content,
                        language=self.language,
                        id="diff-modified-content",
                        read_only=True,
                    )

            with Horizontal(id="diff-buttons"):
                yield Button("Apply Changes", id="apply-diff", variant="success")
                yield Button("Toggle View", id="toggle-unified-view")
                yield Button("Close", id="close-diff", variant="error")
    
    def on_mount(self) -> None:
        """Called when the screen is mounted"""
        # Apply custom CSS classes to highlight changed lines
        self._highlight_changes()
        
    def watch_show_unified(self, show_unified: bool) -> None:
        """React to changes in the show_unified state by toggling visibility"""
        try:
            unified = self.query_one("#unified-diff", TextArea)
            split = self.query_one("#diff-split-view", Horizontal)
            if show_unified:
                split.add_class("hidden")
                unified.remove_class("hidden")
            else:
                unified.add_class("hidden")
                split.remove_class("hidden")
        except Exception:
            # Fall back to full refresh if needed
            self.refresh(repaint=True)
    
    def action_close(self) -> None:
        """Close the diff view"""
        self.app.pop_screen()
        
    def action_apply(self) -> None:
        """Apply the changes"""
        self._apply_changes()
        
    def action_toggle_view(self) -> None:
        """Toggle between unified and side-by-side view"""
        self.show_unified = not self.show_unified
    
    def _highlight_changes(self) -> None:
        """Highlight the lines that have changed in both panels"""
        try:
            if not self.show_unified:
                # Side-by-side view highlighting
                original_editor = self.query_one("#diff-original-content", TextArea)
                for line_num in self.changed_lines["original"]:
                    if 0 <= line_num < len(self.original_content.splitlines()):
                        # In the future, implement line-specific highlighting
                        pass
                
                modified_editor = self.query_one("#diff-modified-content", TextArea)
                for line_num in self.changed_lines["modified"]:
                    if 0 <= line_num < len(self.modified_content.splitlines()):
                        # In the future, implement line-specific highlighting
                        pass
        except Exception as e:
            # Log the error but don't crash
            import logging
            logging.error(f"Error highlighting diff lines: {str(e)}", exc_info=True)
    
    async def _apply_changes(self) -> None:
        """Apply the changes using the callback"""
        try:
            if self.on_apply_callback:
                # Use proper asyncio.create_task to not block
                asyncio.create_task(self._safe_apply_callback())
            self.app.pop_screen()
        except Exception as e:
            import logging
            logging.error(f"Error applying diff changes: {str(e)}", exc_info=True)
            
    async def _safe_apply_callback(self) -> None:
        """Safely apply the callback with error handling"""
        try:
            if callable(self.on_apply_callback):
                await self.on_apply_callback(self.modified_content)
        except Exception as e:
            import logging
            logging.error(f"Error in diff apply callback: {str(e)}", exc_info=True)
            # Notify the user through the app if possible
            if hasattr(self.app, "notify"):
                self.app.notify(f"Error applying changes: {str(e)}", severity="error")
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses asynchronously"""
        button_id = event.button.id

        if button_id == "close-diff":
            # Close without applying changes
            self.action_close()
        elif button_id == "apply-diff":
            # Apply the changes and close asynchronously
            await self._apply_changes()
        elif button_id == "toggle-unified-view":
            # Toggle between unified and side-by-side view
            self.show_unified = not self.show_unified


# Improved CSS for the diff view
DIFF_VIEW_CSS = """
#diff-view-container {
    width: 95%;
    height: 90%;
    margin: 2 2;
    background: $surface;
    border: solid $accent;
    border-radius: 1;
    padding: 1 1;
}

#diff-title {
    text-align: center;
    background: $primary;
    color: $text;
    padding: 1;
    margin-bottom: 1;
    font-weight: bold;
    border-radius: 1;
}

#diff-split-view {
    width: 100%;
    height: 80%;
}

#diff-original-container, #diff-modified-container {
    width: 50%;
    height: 100%;
    margin: 0 1;
}

#diff-original-title, #diff-modified-title {
    text-align: center;
    background: $panel;
    margin-bottom: 1;
    border-radius: 1;
}

#diff-original-content, #diff-modified-content, #unified-diff {
    height: 100%;
    border: solid $panel-darken-1;
    border-radius: 1;
}

#diff-buttons {
    width: 100%;
    height: 3;
    align-horizontal: center;
    margin-top: 1;
}

Button {
    margin: 0 1;
}

/* Highlight styles for diff views */
.diff-line-added {
    background: $success-darken-2;
    color: $text;
}

.diff-line-removed {
    background: $error-darken-2;
    color: $text;
}

/* Make the modal stand out more */
.diff-view-screen {
    background: rgba(0, 0, 0, 0.7);
}
"""
