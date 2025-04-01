"""
Collaboration Session Module - Provides session management for real-time collaboration
"""

import time
import json
import asyncio
import logging
import uuid
from typing import Dict, List, Any, Optional, Set, Tuple, Union

from .operational_transform import (
    Operation, 
    InsertOperation, 
    DeleteOperation, 
    transform, 
    apply_operation,
    OperationQueue
)
from .document_chunker import (
    DocumentChunkManager,
    ChunkedDocument,
    MAX_UNCHUNKED_SIZE
)
from .connection_pool import (
    ConnectionPoolManager,
    ConnectionPool
)
from ..utils.performance import (
    PerformanceOptimizer,
    DebounceThrottle,
    TimingProfiler
)

logger = logging.getLogger(__name__)

class CursorPosition:
    """Represents a cursor position in a document"""
    
    def __init__(self, row: int, column: int):
        """
        Initialize a cursor position
        
        Args:
            row: Row (line) number (0-based)
            column: Column number (0-based)
        """
        self.row = row
        self.column = column
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary representation"""
        return {
            "row": self.row,
            "column": self.column
        }
    
    @staticmethod
    def from_dict(data: Dict[str, int]) -> 'CursorPosition':
        """Create from dictionary representation"""
        return CursorPosition(data["row"], data["column"])
    
    def transform(self, operation: Operation, text: str) -> 'CursorPosition':
        """
        Transform this cursor position against an operation
        
        Args:
            operation: Operation to transform against
            text: Current text content
            
        Returns:
            Transformed cursor position
        """
        # Calculate absolute position in the document
        lines = text.split('\n')
        absolute_pos = sum(len(line) + 1 for line in lines[:self.row]) + self.column
        
        # Transform the absolute position
        if isinstance(operation, InsertOperation):
            if operation.position < absolute_pos:
                absolute_pos += len(operation.text)
        elif isinstance(operation, DeleteOperation):
            if operation.position < absolute_pos:
                delete_end = operation.position + operation.length
                if delete_end <= absolute_pos:
                    # Delete ends before the cursor
                    absolute_pos -= operation.length
                else:
                    # Delete contains the cursor
                    absolute_pos = operation.position
        
        # Convert back to row/column
        new_text = apply_operation(text, operation)
        new_lines = new_text.split('\n')
        
        row = 0
        pos = 0
        while row < len(new_lines) and pos + len(new_lines[row]) + 1 <= absolute_pos:
            pos += len(new_lines[row]) + 1
            row += 1
        
        column = absolute_pos - pos if row < len(new_lines) else 0
        
        return CursorPosition(row, column)


class User:
    """Represents a user in a collaboration session"""
    
    def __init__(self, client_id: str, username: str, websocket):
        """
        Initialize a user
        
        Args:
            client_id: Client ID
            username: Username
            websocket: WebSocket connection
        """
        self.client_id = client_id
        self.username = username
        self.websocket = websocket
        self.joined_at = time.time()
        self.active = True
        self.cursors: Dict[str, CursorPosition] = {}  # file_path -> cursor
        self.version = 0  # Client's current operation version
        self.last_heartbeat = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "client_id": self.client_id,
            "username": self.username,
            "active": self.active,
            "joined_at": self.joined_at
        }
    
    async def send(self, message: Dict[str, Any]) -> None:
        """
        Send a message to this user
        
        Args:
            message: Message to send
        """
        if self.active and self.websocket:
            try:
                await self.websocket.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {self.username}: {str(e)}")
                self.active = False
    
    def update_cursor(self, file_path: str, position: CursorPosition) -> None:
        """
        Update cursor position for a file
        
        Args:
            file_path: File path
            position: Cursor position
        """
        self.cursors[file_path] = position
        self.last_heartbeat = time.time()
    
    def is_likely_disconnected(self, timeout: int = 30) -> bool:
        """
        Check if the user is likely disconnected based on heartbeat
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            True if the user is likely disconnected
        """
        return time.time() - self.last_heartbeat > timeout


class CollaborationSession:
    """
    Represents a real-time collaboration session with OT support
    
    This class manages a collaboration session with multiple users,
    handling operations with conflict resolution using Operational Transform.
    Supports large file handling through document chunking.
    """
    
    def __init__(self, 
                 session_id: str, 
                 name: str = "Unnamed Session",
                 connection_pool: Optional[ConnectionPool] = None):
        """
        Initialize a collaboration session
        
        Args:
            session_id: Session ID
            name: Session name
            connection_pool: Optional connection pool for this session
        """
        self.session_id = session_id
        self.name = name
        self.created_at = time.time()
        self.users: Dict[str, User] = {}
        self.file_content: Dict[str, str] = {}
        self.file_history: Dict[str, List[Dict[str, Any]]] = {}
        self.chat_history: List[Dict[str, Any]] = []
        self.operation_queues: Dict[str, OperationQueue] = {}  # file_path -> queue
        self.message_acks: Dict[str, Set[str]] = {}  # message_id -> set of client_ids
        self.heartbeat_task = None
        self.reconnection_intervals: Dict[str, float] = {}  # client_id -> interval
        
        # Performance optimization for large files
        self.chunk_manager = DocumentChunkManager()
        self.chunked_files: Set[str] = set()  # Set of files being handled in chunks
        self.client_known_chunks: Dict[str, Dict[str, Dict[str, Any]]] = {}  # client_id -> file_path -> chunks
        
        # Connection pool for efficient WebSocket communication
        self.connection_pool = connection_pool
        self.is_large_session = False  # Tracks if this is a large session (many users)
    
    async def start(self) -> None:
        """Start the session and background tasks"""
        # Start heartbeat task
        self.heartbeat_task = asyncio.create_task(self._heartbeat_checker())
    
    async def stop(self) -> None:
        """Stop the session and background tasks"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
    
    async def _heartbeat_checker(self) -> None:
        """Check for disconnected users periodically"""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                disconnected = []
                for client_id, user in self.users.items():
                    if user.active and user.is_likely_disconnected():
                        logger.info(f"User {user.username} appears to be disconnected")
                        user.active = False
                        disconnected.append(client_id)
                
                # Notify other users about disconnections
                if disconnected:
                    for client_id in disconnected:
                        await self.broadcast({
                            "type": "user_inactive",
                            "client_id": client_id,
                            "username": self.users[client_id].username
                        })
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat checker: {str(e)}")
    
    async def add_user(self, client_id: str, username: str, websocket) -> None:
        """
        Add a user to the session
        
        Args:
            client_id: Client ID
            username: Username
            websocket: WebSocket connection
        """
        user = User(client_id, username, websocket)
        self.users[client_id] = user
        
        # Initialize reconnection interval
        self.reconnection_intervals[client_id] = 1.0  # Initial backoff: 1 second
        
        # Send current state to new user
        await user.send({
            "type": "session_state",
            "session_id": self.session_id,
            "session_name": self.name,
            "users": {cid: u.to_dict() for cid, u in self.users.items()},
            "files": self.file_content,
            "cursors": {cid: {path: pos.to_dict() for path, pos in u.cursors.items()} 
                        for cid, u in self.users.items()},
            "chat_history": self.chat_history
        })
        
        # Notify other users
        await self.broadcast({
            "type": "user_joined",
            "client_id": client_id,
            "username": username
        }, exclude=user.websocket)
        
        logger.info(f"User {username} joined session {self.session_id}")
    
    async def handle_reconnection(self, client_id: str, websocket) -> None:
        """
        Handle user reconnection
        
        Args:
            client_id: Client ID
            websocket: New WebSocket connection
        """
        if client_id in self.users:
            user = self.users[client_id]
            old_websocket = user.websocket
            
            # Update user state
            user.websocket = websocket
            user.active = True
            user.last_heartbeat = time.time()
            
            # Reset reconnection interval
            self.reconnection_intervals[client_id] = 1.0
            
            # Send current state
            await user.send({
                "type": "session_state",
                "session_id": self.session_id,
                "session_name": self.name,
                "users": {cid: u.to_dict() for cid, u in self.users.items()},
                "files": self.file_content,
                "cursors": {cid: {path: pos.to_dict() for path, pos in u.cursors.items()} 
                            for cid, u in self.users.items()},
                "chat_history": self.chat_history,
                "reconnected": True
            })
            
            # Notify other users
            await self.broadcast({
                "type": "user_active",
                "client_id": client_id,
                "username": user.username
            }, exclude=user.websocket)
            
            logger.info(f"User {user.username} reconnected to session {self.session_id}")
            return True
        else:
            return False
    
    async def remove_user(self, client_id: str) -> None:
        """
        Remove a user from the session
        
        Args:
            client_id: Client ID
        """
        if client_id in self.users:
            username = self.users[client_id].username
            del self.users[client_id]
            
            # Clean up reconnection data
            if client_id in self.reconnection_intervals:
                del self.reconnection_intervals[client_id]
            
            # Notify other users
            await self.broadcast({
                "type": "user_left",
                "client_id": client_id,
                "username": username
            })
            
            logger.info(f"User {username} left session {self.session_id}")
    
    async def broadcast(self, message: Dict[str, Any], exclude=None) -> None:
        """
        Broadcast a message to all active users
        
        Args:
            message: Message to broadcast
            exclude: Optional WebSocket connection to exclude
        """
        # Add message ID for acknowledgment tracking if not present
        if "message_id" not in message:
            message["message_id"] = str(uuid.uuid4())
        
        # Initialize acknowledgment tracking
        message_id = message["message_id"]
        self.message_acks[message_id] = set()
        
        # Send to all active users
        coros = []
        for user in self.users.values():
            if user.active and user.websocket != exclude:
                coros.append(user.send(message))
                
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)
    
    async def handle_message_ack(self, client_id: str, message_id: str) -> None:
        """
        Handle message acknowledgment
        
        Args:
            client_id: Client ID
            message_id: Message ID
        """
        if message_id in self.message_acks:
            self.message_acks[message_id].add(client_id)
            
            # Clean up when all active users have acknowledged
            active_users = {uid for uid, user in self.users.items() if user.active}
            if active_users.issubset(self.message_acks[message_id]):
                del self.message_acks[message_id]
    
    @TimingProfiler.profile
    def _ensure_operation_queue(self, file_path: str) -> None:
        """
        Ensure an operation queue exists for a file
        
        Args:
            file_path: File path
        """
        if file_path not in self.operation_queues:
            self.operation_queues[file_path] = OperationQueue()
            
        if file_path not in self.file_content:
            self.file_content[file_path] = ""
            
        if file_path not in self.file_history:
            self.file_history[file_path] = []
            
        # Check if we need to use chunking for this file
        if file_path not in self.chunked_files and file_path in self.file_content:
            content = self.file_content[file_path]
            if len(content) > MAX_UNCHUNKED_SIZE:
                self._convert_to_chunked(file_path, content)
                
    def _convert_to_chunked(self, file_path: str, content: str) -> None:
        """
        Convert a file to use chunking
        
        Args:
            file_path: File path
            content: File content
        """
        logger.info(f"Converting file to chunked format: {file_path}")
        chunked_doc = self.chunk_manager.get_document(file_path)
        chunked_doc.set_content(content)
        self.chunked_files.add(file_path)
        
        # Reset client chunk knowledge
        for client_id in self.users.keys():
            if client_id not in self.client_known_chunks:
                self.client_known_chunks[client_id] = {}
            self.client_known_chunks[client_id][file_path] = {}
    
    @TimingProfiler.async_profile
    async def handle_edit(self, client_id: str, data: Dict[str, Any]) -> None:
        """
        Handle an edit operation with conflict resolution
        
        Args:
            client_id: Client ID
            data: Edit operation data
        """
        try:
            file_path = data["file_path"]
            operation_data = data["operation"]
            client_version = data.get("version", 0)
            
            # Ensure file exists in our tracking
            self._ensure_operation_queue(file_path)
            
            # Get the user
            if client_id not in self.users:
                logger.error(f"Unknown client ID: {client_id}")
                return
                
            user = self.users[client_id]
            queue = self.operation_queues[file_path]
            
            # Convert operation data to Operation object
            operation = Operation.from_dict(operation_data)
            
            # Transform operation against all concurrent operations
            transformed_op = queue.transform_operation(client_id, operation, client_version)
            
            # Check if we need to handle as chunked document
            if file_path in self.chunked_files:
                # Handle chunked document edit
                chunked_doc = self.chunk_manager.get_document(file_path)
                
                # Apply the transformed operation to the chunked document
                chunked_doc.apply_operation(transformed_op)
                
                # Update in-memory content (for consistency)
                self.file_content[file_path] = chunked_doc.get_content()
            else:
                # Regular document editing
                # Apply the transformed operation to the document
                self.file_content[file_path] = apply_operation(self.file_content[file_path], transformed_op)
                
                # Check if the file has grown large enough to need chunking
                if len(self.file_content[file_path]) > MAX_UNCHUNKED_SIZE:
                    self._convert_to_chunked(file_path, self.file_content[file_path])
            
            # Record the operation in history
            self.file_history[file_path].append({
                "timestamp": time.time(),
                "client_id": client_id,
                "username": user.username,
                "operation": transformed_op.to_dict(),
                "original_operation": operation_data
            })
            
            # Add to operation queue
            server_version = len(queue.operations)
            queue.add_operation(client_id, transformed_op, server_version)
            
            # Update user's version
            user.version = server_version + 1
            
            # Update all cursors
            for u in self.users.values():
                if file_path in u.cursors:
                    u.cursors[file_path] = u.cursors[file_path].transform(
                        transformed_op, self.file_content[file_path]
                    )
            
            # Use connection pool if available for efficient broadcasting
            if self.connection_pool:
                # Format the message once
                message = json.dumps({
                    "type": "edit",
                    "file_path": file_path,
                    "operation": transformed_op.to_dict(),
                    "client_id": client_id,
                    "username": user.username,
                    "server_version": server_version
                })
                
                # Broadcast through connection pool
                await self.connection_pool.broadcast(
                    message=message,
                    topic=f"session:{self.session_id}:edits",
                    exclude=client_id
                )
            else:
                # Fall back to direct broadcasting
                await self.broadcast({
                    "type": "edit",
                    "file_path": file_path,
                    "operation": transformed_op.to_dict(),
                    "client_id": client_id,
                    "username": user.username,
                    "server_version": server_version
                }, exclude=user.websocket)
            
            # Send acknowledgment to the originating client
            ack_message = {
                "type": "ack",
                "file_path": file_path,
                "client_version": client_version,
                "server_version": server_version
            }
            
            # If chunked file, include incremental chunk updates
            if file_path in self.chunked_files:
                # Get client's known chunks state
                if client_id not in self.client_known_chunks:
                    self.client_known_chunks[client_id] = {}
                if file_path not in self.client_known_chunks[client_id]:
                    self.client_known_chunks[client_id][file_path] = {}
                    
                # Get incremental updates
                chunked_doc = self.chunk_manager.get_document(file_path)
                updates = chunked_doc.get_incremental_update(
                    self.client_known_chunks[client_id].get(file_path, {})
                )
                
                # Add updates to ack
                ack_message["chunks"] = updates
                
                # Update client's known chunks
                for chunk_id, chunk_data in updates.get("changed_chunks", {}).items():
                    self.client_known_chunks[client_id][file_path][chunk_id] = {
                        "last_modified": chunk_data["last_modified"]
                    }
                
                # Remove deleted chunks
                for chunk_id in updates.get("deleted_chunks", []):
                    if chunk_id in self.client_known_chunks[client_id][file_path]:
                        del self.client_known_chunks[client_id][file_path][chunk_id]
            
            # Use connection pool if available
            if self.connection_pool:
                await self.connection_pool.send_to_client(
                    client_id=client_id,
                    message=json.dumps(ack_message)
                )
            else:
                await user.send(ack_message)
            
        except Exception as e:
            logger.error(f"Error handling edit: {str(e)}", exc_info=True)
            # Send error to client
            error_message = {
                "type": "error",
                "error": str(e)
            }
            
            if client_id in self.users:
                if self.connection_pool:
                    await self.connection_pool.send_to_client(
                        client_id=client_id,
                        message=json.dumps(error_message)
                    )
                else:
                    await self.users[client_id].send(error_message)
    
    async def handle_cursor_update(self, client_id: str, data: Dict[str, Any]) -> None:
        """
        Handle cursor position update
        
        Args:
            client_id: Client ID
            data: Cursor position data
        """
        try:
            file_path = data["file_path"]
            position_data = data["position"]
            
            # Get the user
            if client_id not in self.users:
                logger.error(f"Unknown client ID: {client_id}")
                return
                
            user = self.users[client_id]
            
            # Update cursor position
            position = CursorPosition.from_dict(position_data)
            user.update_cursor(file_path, position)
            
            # Broadcast to other users
            await self.broadcast({
                "type": "cursor",
                "file_path": file_path,
                "position": position_data,
                "client_id": client_id,
                "username": user.username
            }, exclude=user.websocket)
            
        except Exception as e:
            logger.error(f"Error handling cursor update: {str(e)}")
    
    async def handle_chat_message(self, client_id: str, data: Dict[str, Any]) -> None:
        """
        Handle chat message
        
        Args:
            client_id: Client ID
            data: Chat message data
        """
        try:
            message_text = data["message"]
            
            # Get the user
            if client_id not in self.users:
                logger.error(f"Unknown client ID: {client_id}")
                return
                
            user = self.users[client_id]
            
            # Create message object
            message = {
                "timestamp": time.time(),
                "client_id": client_id,
                "username": user.username,
                "message": message_text
            }
            
            # Add to chat history
            self.chat_history.append(message)
            
            # Broadcast to all users
            await self.broadcast({
                "type": "chat",
                "message": message
            })
            
        except Exception as e:
            logger.error(f"Error handling chat message: {str(e)}")
    
    async def handle_heartbeat(self, client_id: str) -> None:
        """
        Handle heartbeat from client
        
        Args:
            client_id: Client ID
        """
        if client_id in self.users:
            user = self.users[client_id]
            user.last_heartbeat = time.time()
            
            # If user was inactive, mark as active again
            if not user.active:
                user.active = True
                await self.broadcast({
                    "type": "user_active",
                    "client_id": client_id,
                    "username": user.username
                }, exclude=user.websocket)
    
    def get_reconnection_interval(self, client_id: str) -> float:
        """
        Get reconnection interval with exponential backoff
        
        Args:
            client_id: Client ID
            
        Returns:
            Reconnection interval in seconds
        """
        if client_id not in self.reconnection_intervals:
            return 1.0
            
        interval = self.reconnection_intervals[client_id]
        
        # Update for next time (exponential backoff, max 60 seconds)
        self.reconnection_intervals[client_id] = min(interval * 2, 60.0)
        
        return interval
    
    def is_empty(self) -> bool:
        """
        Check if the session is empty
        
        Returns:
            True if no active users
        """
        return not any(user.active for user in self.users.values())


