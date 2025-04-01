"""
LSP Client Module - Provides Language Server Protocol client functionality for Terminator IDE
"""

import os
import json
import uuid
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional, Callable, Tuple, Set, Union
from urllib.parse import urlparse, unquote
from pathlib import Path

logger = logging.getLogger(__name__)

class LSPClient:
    """
    Language Server Protocol client for communicating with language servers
    
    This class handles the communication between the IDE and language servers
    using the Language Server Protocol.
    """
    
    def __init__(self, server_cmd: List[str], workspace_path: str, language_id: str, name: str):
        """
        Initialize an LSP client
        
        Args:
            server_cmd: Command to start the language server
            workspace_path: Path to the workspace root directory
            language_id: Language identifier (e.g., 'python', 'typescript')
            name: Human-readable name for the language server
        """
        self.server_cmd = server_cmd
        self.workspace_path = workspace_path
        self.language_id = language_id
        self.name = name
        
        # Server process and communication
        self.process: Optional[subprocess.Popen] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        
        # Protocol state
        self.request_id = 0
        self.initialized = False
        self.running = False
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.notification_callbacks: Dict[str, List[Callable]] = {}
        
        # Server capabilities (populated after initialization)
        self.server_capabilities: Dict[str, Any] = {}
        
        # Tracking open documents
        self.open_documents: Set[str] = set()
    
    async def start(self) -> bool:
        """
        Start the language server process and initialize the connection
        
        Returns:
            True if the server was started successfully, False otherwise
        """
        try:
            logger.info(f"Starting language server: {self.name}")
            
            # Start the server process
            self.process = subprocess.Popen(
                self.server_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workspace_path,
                env=os.environ.copy()
            )
            
            # Set up communication streams
            self.reader, self.writer = await asyncio.open_connection(
                stdin=self.process.stdout,
                stdout=self.process.stdin
            )
            
            # Start message processing loop
            self.running = True
            asyncio.create_task(self._read_messages())
            
            # Initialize the server
            success = await self._initialize_server()
            if not success:
                logger.error(f"Failed to initialize language server: {self.name}")
                await self.stop()
                return False
                
            logger.info(f"Language server initialized: {self.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting language server: {str(e)}", exc_info=True)
            await self.stop()
            return False
    
    async def stop(self) -> None:
        """Stop the language server process and clean up resources"""
        if self.running:
            self.running = False
            
            try:
                # Send shutdown request
                if self.initialized:
                    await self.send_request("shutdown", {})
                    await self.send_notification("exit", {})
                
                # Close writer
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
                
                # Terminate process if still running
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try:
                        await asyncio.wait_for(asyncio.create_subprocess_exec(
                            *["kill", str(self.process.pid)]
                        ), timeout=2.0)
                    except asyncio.TimeoutError:
                        self.process.kill()
            
            except Exception as e:
                logger.error(f"Error stopping language server: {str(e)}", exc_info=True)
            finally:
                # Clean up resources
                self.initialized = False
                self.reader = None
                self.writer = None
                self.process = None
                self.pending_requests.clear()
                self.notification_callbacks.clear()
                self.open_documents.clear()
    
    async def _initialize_server(self) -> bool:
        """
        Initialize the language server with workspace and client information
        
        Returns:
            True if initialization was successful, False otherwise
        """
        # Build initialization parameters
        init_params = {
            "processId": os.getpid(),
            "clientInfo": {
                "name": "Terminator IDE",
                "version": "1.0.0"
            },
            "rootPath": self.workspace_path,
            "rootUri": self._path_to_uri(self.workspace_path),
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                        "resourceOperations": ["create", "rename", "delete"]
                    },
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True}
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                        "didSave": True
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True
                        },
                        "contextSupport": True
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"]
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True}
                        }
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 26))}
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "quickfix",
                                    "refactor",
                                    "refactor.extract",
                                    "refactor.inline",
                                    "refactor.rewrite",
                                    "source",
                                    "source.organizeImports"
                                ]
                            }
                        }
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True},
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "tagSupport": {"valueSet": [1, 2]}
                    }
                }
            },
            "trace": "verbose",
            "workspaceFolders": [
                {
                    "uri": self._path_to_uri(self.workspace_path),
                    "name": os.path.basename(self.workspace_path)
                }
            ]
        }
        
        try:
            # Send initialize request
            response = await self.send_request("initialize", init_params)
            
            if not response or "error" in response:
                error_msg = response.get("error", {}).get("message", "Unknown error") if response else "No response"
                logger.error(f"Language server initialization failed: {error_msg}")
                return False
            
            # Store server capabilities
            self.server_capabilities = response.get("capabilities", {})
            
            # Send initialized notification
            await self.send_notification("initialized", {})
            
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Error during language server initialization: {str(e)}", exc_info=True)
            return False
    
    async def _read_messages(self) -> None:
        """Read and process messages from the language server"""
        if not self.reader:
            return
            
        while self.running:
            try:
                # Read message headers
                header = ""
                while self.running:
                    line = await self.reader.readline()
                    if not line:
                        # EOF reached, server has closed the connection
                        logger.warning(f"Language server {self.name} closed the connection")
                        await self.stop()
                        return
                        
                    header += line.decode("utf-8")
                    if header.endswith("\r\n\r\n"):
                        break
                
                # Parse Content-Length
                content_length = 0
                for header_line in header.split("\r\n"):
                    if header_line.startswith("Content-Length:"):
                        content_length = int(header_line.split(":", 1)[1].strip())
                
                # Read message content
                if content_length > 0:
                    content = await self.reader.readexactly(content_length)
                    message = json.loads(content.decode("utf-8"))
                    
                    # Process the message
                    asyncio.create_task(self._handle_message(message))
            
            except (asyncio.CancelledError, asyncio.IncompleteReadError):
                # Connection closed or cancelled
                break
            except Exception as e:
                logger.error(f"Error reading LSP message: {str(e)}", exc_info=True)
                # Continue trying to read messages
    
    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle a message from the language server"""
        try:
            # Check message type
            if "id" in message and "result" in message:
                # Response to a request
                request_id = message["id"]
                if request_id in self.pending_requests:
                    future = self.pending_requests.pop(request_id)
                    future.set_result(message)
                else:
                    logger.warning(f"Received response for unknown request ID: {request_id}")
            
            elif "id" in message and "error" in message:
                # Error response
                request_id = message["id"]
                if request_id in self.pending_requests:
                    future = self.pending_requests.pop(request_id)
                    future.set_exception(Exception(f"LSP error: {message['error']}"))
                else:
                    logger.warning(f"Received error for unknown request ID: {request_id}")
            
            elif "method" in message and "id" in message:
                # Request from server
                # We don't implement handling server requests yet, so just respond with null
                await self.send_response(message["id"], None)
            
            elif "method" in message:
                # Notification from server
                method = message["method"]
                if method in self.notification_callbacks:
                    for callback in self.notification_callbacks[method]:
                        try:
                            await callback(message.get("params", {}))
                        except Exception as e:
                            logger.error(f"Error in notification callback: {str(e)}", exc_info=True)
            
            else:
                logger.warning(f"Received unknown message type: {message}")
        
        except Exception as e:
            logger.error(f"Error handling LSP message: {str(e)}", exc_info=True)
    
    async def send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a request to the language server
        
        Args:
            method: LSP method name
            params: Method parameters
            
        Returns:
            Server response
            
        Raises:
            Exception: If there is an error sending the request or
                      the server responds with an error
        """
        if not self.writer:
            raise Exception("Language server not connected")
            
        # Generate request ID
        self.request_id += 1
        request_id = self.request_id
        
        # Create request message
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        # Create future for the response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        # Send the request
        await self._send_message(request)
        
        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=30.0)
            
            if "error" in response:
                error_msg = response["error"].get("message", "Unknown error")
                code = response["error"].get("code", 0)
                logger.error(f"LSP error ({code}): {error_msg}")
                raise Exception(f"LSP error: {error_msg}")
                
            return response.get("result", {})
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            raise Exception(f"Timeout waiting for response to {method} request")
    
    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """
        Send a notification to the language server
        
        Args:
            method: LSP method name
            params: Method parameters
            
        Raises:
            Exception: If there is an error sending the notification
        """
        if not self.writer:
            raise Exception("Language server not connected")
            
        # Create notification message
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        # Send the notification
        await self._send_message(notification)
    
    async def send_response(self, request_id: int, result: Any) -> None:
        """
        Send a response to a server request
        
        Args:
            request_id: Request ID to respond to
            result: Response result
            
        Raises:
            Exception: If there is an error sending the response
        """
        if not self.writer:
            raise Exception("Language server not connected")
            
        # Create response message
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }
        
        # Send the response
        await self._send_message(response)
    
    async def _send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message to the language server
        
        Args:
            message: Message to send
            
        Raises:
            Exception: If there is an error sending the message
        """
        if not self.writer:
            raise Exception("Language server not connected")
            
        try:
            # Encode the message
            content = json.dumps(message).encode("utf-8")
            
            # Write the message with Content-Length header
            header = f"Content-Length: {len(content)}\r\n\r\n"
            self.writer.write(header.encode("utf-8"))
            self.writer.write(content)
            
            await self.writer.drain()
            
        except Exception as e:
            logger.error(f"Error sending LSP message: {str(e)}", exc_info=True)
            raise Exception(f"Failed to send message: {str(e)}")
    
    def register_notification_callback(self, method: str, callback: Callable) -> None:
        """
        Register a callback for server notifications
        
        Args:
            method: LSP notification method name
            callback: Async function to call when notification is received
        """
        if method not in self.notification_callbacks:
            self.notification_callbacks[method] = []
            
        self.notification_callbacks[method].append(callback)
    
    def unregister_notification_callback(self, method: str, callback: Callable) -> None:
        """
        Unregister a notification callback
        
        Args:
            method: LSP notification method name
            callback: Callback to unregister
        """
        if method in self.notification_callbacks:
            if callback in self.notification_callbacks[method]:
                self.notification_callbacks[method].remove(callback)
                
            if not self.notification_callbacks[method]:
                del self.notification_callbacks[method]
    
    async def text_document_did_open(self, uri: str, language_id: str, text: str) -> None:
        """
        Notify the server that a document has been opened
        
        Args:
            uri: Document URI
            language_id: Language identifier
            text: Document text
        """
        await self.send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": 1,
                "text": text
            }
        })
        
        self.open_documents.add(uri)
    
    async def text_document_did_change(self, uri: str, text: str, version: int) -> None:
        """
        Notify the server that a document has changed
        
        Args:
            uri: Document URI
            text: New document text
            version: Document version
        """
        # Check if we're using incremental or full sync
        sync_kind = self.server_capabilities.get("textDocumentSync", {})
        if isinstance(sync_kind, dict):
            sync_kind = sync_kind.get("change", 1)  # Default to full sync
        
        if sync_kind == 2:  # Incremental sync
            # For simplicity, we're always sending full content for now
            # A proper implementation would calculate changes
            await self.send_notification("textDocument/didChange", {
                "textDocument": {
                    "uri": uri,
                    "version": version
                },
                "contentChanges": [
                    {
                        "text": text
                    }
                ]
            })
        else:  # Full sync
            await self.send_notification("textDocument/didChange", {
                "textDocument": {
                    "uri": uri,
                    "version": version
                },
                "contentChanges": [
                    {
                        "text": text
                    }
                ]
            })
    
    async def text_document_did_close(self, uri: str) -> None:
        """
        Notify the server that a document has been closed
        
        Args:
            uri: Document URI
        """
        await self.send_notification("textDocument/didClose", {
            "textDocument": {
                "uri": uri
            }
        })
        
        self.open_documents.discard(uri)
    
    async def get_completion(self, uri: str, position: Dict[str, int], 
                           trigger_kind: int = 1, 
                           trigger_character: Optional[str] = None) -> Dict[str, Any]:
        """
        Request completion items at a position
        
        Args:
            uri: Document URI
            position: Position in the document (line, character)
            trigger_kind: Completion trigger kind (1 = invoked, 2 = trigger character, 3 = re-trigger)
            trigger_character: Character that triggered completion (if applicable)
            
        Returns:
            Completion items
        """
        params = {
            "textDocument": {
                "uri": uri
            },
            "position": position,
            "context": {
                "triggerKind": trigger_kind
            }
        }
        
        if trigger_character:
            params["context"]["triggerCharacter"] = trigger_character
            
        return await self.send_request("textDocument/completion", params)
    
    async def get_hover(self, uri: str, position: Dict[str, int]) -> Dict[str, Any]:
        """
        Request hover information at a position
        
        Args:
            uri: Document URI
            position: Position in the document (line, character)
            
        Returns:
            Hover information
        """
        params = {
            "textDocument": {
                "uri": uri
            },
            "position": position
        }
            
        return await self.send_request("textDocument/hover", params)
    
    async def get_definition(self, uri: str, position: Dict[str, int]) -> Dict[str, Any]:
        """
        Request definition locations for a symbol
        
        Args:
            uri: Document URI
            position: Position in the document (line, character)
            
        Returns:
            Definition locations
        """
        params = {
            "textDocument": {
                "uri": uri
            },
            "position": position
        }
            
        return await self.send_request("textDocument/definition", params)
    
    async def get_references(self, uri: str, position: Dict[str, int], 
                           include_declaration: bool = True) -> Dict[str, Any]:
        """
        Request references to a symbol
        
        Args:
            uri: Document URI
            position: Position in the document (line, character)
            include_declaration: Whether to include the declaration in results
            
        Returns:
            Reference locations
        """
        params = {
            "textDocument": {
                "uri": uri
            },
            "position": position,
            "context": {
                "includeDeclaration": include_declaration
            }
        }
            
        return await self.send_request("textDocument/references", params)
    
    async def format_document(self, uri: str) -> List[Dict[str, Any]]:
        """
        Request document formatting
        
        Args:
            uri: Document URI
            
        Returns:
            Text edits to format the document
        """
        params = {
            "textDocument": {
                "uri": uri
            },
            "options": {
                "tabSize": 4,
                "insertSpaces": True
            }
        }
            
        return await self.send_request("textDocument/formatting", params)
    
    def _path_to_uri(self, path: str) -> str:
        """Convert a local file path to a URI"""
        path = os.path.abspath(os.path.normpath(path))
        return f"file://{path}"
    
    def _uri_to_path(self, uri: str) -> str:
        """Convert a URI to a local file path"""
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError(f"Only file:// URIs are supported, got {uri}")
            
        path = parsed.path
        
        # Handle Windows paths
        if os.name == "nt":
            if path.startswith("/"):
                path = path[1:]
            path = path.replace("/", "\\")
            
        return unquote(path)


class LanguageServerManager:
    """
    Manages multiple language servers for different languages
    
    This class keeps track of language servers for different languages
    and routes requests to the appropriate server based on file type.
    """
    
    # Default server commands for common languages
    DEFAULT_SERVERS = {
        "python": {
            "command": ["pylsp"],
            "name": "Python Language Server",
            "file_extensions": [".py", ".pyi"]
        },
        "typescript": {
            "command": ["typescript-language-server", "--stdio"],
            "name": "TypeScript Language Server",
            "file_extensions": [".ts", ".tsx", ".js", ".jsx"]
        },
        "json": {
            "command": ["vscode-json-language-server", "--stdio"],
            "name": "JSON Language Server",
            "file_extensions": [".json"]
        },
        "html": {
            "command": ["vscode-html-language-server", "--stdio"],
            "name": "HTML Language Server",
            "file_extensions": [".html", ".htm"]
        },
        "css": {
            "command": ["vscode-css-language-server", "--stdio"],
            "name": "CSS Language Server",
            "file_extensions": [".css", ".scss", ".less"]
        }
    }
    
    def __init__(self, workspace_path: str):
        """
        Initialize the language server manager
        
        Args:
            workspace_path: Path to the workspace root directory
        """
        self.workspace_path = workspace_path
        self.servers: Dict[str, LSPClient] = {}
        self.file_extension_map: Dict[str, str] = {}
        
        # Build file extension map from default servers
        for lang_id, info in self.DEFAULT_SERVERS.items():
            for ext in info["file_extensions"]:
                self.file_extension_map[ext] = lang_id
    
    async def start_server(self, language_id: str) -> bool:
        """
        Start a language server for a specific language
        
        Args:
            language_id: Language identifier
            
        Returns:
            True if the server was started successfully, False otherwise
        """
        if language_id in self.servers:
            # Server already started
            return True
            
        if language_id not in self.DEFAULT_SERVERS:
            logger.error(f"No language server configured for {language_id}")
            return False
            
        server_info = self.DEFAULT_SERVERS[language_id]
        
        # Create and start the server
        client = LSPClient(
            server_cmd=server_info["command"],
            workspace_path=self.workspace_path,
            language_id=language_id,
            name=server_info["name"]
        )
        
        success = await client.start()
        if success:
            self.servers[language_id] = client
            return True
        else:
            return False
    
    async def stop_all_servers(self) -> None:
        """Stop all running language servers"""
        for client in self.servers.values():
            await client.stop()
            
        self.servers.clear()
    
    def get_language_id_for_file(self, file_path: str) -> Optional[str]:
        """
        Determine the language identifier for a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language identifier or None if not supported
        """
        _, ext = os.path.splitext(file_path)
        return self.file_extension_map.get(ext)
    
    def get_server_for_file(self, file_path: str) -> Optional[LSPClient]:
        """
        Get the language server for a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language server client or None if not supported
        """
        language_id = self.get_language_id_for_file(file_path)
        if not language_id:
            return None
            
        return self.servers.get(language_id)
    
    async def ensure_server_for_file(self, file_path: str) -> Optional[LSPClient]:
        """
        Ensure a language server is running for a file type
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language server client or None if not supported
        """
        language_id = self.get_language_id_for_file(file_path)
        if not language_id:
            return None
            
        if language_id not in self.servers:
            success = await self.start_server(language_id)
            if not success:
                return None
                
        return self.servers[language_id]