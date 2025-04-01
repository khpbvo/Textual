"""
Panels Module - Provides resizable panel functionality for Terminator IDE
"""

import logging
from textual.app import App
from textual.events import MouseDown, MouseUp, MouseMove
from textual.widgets import Static
from textual.css.query import DOMQuery

class ResizablePanelsMixin:
    """
    Mixin class that provides resizable panel functionality for Textual apps.
    
    This mixin adds the following features:
    - Panel width tracking and initialization
    - Mouse event handlers for panel resizing
    - Automatic panel width constraints
    """
    
    def initialize_resizable_panels(self):
        """Initialize the resizable panel tracking state"""
        # Initialize resizable panel tracking
        self.resizing = False
        self.resizing_panel = None
        self.start_x = 0
        self.current_widths = {
            "sidebar": 20,           # Default sidebar width 20%
            "editor-container": 60,  # Default editor width 60%
            "ai-panel": 20           # Default AI panel width 20%
        }
    
    def apply_panel_widths(self):
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
    
    async def handle_gutter_mouse_down(self, event: MouseDown) -> None:
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
    
    async def handle_gutter_mouse_up(self, event: MouseUp) -> None:
        """Handle mouse up events to stop resizing"""
        if self.resizing:
            self.resizing = False
            self.resizing_panel = None
            
            # Release the mouse capture
            self.release_mouse()
    
    async def handle_gutter_mouse_move(self, event: MouseMove) -> None:
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
                return widget
        
        return None

# Panel CSS styles
PANEL_CSS = """
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
    cursor: col-resize;
    text-align: center;
    transition: background 0.1s;
}

.gutter:hover {
    background: $accent;
    color: $text;
}
"""