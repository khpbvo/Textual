# Collaboration Module for Terminator IDE
# 
# Provides real-time collaborative editing features with:
# - Conflict-free editing using Operational Transform
# - Document chunking for large files
# - Connection pooling for scalability
# - Performance optimization
# - Shared AI session support

from .operational_transform import (
    Operation, 
    InsertOperation,
    DeleteOperation,
    transform,
    apply_operation,
    OperationQueue
)

from .document_chunker import (
    DocumentChunk,
    ChunkedDocument,
    DocumentChunkManager,
    MAX_UNCHUNKED_SIZE
)

from .connection_pool import (
    ConnectionPool,
    ConnectionPoolManager
)

from .session import (
    CursorPosition,
    User,
    CollaborationSession,
    SessionManager
)

from .shared_ai_session import (
    AIMessage,
    SharedAIContext,
    SharedAIManager,
    SharedAICollaborationIntegration
)

__all__ = [
    # Operational Transform
    'Operation',
    'InsertOperation', 
    'DeleteOperation',
    'transform',
    'apply_operation',
    'OperationQueue',
    
    # Document Chunking
    'DocumentChunk',
    'ChunkedDocument',
    'DocumentChunkManager',
    'MAX_UNCHUNKED_SIZE',
    
    # Connection Pooling
    'ConnectionPool',
    'ConnectionPoolManager',
    
    # Session Management
    'CursorPosition',
    'User',
    'CollaborationSession',
    'SessionManager',
    
    # Shared AI Session
    'AIMessage',
    'SharedAIContext',
    'SharedAIManager',
    'SharedAICollaborationIntegration'
]