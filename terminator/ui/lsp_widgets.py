"""
LSP Widgets Module - UI components for LSP integration
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Callable, Tuple, Set, Union

from textual.app import ComposeResult
from textual.widgets import Static, Label, Button
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.containers import Container, ScrollableContainer
logger = logging.getLogger(__name__)

class HoverTooltip(Static):
    """Tooltip to display hover information"""
    
    DEFAULT_CSS = """
    HoverTooltip {
        layer: tooltip;
        background: $surface;
        border: solid $accent;
        padding: 1;
        max-width: 80;
        max-height: 20;
        overflow: auto;
    }
    """
    
    hover_content = reactive("")
    is_markdown = reactive(False)
    
    def __init__(self, content: str = "", is_markdown: bool = False):
        """
        Initialize the hover tooltip
        
        Args:
            content: Hover content
            is_markdown: Whether the content is markdown
        """
        super().__init__()
        self.hover_content = content
        self.is_markdown = is_markdown
    
    def render(self):
        """Render the tooltip content"""
        if self.is_markdown:
            return f"[markdown]{self.hover_content}[/markdown]"
        return self.hover_content


class CompletionMenu(Container):
    """Menu for displaying completion items"""
    
    DEFAULT_CSS = """
    CompletionMenu {
        layer: menu;
        background: $surface;
        border: solid $accent;
        padding: 0;
        max-width: 60;
        max-height: 15;
        overflow: auto;
    }
    
    .completion-item {
        padding: 0 1;
    }
    
    .completion-item-selected {
        background: $accent;
        color: $text;
    }
    
    .completion-kind-icon {
        width: 2;
        margin-right: 1;
        color: $text-muted;
    }
    """
    
    def __init__(self, items: List[Dict[str, Any]] = None):
        """
        Initialize the completion menu
        
        Args:
            items: List of completion items
        """
        super().__init__()
        self.items = items or []
        self.selected_index = 0
    
    def compose(self) -> ComposeResult:
        """Create the menu items"""
        if not self.items:
            yield Label("No suggestions", classes="completion-item")
            return
            
        for i, item in enumerate(self.items):
            # Get item properties
            label = item.get("label", "")
            kind = item.get("kind", 1)
            detail = item.get("detail", "")
            
            # Get icon for the kind
            kind_icon = self._get_kind_icon(kind)
            
            # Create classes based on selection
            classes = "completion-item"
            if i == self.selected_index:
                classes += " completion-item-selected"
                
            # Create the item
            if detail:
                label_text = f"{kind_icon} {label} - {detail}"
            else:
                label_text = f"{kind_icon} {label}"
                
            yield Label(label_text, classes=classes, id=f"completion-{i}")
    
    def select_next(self) -> None:
        """Select the next completion item"""
        if not self.items:
            return
            
        # Unselect current item
        current = self.query_one(f"#completion-{self.selected_index}")
        current.remove_class("completion-item-selected")
        
        # Select next item
        self.selected_index = (self.selected_index + 1) % len(self.items)
        next_item = self.query_one(f"#completion-{self.selected_index}")
        next_item.add_class("completion-item-selected")
    
    def select_previous(self) -> None:
        """Select the previous completion item"""
        if not self.items:
            return
            
        # Unselect current item
        current = self.query_one(f"#completion-{self.selected_index}")
        current.remove_class("completion-item-selected")
        
        # Select previous item
        self.selected_index = (self.selected_index - 1) % len(self.items)
        prev_item = self.query_one(f"#completion-{self.selected_index}")
        prev_item.add_class("completion-item-selected")
    
    def get_selected_item(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected completion item"""
        if not self.items:
            return None
            
        return self.items[self.selected_index]
    
    def _get_kind_icon(self, kind: int) -> str:
        """Get icon for a completion item kind"""
        # Icons for different completion item kinds
        kind_icons = {
            1: "[f]",      # Text
            2: "[M]",      # Method
            3: "[F]",      # Function
            4: "[C]",      # Constructor
            5: "[f]",      # Field
            6: "[V]",      # Variable
            7: "[C]",      # Class
            8: "[I]",      # Interface
            9: "[M]",      # Module
            10: "[P]",     # Property
            11: "[U]",     # Unit
            12: "[V]",     # Value
            13: "[E]",     # Enum
            14: "[K]",     # Keyword
            15: "[S]",     # Snippet
            16: "[C]",     # Color
            17: "[F]",     # File
            18: "[R]",     # Reference
            19: "[F]",     # Folder
            20: "[E]",     # EnumMember
            21: "[C]",     # Constant
            22: "[S]",     # Struct
            23: "[E]",     # Event
            24: "[O]",     # Operator
            25: "[T]",     # TypeParameter
        }
        
        return kind_icons.get(kind, "[?]")


