"""
LSP Features Module - Provides feature providers for Language Server Protocol integration
"""

import os
import logging
import asyncio
from typing import Dict, List, Any, Optional, Callable, Tuple, Set, Union

from .client import LSPClient, LanguageServerManager

logger = logging.getLogger(__name__)

class CompletionProvider:
    """
    Provides code completion using LSP
    
    This class handles code completion requests and results from language servers
    and converts them to a format usable by the Terminator IDE.
    """
    
    def __init__(self, server_manager: LanguageServerManager):
        """
        Initialize the completion provider
        
        Args:
            server_manager: Language server manager instance
        """
        self.server_manager = server_manager
    
    async def get_completions(self, file_path: str, position: Dict[str, int],
                             trigger_char: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get completion items at a position in a file
        
        Args:
            file_path: Path to the file
            position: Position in the document (line, character)
            trigger_char: Character that triggered completion (if applicable)
            
        Returns:
            List of completion items
        """
        try:
            # Get the language server for this file
            server = await self.server_manager.ensure_server_for_file(file_path)
            if not server:
                logger.warning(f"No language server available for {file_path}")
                return []
                
            # Determine trigger kind
            trigger_kind = 1  # Invoked
            if trigger_char:
                trigger_kind = 2  # Trigger character
                
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Request completions
            result = await server.get_completion(uri, position, trigger_kind, trigger_char)
            
            # Process results
            items = []
            if "items" in result:
                # CompletionList format
                items = result["items"]
            elif isinstance(result, list):
                # Direct array of CompletionItems
                items = result
                
            # Convert to Terminator format
            completions = []
            for item in items:
                completions.append({
                    "label": item.get("label", ""),
                    "kind": item.get("kind", 1),
                    "detail": item.get("detail", ""),
                    "documentation": self._extract_documentation(item),
                    "insert_text": item.get("insertText", item.get("label", "")),
                    "sort_text": item.get("sortText", item.get("label", "")),
                    "filter_text": item.get("filterText", item.get("label", "")),
                    "is_snippet": item.get("insertTextFormat", 1) == 2
                })
                
            return completions
            
        except Exception as e:
            logger.error(f"Error getting completions: {str(e)}", exc_info=True)
            return []
    
    def _extract_documentation(self, item: Dict[str, Any]) -> str:
        """Extract documentation from a completion item"""
        doc = item.get("documentation", "")
        if isinstance(doc, dict):
            # MarkupContent format
            return doc.get("value", "")
        return doc


class DiagnosticsProvider:
    """
    Provides diagnostics (errors, warnings) using LSP
    
    This class handles diagnostics notifications from language servers
    and converts them to a format usable by the Terminator IDE.
    """
    
    def __init__(self, server_manager: LanguageServerManager):
        """
        Initialize the diagnostics provider
        
        Args:
            server_manager: Language server manager instance
        """
        self.server_manager = server_manager
        self.diagnostics_callbacks: List[Callable[[str, List[Dict[str, Any]]], None]] = []
        
        # Set up notification handlers for all servers
        for server in server_manager.servers.values():
            server.register_notification_callback(
                "textDocument/publishDiagnostics",
                self._handle_diagnostics
            )
    
    def register_callback(self, callback: Callable[[str, List[Dict[str, Any]]], None]) -> None:
        """
        Register a callback for diagnostics updates
        
        Args:
            callback: Function to call when diagnostics are updated for a file
                     Takes (file_path, diagnostics) arguments
        """
        self.diagnostics_callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable[[str, List[Dict[str, Any]]], None]) -> None:
        """
        Unregister a diagnostics callback
        
        Args:
            callback: Callback to unregister
        """
        if callback in self.diagnostics_callbacks:
            self.diagnostics_callbacks.remove(callback)
    
    async def _handle_diagnostics(self, params: Dict[str, Any]) -> None:
        """Handle diagnostics notification from a language server"""
        try:
            uri = params.get("uri", "")
            if not uri.startswith("file://"):
                return
                
            # Convert URI to file path
            file_path = uri[7:]  # Remove "file://"
            
            # Convert diagnostics to Terminator format
            diagnostics = []
            for diag in params.get("diagnostics", []):
                severity = self._map_severity(diag.get("severity", 1))
                
                diagnostics.append({
                    "severity": severity,
                    "message": diag.get("message", ""),
                    "range": diag.get("range", {}),
                    "code": diag.get("code", ""),
                    "source": diag.get("source", "")
                })
                
            # Notify callbacks
            for callback in self.diagnostics_callbacks:
                callback(file_path, diagnostics)
                
        except Exception as e:
            logger.error(f"Error handling diagnostics: {str(e)}", exc_info=True)
    
    def _map_severity(self, lsp_severity: int) -> str:
        """Map LSP severity to Terminator severity"""
        severity_map = {
            1: "error",
            2: "warning",
            3: "information",
            4: "hint"
        }
        return severity_map.get(lsp_severity, "information")


class HoverProvider:
    """
    Provides hover information using LSP
    
    This class handles hover requests and results from language servers
    and converts them to a format usable by the Terminator IDE.
    """
    
    def __init__(self, server_manager: LanguageServerManager):
        """
        Initialize the hover provider
        
        Args:
            server_manager: Language server manager instance
        """
        self.server_manager = server_manager
    
    async def get_hover(self, file_path: str, position: Dict[str, int]) -> Dict[str, Any]:
        """
        Get hover information at a position in a file
        
        Args:
            file_path: Path to the file
            position: Position in the document (line, character)
            
        Returns:
            Hover information
        """
        try:
            # Get the language server for this file
            server = await self.server_manager.ensure_server_for_file(file_path)
            if not server:
                logger.warning(f"No language server available for {file_path}")
                return {"contents": ""}
                
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Request hover info
            result = await server.get_hover(uri, position)
            
            # Extract contents
            contents = result.get("contents", "")
            if isinstance(contents, dict):
                # MarkupContent format
                return {
                    "contents": contents.get("value", ""),
                    "is_markdown": contents.get("kind", "plaintext") == "markdown",
                    "range": result.get("range")
                }
            elif isinstance(contents, list):
                # Array of MarkedString
                values = []
                for item in contents:
                    if isinstance(item, str):
                        values.append(item)
                    elif isinstance(item, dict):
                        values.append(item.get("value", ""))
                        
                return {
                    "contents": "\n\n".join(values),
                    "is_markdown": True,
                    "range": result.get("range")
                }
            else:
                # Plain string
                return {
                    "contents": contents,
                    "is_markdown": False,
                    "range": result.get("range")
                }
                
        except Exception as e:
            logger.error(f"Error getting hover info: {str(e)}", exc_info=True)
            return {"contents": ""}


class DefinitionProvider:
    """
    Provides definition locations using LSP
    
    This class handles definition requests and results from language servers
    and converts them to a format usable by the Terminator IDE.
    """
    
    def __init__(self, server_manager: LanguageServerManager):
        """
        Initialize the definition provider
        
        Args:
            server_manager: Language server manager instance
        """
        self.server_manager = server_manager
    
    async def get_definition(self, file_path: str, position: Dict[str, int]) -> List[Dict[str, Any]]:
        """
        Get definition locations for a symbol
        
        Args:
            file_path: Path to the file
            position: Position in the document (line, character)
            
        Returns:
            List of definition locations
        """
        try:
            # Get the language server for this file
            server = await self.server_manager.ensure_server_for_file(file_path)
            if not server:
                logger.warning(f"No language server available for {file_path}")
                return []
                
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Request definition
            result = await server.get_definition(uri, position)
            
            # Process results
            locations = []
            if isinstance(result, list):
                # Array of Locations
                for loc in result:
                    locations.append(self._convert_location(loc))
            elif result and isinstance(result, dict):
                # Single Location
                locations.append(self._convert_location(result))
                
            return locations
            
        except Exception as e:
            logger.error(f"Error getting definition: {str(e)}", exc_info=True)
            return []
    
    def _convert_location(self, location: Dict[str, Any]) -> Dict[str, Any]:
        """Convert LSP location to Terminator format"""
        uri = location.get("uri", "")
        if uri.startswith("file://"):
            file_path = uri[7:]  # Remove "file://"
        else:
            file_path = uri
            
        return {
            "file_path": file_path,
            "range": location.get("range", {})
        }


class ReferenceProvider:
    """
    Provides reference locations using LSP
    
    This class handles reference requests and results from language servers
    and converts them to a format usable by the Terminator IDE.
    """
    
    def __init__(self, server_manager: LanguageServerManager):
        """
        Initialize the reference provider
        
        Args:
            server_manager: Language server manager instance
        """
        self.server_manager = server_manager
    
    async def get_references(self, file_path: str, position: Dict[str, int],
                           include_declaration: bool = True) -> List[Dict[str, Any]]:
        """
        Get reference locations for a symbol
        
        Args:
            file_path: Path to the file
            position: Position in the document (line, character)
            include_declaration: Whether to include the declaration
            
        Returns:
            List of reference locations
        """
        try:
            # Get the language server for this file
            server = await self.server_manager.ensure_server_for_file(file_path)
            if not server:
                logger.warning(f"No language server available for {file_path}")
                return []
                
            # Convert file path to URI
            uri = f"file://{os.path.abspath(file_path)}"
            
            # Request references
            result = await server.get_references(uri, position, include_declaration)
            
            # Process results
            locations = []
            if isinstance(result, list):
                # Array of Locations
                for loc in result:
                    locations.append(self._convert_location(loc))
                
            return locations
            
        except Exception as e:
            logger.error(f"Error getting references: {str(e)}", exc_info=True)
            return []
    
    def _convert_location(self, location: Dict[str, Any]) -> Dict[str, Any]:
        """Convert LSP location to Terminator format"""
        uri = location.get("uri", "")
        if uri.startswith("file://"):
            file_path = uri[7:]  # Remove "file://"
        else:
            file_path = uri
            
        return {
            "file_path": file_path,
            "range": location.get("range", {}),
            "is_declaration": location.get("isDeclaration", False)
        }