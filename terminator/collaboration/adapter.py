"""
Adapter Module - Provides compatibility adapters for legacy collaboration code
"""

import json
import uuid
import time
import asyncio
import logging
try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover
    websockets = None  # type: ignore
from typing import Dict, List, Any, Optional, Set, Tuple, Union, Callable, Awaitable

from .session import (
    SessionManager,
    CollaborationSession as EnhancedCollaborationSession,
    User
)
from .shared_ai_session import (
    SharedAIManager,
    SharedAICollaborationIntegration,
    SharedAIContext
)
from .operational_transform import (
    Operation,
    InsertOperation,
    DeleteOperation
)
from .connection_pool import ConnectionPoolManager
from ..utils.performance import TimingProfiler

logger = logging.getLogger(__name__)

class CollaborationManager:
    """
    Adapter for the legacy collaboration manager
    
    Provides backwards compatibility with the old API while using
    the new enhanced collaboration module under the hood.
    """
    
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
        self.running = False
        
        # Use the enhanced session manager
        self.session_manager = SessionManager(use_connection_pooling=True)
        self.sessions: Dict[str, 'CollaborationSession'] = {}
        
        # Initialize shared AI session manager
        self.ai_manager = SharedAIManager()
        self.ai_integration = SharedAICollaborationIntegration(
            session_manager=self.session_manager,
            ai_manager=self.ai_manager
        )
        
    async def start_server(self) -> None:
        """Start the WebSocket server"""
        if self.running:
            return
            
        self.running = True
        await self.session_manager.start()
        self.server = await websockets.serve(
            self.handle_connection, 
            self.host, 
            self.port
        )
        logger.info(f"Collaboration server started on {self.host}:{self.port}")
        
    async def stop_server(self) -> None:
        """Stop the WebSocket server"""
        if not self.running:
            return
            
        self.running = False
        await self.session_manager.stop()
        
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        logger.info("Collaboration server stopped")
            
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
                
                # Get or create session using the enhanced session manager
                enhanced_session = self.session_manager.get_session(session_id)
                if not enhanced_session:
                    enhanced_session = self.session_manager.create_session(name=f"Session {session_id}")
                
                # Create adapter if needed
                if session_id not in self.sessions:
                    self.sessions[session_id] = CollaborationSession(
                        session_id=session_id,
                        enhanced_session=enhanced_session
                    )
                
                # Register with connection pool
                self.session_manager.register_client_with_connection_pool(
                    client_id=client_id,
                    session_id=session_id,
                    websocket=websocket
                )
                
                # Add user to session
                session = self.sessions[session_id]
                await session.add_user(client_id, username, websocket)
                
                # Welcome message
                await websocket.send(json.dumps({
                    "type": "welcome",
                    "session_id": session_id,
                    "client_id": client_id,
                    "message": f"Welcome to the collaboration session, {username}!"
                }))
                
                # Main message handling loop
                async for message in websocket:
                    data = json.loads(message)
                    
                    if data["type"] == "edit":
                        # Handle edit operation
                        await session.handle_edit(data, client_id)
                    elif data["type"] == "cursor_move":
                        # Handle cursor movement
                        await session.handle_cursor_move(data, client_id)
                    elif data["type"] == "chat":
                        # Handle chat message
                        await session.handle_chat(data, client_id)
                    elif data["type"] == "ai_message":
                        # Handle shared AI message
                        result = await self.ai_integration.handle_ai_message(
                            session_id=session_id,
                            client_id=client_id,
                            message=data["message"]
                        )
                        
                        # Send acknowledgment to the client
                        await websocket.send(json.dumps({
                            "type": "ai_result",
                            "result": result
                        }))
                    elif data["type"] == "get_ai_context":
                        # Get AI context for the session
                        result = await self.ai_integration.get_ai_context(
                            session_id=session_id
                        )
                        
                        # Send context to the client
                        await websocket.send(json.dumps({
                            "type": "ai_context",
                            "result": result
                        }))
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_id} connection closed")
        except Exception as e:
            logger.error(f"Collaboration error: {str(e)}", exc_info=True)
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
        
        # Create enhanced session
        enhanced_session = self.session_manager.create_session(name=f"Session {session_id}")
        
        # Create adapter
        self.sessions[session_id] = CollaborationSession(
            session_id=session_id,
            enhanced_session=enhanced_session
        )
        
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
            
            # Remove the session from both dictionaries
            del self.sessions[session_id]
            
            # The session_manager will clean up sessions automatically through its background tasks
            
            return True
        return False
        
    def register_ai_client(self, client: Any) -> None:
        """
        Register an AI client for shared AI sessions
        
        Args:
            client: AI client
        """
        self.ai_manager.register_ai_client(client)
        
    def register_ai_generate_callback(self, callback: Callable[[str, List[Dict[str, str]]], Awaitable[str]]) -> None:
        """
        Register a callback for generating AI responses
        
        Args:
            callback: Function that takes a context ID and messages, returns a response
        """
        self.ai_manager.register_generate_callback(callback)


