# Collaboration Module for Terminator IDE

This module provides real-time collaboration features for the Terminator IDE, allowing multiple users to edit files together with conflict-free editing and high-performance synchronization.

## Features

### Core Features

- **Operational Transform (OT)**: Provides conflict-free real-time editing
- **Cursor Preservation**: Maintains cursor position during document transformations
- **Reliable Message Delivery**: Uses acknowledgment system for reliable delivery
- **Reconnection Logic**: Automatic reconnection with exponential backoff
- **Heartbeat Mechanism**: Detects disconnections and inactive users
- **Session Recovery**: Recovers state after disconnection
- **Multiple Sessions**: Support for multiple simultaneous collaboration sessions

### Performance Optimizations

- **Document Chunking**: Efficiently handle large files (>1MB) through incremental chunking
- **Connection Pooling**: Optimize WebSocket communication for multiple users
- **Incremental Updates**: Send only changed document chunks to clients
- **Performance Monitoring**: Built-in profiling and statistics gathering
- **Caching**: Intelligent caching to reduce redundant operations
- **Parallel Processing**: Asynchronous processing of operations

### Operational Transform

The OT algorithm allows multiple users to edit the same document simultaneously without conflicts. It works by transforming operations against each other to ensure that the document remains consistent across all clients.

Key components:
- `InsertOperation`: Insert text at a specific position
- `DeleteOperation`: Delete text at a specific position
- `transform()`: Transform two operations against each other
- `apply_operation()`: Apply an operation to a document

### Document Chunking

For large files, the module automatically splits documents into manageable chunks:

Key components:
- `DocumentChunk`: Represents a chunk of a large document
- `ChunkedDocument`: Manages a document split into chunks
- `DocumentChunkManager`: Manages multiple chunked documents
- Automatic conversion when files exceed size threshold
- Intelligent rebalancing of chunks when needed

### Connection Pooling

Efficiently manages WebSocket connections for high-load scenarios:

Key components:
- `ConnectionPool`: Manages a pool of WebSocket connections
- `ConnectionPoolManager`: Manages multiple connection pools
- Topic-based publishing/subscribing to optimize message delivery
- Automatic cleanup of idle pools and connections

### Session Management

The collaboration system uses a session-based approach, where each session represents a collaborative editing session with multiple users.

Key components:
- `CollaborationSession`: Manages a real-time collaboration session
- `SessionManager`: Manages multiple sessions
- `User`: Represents a user in a session

## Usage Example

```python
import uuid
import json
import asyncio
import websockets

from terminator.collaboration import (
    SessionManager, 
    CollaborationSession,
    DocumentChunkManager
)
from terminator.utils.performance import TimingProfiler

# Create a session manager with connection pooling enabled
session_manager = SessionManager(use_connection_pooling=True)
await session_manager.start()

# Create a new session
session = session_manager.create_session("Project Collaboration")

# Handle WebSocket connections
async def handle_websocket(websocket, path):
    client_id = str(uuid.uuid4())
    username = "User" + client_id[:6]
    
    # Register with connection pool for efficient message delivery
    session_manager.register_client_with_connection_pool(
        client_id=client_id,
        session_id=session.session_id,
        websocket=websocket
    )
    
    # Add user to session
    await session.add_user(client_id, username, websocket)
    
    try:
        async for message in websocket:
            data = json.loads(message)
            
            # Profile the message handling for performance monitoring
            with TimingProfiler.async_profile(f"handle_message_{data['type']}"):
                # Handle different message types
                if data["type"] == "edit":
                    await session.handle_edit(client_id, data)
                elif data["type"] == "cursor":
                    await session.handle_cursor_update(client_id, data)
                elif data["type"] == "chat":
                    await session.handle_chat_message(client_id, data)
                elif data["type"] == "heartbeat":
                    await session.handle_heartbeat(client_id)
                elif data["type"] == "ack":
                    await session.handle_message_ack(client_id, data["message_id"])
                elif data["type"] == "get_chunk":
                    # Handle request for specific document chunk (for large files)
                    file_path = data["file_path"]
                    chunk_id = data["chunk_id"]
                    
                    if file_path in session.chunked_files:
                        chunked_doc = session.chunk_manager.get_document(file_path)
                        for chunk in chunked_doc.chunks:
                            if chunk.chunk_id == chunk_id:
                                await websocket.send(json.dumps({
                                    "type": "chunk_data",
                                    "file_path": file_path,
                                    "chunk_id": chunk_id,
                                    "content": chunk.content,
                                    "start_offset": chunk.start_offset,
                                    "length": chunk.length
                                }))
                                break
    finally:
        await session.remove_user(client_id)

# Start WebSocket server
async def main():
    async with websockets.serve(handle_websocket, "localhost", 8765):
        # Log performance stats periodically
        while True:
            await asyncio.sleep(600)  # Every 10 minutes
            stats = session_manager.get_performance_stats()
            print(f"Performance statistics: {stats}")
            
asyncio.run(main())
```

### Client-Side Implementation Example

