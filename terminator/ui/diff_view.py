"""
Diff View Module - Provides UI components for displaying code diffs in Terminator IDE
"""

import difflib
from typing import Dict, List, Tuple, Optional

from textual.screen import ModalScreen
from textual.widgets import (
    Button, Horizontal, Static, Label, TextArea, Container
)
from textual.reactive import reactive
from textual.app import ComposeResult

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
            if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
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
    
    @staticmethod
    def highlight_changes(text: str, line_changes: List[int]) -> str:
        """Add highlight markup to changed lines in text"""
        lines = text.splitlines()
        result = []
        
        for i, line in enumerate(lines):
            if i in line_changes:
                result.append(f"[bold red]{line}[/bold red]")
            else:
                result.append(line)
                
        return '\n'.join(result)

class DiffViewScreen(ModalScreen):
    """Modal screen for displaying code diffs"""
    
    show_unified = reactive(False)
    
    def __init__(self, 
                 original_content: str, 
                 modified_content: str, 
                 title: str = "Code Changes",
                 original_title: str = "Original",
                 modified_title: str = "Modified",
                 highlight_language: str = "python",
                 on_apply_callback = None):
        """
        Initialize the diff view screen
        
        Args:
            original_content: Original content
            modified_content: Modified content
            title: Title of the diff view
            original_title: Title for the original content panel
            modified_title: Title for the modified content panel
            highlight_language: Language for syntax highlighting
            on_apply_callback: Function to call when changes are applied
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
        yield Container(id="diff-view-container")
        self._refresh_view()
    
    def _refresh_view(self) -> None:
        """Refresh the diff view based on current state"""
        container = self.query_one("#diff-view-container")
        container.remove_children()
        
        with container:
            yield Label(self.screen_title, id="diff-title")
            
            if self.show_unified:
                # Unified diff view
                yield TextArea(self.unified_diff, language="diff", id="unified-diff", read_only=True)
            else:
                # Side-by-side diff view
                with Horizontal(id="diff-split-view"):
                    with Container(id="diff-original-container"):
                        yield Label(self.original_title, id="diff-original-title")
                        yield TextArea(
                            self.original_content,
                            language=self.language,
                            id="diff-original-content",
                            read_only=True
                        )
                    
                    with Container(id="diff-modified-container"):
                        yield Label(self.modified_title, id="diff-modified-title")
                        yield TextArea(
                            self.modified_content,
                            language=self.language,
                            id="diff-modified-content",
                            read_only=True
                        )
            
            with Horizontal(id="diff-buttons"):
                yield Button("Apply Changes", id="apply-diff", variant="success")
                yield Button("Toggle Unified View", id="toggle-unified-view")
                yield Button("Close", id="close-diff", variant="error")
    
    def on_mount(self) -> None:
        """Called when the screen is mounted"""
        # Apply custom CSS classes to highlight changed lines
        self._highlight_changes()
        
        # Add key binding for escape key
        self.add_key_binding("escape", "close")
    
    def action_close(self) -> None:
        """Close the diff view"""
        self.app.pop_screen()
    
    def _highlight_changes(self) -> None:
        """Highlight the lines that have changed in both panels"""
        # This is a basic implementation - for a production app, 
        # you would use proper CSS styling to highlight changes
        try:
            # Create CSS for highlighting original lines that were changed
            original_editor = self.query_one("#diff-original-content", TextArea)
            for line_num in self.changed_lines["original"]:
                # Apply highlighting to the lines that were changed in the original
                pass  # This would require custom rendering in a full implementation
            
            # Create CSS for highlighting modified lines that were changed    
            modified_editor = self.query_one("#diff-modified-content", TextArea)
            for line_num in self.changed_lines["modified"]:
                # Apply highlighting to the lines that were changed in the modified
                pass  # This would require custom rendering in a full implementation
        except Exception:
            # The side-by-side view might not be active
            pass
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the diff view"""
        button_id = event.button.id
        
        if button_id == "toggle-unified-view":
            # Toggle between unified and side-by-side view
            self.show_unified = not self.show_unified
            self._refresh_view()
        
        elif button_id == "apply-diff":
            # Apply the changes
            if self.on_apply_callback:
                self.on_apply_callback(self.modified_content)
            # Close the screen
            self.app.pop_screen()
        
        elif button_id == "close-diff":
            # Close without applying changes
            self.app.pop_screen()

# CSS for the diff view
DIFF_VIEW_CSS = """
#diff-view-container {
    width: 95%;
    height: 90%;
    margin: 2 2;
    background: $surface;
    border: solid $accent;
    padding: 1;
}

#diff-title {
    text-align: center;
    background: $primary;
    color: $text;
    padding: 1;
    margin-bottom: 1;
    font-weight: bold;
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
}

#diff-original-content, #diff-modified-content, #unified-diff {
    height: 100%;
    border: solid $panel-darken-1;
}

#diff-buttons {
    width: 100%;
    height: 3;
    align-horizontal: center;
    margin-top: 1;
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
"""