class CollaborationSession:
    """
    Adapter for the legacy collaboration session
    
    Wraps the enhanced collaboration session with the legacy API.
    """
    
    def __init__(self, session_id: str, enhanced_session: EnhancedCollaborationSession):
        """
        Initialize a collaboration session
        
        Args:
            session_id: Session ID
            enhanced_session: The enhanced collaboration session
        """
        self.session_id = session_id
        self.enhanced_session = enhanced_session
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
        # Add to local tracking
        self.users[client_id] = {
            "username": username,
            "websocket": websocket,
            "joined_at": time.time(),
            "active": True
        }
        
        # Add to enhanced session
        await self.enhanced_session.add_user(client_id, username, websocket)
        
        # Send current state to new user
        # Enhanced session already does this, but we'll do it again for compatibility
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
            
            # Remove from enhanced session
            await self.enhanced_session.remove_user(client_id)
            
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
        # Enhanced session has better broadcasting with connection pooling
        # but we'll use the legacy approach for compatibility
        message_json = json.dumps(message)
        coros = []
        
        for user_data in self.users.values():
            if user_data["websocket"] != exclude and user_data["active"]:
                coros.append(user_data["websocket"].send(message_json))
                
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)
    
    @TimingProfiler.async_profile
    async def handle_edit(self, data: Dict[str, Any], client_id: str) -> None:
        """
        Handle an edit operation
        
        Args:
            data: Edit operation data
            client_id: Client ID
        """
        file_path = data["file_path"]
        legacy_operation = data["operation"]
        username = self.users[client_id]["username"]
        
        # Update file content using legacy approach for tracking
        if file_path not in self.file_content:
            self.file_content[file_path] = ""
            self.file_history[file_path] = []
        
        # Convert legacy operation to enhanced operation
        operation = None
        if legacy_operation["type"] == "insert":
            pos = legacy_operation["position"]
            text = legacy_operation["text"]
            operation = InsertOperation(pos, text)
            
            # Update legacy tracking
            content = self.file_content[file_path]
            self.file_content[file_path] = content[:pos] + text + content[pos:]
            
        elif legacy_operation["type"] == "delete":
            start = legacy_operation["start"]
            end = legacy_operation["end"]
            length = end - start
            operation = DeleteOperation(start, length)
            
            # Update legacy tracking
            content = self.file_content[file_path]
            self.file_content[file_path] = content[:start] + content[end:]
        
        # Record in legacy history
        self.file_history[file_path].append({
            "timestamp": time.time(),
            "client_id": client_id,
            "username": username,
            "operation": legacy_operation
        })
        
        # Handle with enhanced session for conflict resolution and chunking
        # We pass a synthesized edit data with the enhanced operation
        enhanced_data = {
            "file_path": file_path,
            "operation": operation.to_dict(),
            "version": 0  # The enhanced session will handle versioning
        }
        
        await self.enhanced_session.handle_edit(client_id, enhanced_data)
        
        # Enhanced session already broadcasts to other clients
        # No need to broadcast again
    
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
        
        # Handle with enhanced session
        enhanced_data = {
            "file_path": file_path,
            "position": {
                "row": position["row"],
                "column": position["column"]
            }
        }
        await self.enhanced_session.handle_cursor_update(client_id, enhanced_data)
        
        # Enhanced session already broadcasts to other clients
        # No need to broadcast again
    
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
        
        # Handle with enhanced session
        enhanced_data = {
            "message": message
        }
        await self.enhanced_session.handle_chat_message(client_id, enhanced_data)
        
        # Enhanced session already broadcasts to other clients
        # No need to broadcast again