class SessionManager:
    """Manages multiple collaboration sessions with support for connection pooling"""
    
    def __init__(self, use_connection_pooling: bool = True):
        """
        Initialize an empty session manager
        
        Args:
            use_connection_pooling: Whether to use connection pooling for WebSocket communication
        """
        self.sessions: Dict[str, CollaborationSession] = {}
        self.cleanup_task = None
        self.perf_monitoring_task = None
        
        # Initialize connection pool manager if enabled
        self.use_connection_pooling = use_connection_pooling
        self.connection_pool_manager = ConnectionPoolManager() if use_connection_pooling else None
    
    async def start(self) -> None:
        """Start the session manager and background tasks"""
        self.cleanup_task = asyncio.create_task(self._cleanup_empty_sessions())
        self.perf_monitoring_task = asyncio.create_task(self._monitor_performance())
        
        # Start connection pool manager if enabled
        if self.connection_pool_manager:
            await self.connection_pool_manager.start()
    
    async def stop(self) -> None:
        """Stop the session manager and background tasks"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
                
        if self.perf_monitoring_task:
            self.perf_monitoring_task.cancel()
            try:
                await self.perf_monitoring_task
            except asyncio.CancelledError:
                pass
                
        # Stop connection pool manager if enabled
        if self.connection_pool_manager:
            await self.connection_pool_manager.stop()
                
        # Stop all sessions
        for session in self.sessions.values():
            await session.stop()
    
    async def _cleanup_empty_sessions(self) -> None:
        """Periodically clean up empty sessions"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                to_remove = []
                for session_id, session in self.sessions.items():
                    if session.is_empty():
                        # Session has no active users
                        to_remove.append(session_id)
                        await session.stop()
                
                for session_id in to_remove:
                    del self.sessions[session_id]
                    logger.info(f"Removed empty session: {session_id}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup: {str(e)}")
                
    async def _monitor_performance(self) -> None:
        """Periodically monitor and log performance statistics"""
        while True:
            try:
                await asyncio.sleep(600)  # Check every 10 minutes
                
                # Get timing stats from profiler
                timing_stats = TimingProfiler.get_stats()
                
                # Log performance statistics
                if timing_stats:
                    logger.info("Performance statistics:")
                    for func_name, stats in timing_stats.items():
                        logger.info(f"  {func_name}: avg={stats['avg']:.4f}s, calls={stats['count']}, "
                                   f"min={stats['min']:.4f}s, max={stats['max']:.4f}s")
                
                # Log connection pool stats if enabled
                if self.connection_pool_manager:
                    pool_stats = self.connection_pool_manager.get_stats()
                    logger.info(f"Connection pool statistics: {pool_stats}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance monitoring: {str(e)}")
    
    @PerformanceOptimizer.memoize(ttl=5)  # Cache for 5 seconds to reduce load
    def get_active_session_count(self) -> int:
        """
        Get the count of active sessions
        
        Returns:
            Number of active sessions
        """
        return len(self.sessions)
    
    def create_session(self, name: str = "Unnamed Session") -> CollaborationSession:
        """
        Create a new session
        
        Args:
            name: Session name
            
        Returns:
            New session
        """
        session_id = str(uuid.uuid4())
        
        # Get or create a connection pool for this session if enabled
        connection_pool = None
        if self.connection_pool_manager:
            connection_pool = self.connection_pool_manager.get_or_create_pool_for_session(session_id)
        
        # Create the session with the connection pool
        session = CollaborationSession(
            session_id=session_id, 
            name=name,
            connection_pool=connection_pool
        )
        self.sessions[session_id] = session
        
        # Start the session
        asyncio.create_task(session.start())
        
        logger.info(f"Created new session: {session_id} - {name}")
        return session
    
    def get_session(self, session_id: str) -> Optional[CollaborationSession]:
        """
        Get a session by ID
        
        Args:
            session_id: Session ID
            
        Returns:
            Session or None if not found
        """
        return self.sessions.get(session_id)
    
    def register_client_with_connection_pool(self, client_id: str, session_id: str, websocket: Any) -> None:
        """
        Register a client with the appropriate connection pool
        
        Args:
            client_id: Client ID
            session_id: Session ID
            websocket: WebSocket connection
        """
        if not self.connection_pool_manager:
            return
            
        # Register client to session's pool
        self.connection_pool_manager.register_client(client_id, session_id)
        
        # Get the pool for this client
        pool = self.connection_pool_manager.get_pool_for_client(client_id)
        if pool:
            # Add the connection to the pool
            pool.add_connection(client_id, websocket)
            
            # Subscribe to session topics
            pool.subscribe(client_id, f"session:{session_id}:edits")
            pool.subscribe(client_id, f"session:{session_id}:cursors")
            pool.subscribe(client_id, f"session:{session_id}:chat")
    
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """
        Get information about all sessions
        
        Returns:
            List of session info dictionaries
        """
        return [
            {
                "session_id": session.session_id,
                "name": session.name,
                "created_at": session.created_at,
                "user_count": sum(1 for user in session.users.values() if user.active),
                "is_large_session": session.is_large_session,
                "file_count": len(session.file_content),
                "chunked_files": len(session.chunked_files)
            }
            for session in self.sessions.values()
        ]
        
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive performance statistics
        
        Returns:
            Dictionary of performance statistics
        """
        stats = {
            "timing": TimingProfiler.get_stats(),
            "sessions": {
                "total": len(self.sessions),
                "active_users": sum(
                    sum(1 for user in session.users.values() if user.active)
                    for session in self.sessions.values()
                ),
                "total_files": sum(len(session.file_content) for session in self.sessions.values()),
                "chunked_files": sum(len(session.chunked_files) for session in self.sessions.values())
            }
        }
        
        # Add connection pool stats if enabled
        if self.connection_pool_manager:
            stats["connection_pools"] = self.connection_pool_manager.get_stats()
            
        return stats