class DiagnosticsPanel(Container):
    """Panel for displaying diagnostics (errors, warnings)"""
    
    DEFAULT_CSS = """
    DiagnosticsPanel {
        background: $surface;
        border-top: solid $accent;
        height: 10;
        overflow: auto;
    }
    
    .diagnostics-title {
        text-align: center;
        background: $primary;
        color: $text;
        margin-bottom: 1;
    }
    
    .diagnostic-error {
        color: $error;
        margin-bottom: 0;
        padding: 0 1;
    }
    
    .diagnostic-warning {
        color: $warning;
        margin-bottom: 0;
        padding: 0 1;
    }
    
    .diagnostic-info {
        color: $info;
        margin-bottom: 0;
        padding: 0 1;
    }
    """
    
    def __init__(self):
        """Initialize the diagnostics panel"""
        super().__init__()
        self.diagnostics_by_file: Dict[str, List[Dict[str, Any]]] = {}
    
    def compose(self) -> ComposeResult:
        """Create the panel layout"""
        yield Label("Problems", classes="diagnostics-title")
        yield ScrollableContainer(id="diagnostics-container")
    
    def update_diagnostics(self, file_path: str, diagnostics: List[Dict[str, Any]]) -> None:
        """
        Update diagnostics for a file
        
        Args:
            file_path: Path to the file
            diagnostics: List of diagnostic items
        """
        # Update our tracking
        self.diagnostics_by_file[file_path] = diagnostics
        
        # Refresh the display
        self._refresh_display()
    
    def _refresh_display(self) -> None:
        """Refresh the diagnostics display"""
        container = self.query_one("#diagnostics-container")
        container.remove_children()
        
        # Display diagnostics grouped by file
        for file_path, items in self.diagnostics_by_file.items():
            if not items:
                continue
                
            # Add file header
            container.mount(Label(f"File: {file_path}", classes="diagnostics-file-header"))
            
            # Add each diagnostic
            for diag in items:
                severity = diag.get("severity", "information")
                message = diag.get("message", "")
                source = diag.get("source", "")
                
                # Get position info
                range_info = diag.get("range", {})
                line = range_info.get("start", {}).get("line", 0) + 1  # LSP is 0-based
                
                # Format the diagnostic
                text = f"Line {line}: {message}"
                if source:
                    text += f" [{source}]"
                    
                # Create with appropriate class
                if severity == "error":
                    container.mount(Label(text, classes="diagnostic-error"))
                elif severity == "warning":
                    container.mount(Label(text, classes="diagnostic-warning"))
                else:
                    container.mount(Label(text, classes="diagnostic-info"))


class ReferencesPanel(ModalScreen):
    """Modal screen for displaying references to a symbol"""
    
    DEFAULT_CSS = """
    ReferencesPanel {
        align: center middle;
    }
    
    #references-container {
        background: $surface;
        border: solid $accent;
        padding: 1;
        width: 80%;
        height: 60%;
    }
    
    #references-title {
        text-align: center;
        background: $primary;
        color: $text;
        margin-bottom: 1;
    }
    
    #references-list {
        height: 80%;
        overflow: auto;
    }
    
    .reference-item {
        margin-bottom: 0;
        padding: 0 1;
    }
    
    .reference-item-selected {
        background: $accent-darken-2;
    }
    
    #references-buttons {
        margin-top: 1;
    }
    """
    
    def __init__(self, references: List[Dict[str, Any]], symbol_name: str = "symbol"):
        """
        Initialize the references panel
        
        Args:
            references: List of reference locations
            symbol_name: Name of the symbol being referenced
        """
        super().__init__()
        self.references = references
        self.symbol_name = symbol_name
        self.selected_index = 0
        
        # Callback for when a reference is selected
        self.on_select_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    
    def compose(self) -> ComposeResult:
        """Create the panel layout"""
        with Container(id="references-container"):
            title = f"References to '{self.symbol_name}'"
            yield Label(title, id="references-title")
            
            # List of references
            refs_container = ScrollableContainer(id="references-list")
            
            if not self.references:
                refs_container.mount(Label("No references found"))
            else:
                for i, ref in enumerate(self.references):
                    file_path = ref.get("file_path", "")
                    range_info = ref.get("range", {})
                    line = range_info.get("start", {}).get("line", 0) + 1  # LSP is 0-based
                    
                    # Format the reference item
                    text = f"{file_path}:{line}"
                    
                    # Create classes based on selection
                    classes = "reference-item"
                    if i == self.selected_index:
                        classes += " reference-item-selected"
                        
                    refs_container.mount(Label(text, classes=classes, id=f"reference-{i}"))
            
            yield refs_container
            
            # Buttons
            with Container(id="references-buttons"):
                yield Button("Go to Selected", id="goto-reference-btn")
                yield Button("Close", id="close-references-btn")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        if button_id == "goto-reference-btn":
            self._goto_selected()
        elif button_id == "close-references-btn":
            self.app.pop_screen()
    
    def _goto_selected(self) -> None:
        """Go to the selected reference"""
        if not self.references or not self.on_select_callback:
            return
            
        # Get the selected reference
        selected = self.references[self.selected_index]
        
        # Call the callback with the selected reference
        self.on_select_callback(selected)
        
        # Close the panel
        self.app.pop_screen()
    
    def select_next(self) -> None:
        """Select the next reference"""
        if not self.references:
            return
            
        # Unselect current item
        current = self.query_one(f"#reference-{self.selected_index}")
        current.remove_class("reference-item-selected")
        
        # Select next item
        self.selected_index = (self.selected_index + 1) % len(self.references)
        next_item = self.query_one(f"#reference-{self.selected_index}")
        next_item.add_class("reference-item-selected")
    
    def select_previous(self) -> None:
        """Select the previous reference"""
        if not self.references:
            return
            
        # Unselect current item
        current = self.query_one(f"#reference-{self.selected_index}")
        current.remove_class("reference-item-selected")
        
        # Select previous item
        self.selected_index = (self.selected_index - 1) % len(self.references)
        prev_item = self.query_one(f"#reference-{self.selected_index}")
        prev_item.add_class("reference-item-selected")