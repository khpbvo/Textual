"""
LSP Integration Module - Connects LSP functionality with Terminator IDE
"""

import os
import logging
import asyncio
from typing import Dict, List, Any, Optional, Callable, Tuple, Set, Union
from textual.app import App
from textual.widgets import TextArea

from .client import LSPClient, LanguageServerManager
from .features import (
    CompletionProvider, 
    DiagnosticsProvider, 
    HoverProvider, 
    DefinitionProvider, 
    ReferenceProvider
)

logger = logging.getLogger(__name__)

class LSPIntegration:
    """
    Integrates Language Server Protocol with Terminator IDE
    
    This class connects the LSP client functionality with the Terminator IDE UI,
    handling document synchronization, diagnostics display, and feature integration.
    """
    
    def __init__(self, app: App, workspace_path: str):
        """
        Initialize the LSP integration
        
        Args:
            app: Terminator app instance
            workspace_path: Path to the workspace root directory
        """
        self.app = app
        self.workspace_path = workspace_path
        
        # Initialize language server manager
        self.server_manager = LanguageServerManager(workspace_path)
        
        # Initialize feature providers
        self.completion_provider = CompletionProvider(self.server_manager)
        self.diagnostics_provider = DiagnosticsProvider(self.server_manager)
        self.hover_provider = HoverProvider(self.server_manager)
        self.definition_provider = DefinitionProvider(self.server_manager)
        self.reference_provider = ReferenceProvider(self.server_manager)
        
        # Track open documents and versions
        self.open_documents: Dict[str, int] = {}
        
        # Register diagnostics callback
        self.diagnostics_provider.register_callback(self._handle_diagnostics)
    
    async def initialize(self) -> None:
        """Initialize all required language servers"""
        # Start servers for common languages
        for lang_id in ["python", "typescript", "json"]:
            try:
                await self.server_manager.start_server(lang_id)
            except Exception as e:
                logger.error(f"Failed to start {lang_id} language server: {str(e)}", exc_info=True)
    
    async def shutdown(self) -> None:
        """Shutdown all language servers"""
        await self.server_manager.stop_all_servers()
    
    async def document_opened(self, file_path: str, content: str) -> None:
        """
        Notify that a document has been opened in the editor
        
        Args:
            file_path: Path to the file
            content: File content
        """
        try:
            # Get language ID for the file
            language_id = self.server_manager.get_language_id_for_file(file_path)
            if not language_id:
                return  # Unsupported file type
                
            # Get or start the language server
            server = await self.server_manager.ensure_server_for_file(file_path)
            if not server:
                return  # No server available
                
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Notify the server
            await server.text_document_did_open(uri, language_id, content)
            
            # Track document version
            self.open_documents[file_path] = 1
            
        except Exception as e:
            logger.error(f"Error handling document open: {str(e)}", exc_info=True)
    
    async def document_changed(self, file_path: str, content: str) -> None:
        """
        Notify that a document has been changed in the editor
        
        Args:
            file_path: Path to the file
            content: New file content
        """
        try:
            if file_path not in self.open_documents:
                # Document not opened yet
                await self.document_opened(file_path, content)
                return
                
            # Get the language server
            server = self.server_manager.get_server_for_file(file_path)
            if not server:
                return  # No server available
                
            # Increment document version
            self.open_documents[file_path] += 1
            version = self.open_documents[file_path]
            
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Notify the server
            await server.text_document_did_change(uri, content, version)
            
        except Exception as e:
            logger.error(f"Error handling document change: {str(e)}", exc_info=True)
    
    async def document_closed(self, file_path: str) -> None:
        """
        Notify that a document has been closed in the editor
        
        Args:
            file_path: Path to the file
        """
        try:
            if file_path not in self.open_documents:
                return  # Document not opened
                
            # Get the language server
            server = self.server_manager.get_server_for_file(file_path)
            if not server:
                return  # No server available
                
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Notify the server
            await server.text_document_did_close(uri)
            
            # Remove from tracking
            del self.open_documents[file_path]
            
        except Exception as e:
            logger.error(f"Error handling document close: {str(e)}", exc_info=True)
    
    async def get_completions_at_cursor(self, editor: TextArea, file_path: str,
                                      trigger_char: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get completion items at the cursor position
        
        Args:
            editor: Editor widget
            file_path: Path to the file being edited
            trigger_char: Character that triggered completion (if applicable)
            
        Returns:
            List of completion items
        """
        try:
            # Get cursor position
            cursor = editor.cursor
            position = {
                "line": cursor.row,
                "character": cursor.column
            }
            
            # Get completions
            return await self.completion_provider.get_completions(
                file_path, position, trigger_char
            )
            
        except Exception as e:
            logger.error(f"Error getting completions: {str(e)}", exc_info=True)
            return []
    
    async def get_hover_at_cursor(self, editor: TextArea, file_path: str) -> Dict[str, Any]:
        """
        Get hover information at the cursor position
        
        Args:
            editor: Editor widget
            file_path: Path to the file being edited
            
        Returns:
            Hover information
        """
        try:
            # Get cursor position
            cursor = editor.cursor
            position = {
                "line": cursor.row,
                "character": cursor.column
            }
            
            # Get hover info
            return await self.hover_provider.get_hover(file_path, position)
            
        except Exception as e:
            logger.error(f"Error getting hover info: {str(e)}", exc_info=True)
            return {"contents": ""}
    
    async def go_to_definition(self, editor: TextArea, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Go to the definition of the symbol at the cursor
        
        Args:
            editor: Editor widget
            file_path: Path to the file being edited
            
        Returns:
            Definition location or None if not found
        """
        try:
            # Get cursor position
            cursor = editor.cursor
            position = {
                "line": cursor.row,
                "character": cursor.column
            }
            
            # Get definition locations
            locations = await self.definition_provider.get_definition(file_path, position)
            
            if locations:
                # Return the first location
                return locations[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error going to definition: {str(e)}", exc_info=True)
            return None
    
    async def find_references(self, editor: TextArea, file_path: str) -> List[Dict[str, Any]]:
        """
        Find references to the symbol at the cursor
        
        Args:
            editor: Editor widget
            file_path: Path to the file being edited
            
        Returns:
            List of reference locations
        """
        try:
            # Get cursor position
            cursor = editor.cursor
            position = {
                "line": cursor.row,
                "character": cursor.column
            }
            
            # Get references
            return await self.reference_provider.get_references(file_path, position, True)
            
        except Exception as e:
            logger.error(f"Error finding references: {str(e)}", exc_info=True)
            return []
    
    async def format_document(self, file_path: str, content: str) -> Optional[str]:
        """
        Format a document
        
        Args:
            file_path: Path to the file
            content: File content
            
        Returns:
            Formatted content or None if formatting failed
        """
        try:
            # Get the language server
            server = await self.server_manager.ensure_server_for_file(file_path)
            if not server:
                return None  # No server available
                
            # Make sure the document is open
            if file_path not in self.open_documents:
                await self.document_opened(file_path, content)
                
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Request formatting
            edits = await server.format_document(uri)
            
            if not edits:
                return None  # No edits returned
                
            # Apply the edits to the content
            # This is a simplified implementation that assumes non-overlapping edits
            result = content
            
            # Sort edits in reverse order to apply them without affecting other edit positions
            sorted_edits = sorted(
                edits, 
                key=lambda e: (
                    e["range"]["start"]["line"],
                    e["range"]["start"]["character"]
                ),
                reverse=True
            )
            
            for edit in sorted_edits:
                result = self._apply_text_edit(result, edit)
                
            return result
            
        except Exception as e:
            logger.error(f"Error formatting document: {str(e)}", exc_info=True)
            return None
    
    def _handle_diagnostics(self, file_path: str, diagnostics: List[Dict[str, Any]]) -> None:
        """
        Handle diagnostics updates from language servers
        
        Args:
            file_path: Path to the file
            diagnostics: List of diagnostic items
        """
        try:
            # Convert to app notification or display in UI
            # This is a placeholder - actual implementation would depend on the app's UI
            
            # For example, in a real implementation:
            # 1. Update diagnostics markers in the editor
            # 2. Show error/warning counts in the status bar
            # 3. Populate problems panel
            
            # Count issues by severity
            counts = {"error": 0, "warning": 0, "information": 0, "hint": 0}
            for diag in diagnostics:
                severity = diag.get("severity", "information")
                counts[severity] += 1
                
            # Log for now
            if counts["error"] > 0 or counts["warning"] > 0:
                logger.info(
                    f"Diagnostics for {os.path.basename(file_path)}: "
                    f"{counts['error']} errors, {counts['warning']} warnings"
                )
                
            # In a real implementation, we would call methods on the app to update the UI
            
        except Exception as e:
            logger.error(f"Error handling diagnostics: {str(e)}", exc_info=True)
    
    def _apply_text_edit(self, text: str, edit: Dict[str, Any]) -> str:
        """
        Apply a text edit to a string
        
        Args:
            text: Original text
            edit: TextEdit object from LSP
            
        Returns:
            Modified text with the edit applied
        """
        try:
            # Extract edit information
            range_start = edit["range"]["start"]
            range_end = edit["range"]["end"]
            new_text = edit["newText"]
            
            # Convert range to string indices
            lines = text.splitlines(True)  # Keep line endings
            
            # Calculate start index
            start_index = 0
            for i in range(range_start["line"]):
                if i < len(lines):
                    start_index += len(lines[i])
            start_index += range_start["character"]
            
            # Calculate end index
            end_index = 0
            for i in range(range_end["line"]):
                if i < len(lines):
                    end_index += len(lines[i])
            end_index += range_end["character"]
            
            # Apply the edit
            return text[:start_index] + new_text + text[end_index:]
            
        except Exception as e:
            logger.error(f"Error applying text edit: {str(e)}", exc_info=True)
            return text  # Return original text on error