```javascript
// Client-side JavaScript example for handling chunked documents
class CollaborationClient {
    constructor(serverUrl) {
        this.serverUrl = serverUrl;
        this.socket = null;
        this.documentChunks = {};  // file_path -> {chunk_id -> chunk_data}
        this.connect();
    }
    
    connect() {
        this.socket = new WebSocket(this.serverUrl);
        
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === "edit") {
                this.handleEdit(data);
            } else if (data.type === "ack" && data.chunks) {
                this.handleChunkedUpdates(data);
            } else if (data.type === "chunk_data") {
                this.handleChunkData(data);
            }
            // Handle other message types...
        };
    }
    
    handleChunkedUpdates(data) {
        const filePath = data.file_path;
        const updates = data.chunks;
        
        // Initialize document chunks if needed
        if (!this.documentChunks[filePath]) {
            this.documentChunks[filePath] = {};
        }
        
        // Apply chunk updates
        for (const [chunkId, chunkData] of Object.entries(updates.changed_chunks || {})) {
            this.documentChunks[filePath][chunkId] = chunkData;
            
            // If content is missing, request it
            if (!chunkData.content) {
                this.requestChunk(filePath, chunkId);
            }
        }
        
        // Remove deleted chunks
        for (const chunkId of updates.deleted_chunks || []) {
            delete this.documentChunks[filePath][chunkId];
        }
        
        // Rebuild document if needed
        if (this.isActiveDocument(filePath)) {
            this.rebuildDocument(filePath);
        }
    }
    
    requestChunk(filePath, chunkId) {
        this.socket.send(JSON.stringify({
            type: "get_chunk",
            file_path: filePath,
            chunk_id: chunkId
        }));
    }
    
    handleChunkData(data) {
        const filePath = data.file_path;
        const chunkId = data.chunk_id;
        
        // Store chunk data
        if (!this.documentChunks[filePath]) {
            this.documentChunks[filePath] = {};
        }
        
        this.documentChunks[filePath][chunkId] = {
            content: data.content,
            start_offset: data.start_offset,
            length: data.length
        };
        
        // Rebuild document if it's active
        if (this.isActiveDocument(filePath)) {
            this.rebuildDocument(filePath);
        }
    }
    
    rebuildDocument(filePath) {
        // Get all chunks for this file
        const chunks = Object.values(this.documentChunks[filePath] || {});
        
        // Sort chunks by start offset
        chunks.sort((a, b) => a.start_offset - b.start_offset);
        
        // Combine chunks into a single document
        let content = chunks.map(chunk => chunk.content).join('');
        
        // Update editor with combined content
        this.updateEditor(filePath, content);
    }
    
    // Other methods...
}
```

## Protocol

### Message Types

- `edit`: Edit operation
- `cursor`: Cursor position update
- `chat`: Chat message
- `heartbeat`: Heartbeat message
- `ack`: Message acknowledgment
- `session_state`: Session state
- `user_joined`: User joined notification
- `user_left`: User left notification
- `user_active`: User became active notification
- `user_inactive`: User became inactive notification
- `error`: Error message

### Client-Server Messages

Client to server:
- Edit operation: `{"type": "edit", "file_path": "...", "operation": {...}, "version": 1}`
- Cursor update: `{"type": "cursor", "file_path": "...", "position": {"row": 0, "column": 0}}`
- Chat message: `{"type": "chat", "message": "..."}`
- Heartbeat: `{"type": "heartbeat"}`
- Acknowledgment: `{"type": "ack", "message_id": "..."}`

Server to client:
- Edit confirmation: `{"type": "ack", "file_path": "...", "client_version": 1, "server_version": 2}`
- Broadcast edit: `{"type": "edit", "file_path": "...", "operation": {...}, "client_id": "...", "server_version": 2}`
- Session state: `{"type": "session_state", "users": {...}, "files": {...}, "cursors": {...}, "chat_history": [...]}`

## Implementation Details

### Conflict Resolution

The module uses the Operational Transform algorithm to resolve conflicts between concurrent edits. When two users edit the same document simultaneously, the algorithm transforms the operations to ensure that they can be applied in any order and still result in the same document state.

### Cursor Preservation

Cursor positions are transformed along with edit operations to ensure that they remain in the correct position after edits by other users are applied.

### Reliability

The system uses a message acknowledgment mechanism to ensure that messages are delivered reliably. If a client doesn't acknowledge a message, the server will resend it when the client reconnects.

### Reconnection

Clients can reconnect to a session after disconnection and receive any updates they missed. The server uses exponential backoff for reconnection attempts to avoid overwhelming the server.

### Performance

The system uses several techniques to optimize performance:

#### Document Chunking
- Large files (>1MB) are automatically split into manageable chunks
- Only modified chunks are transmitted over the network
- Reduces memory usage and improves responsiveness
- Automatic rebalancing ensures optimal chunk sizes

#### Connection Pooling
- WebSocket connections are pooled for efficient communication
- Topic-based message distribution minimizes bandwidth usage
- Connections are automatically cleaned up when idle
- Multiple pools distribute load for high-concurrency scenarios

#### Optimization Techniques
- Incremental updates to minimize data transfer
- Memoization and caching to avoid redundant operations
- Performance profiling and monitoring to identify bottlenecks
- Asynchronous message processing for non-blocking operations
- Thread pool execution for CPU-intensive operations

#### Scaling
- Support for hundreds of simultaneous connections
- Efficient handling of large files (tested up to 100MB)
- Minimal CPU and memory overhead per connection
- Performance metrics collection for monitoring system health