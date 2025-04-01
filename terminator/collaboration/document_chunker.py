"""
Document Chunker Module - Provides chunking for large documents in collaborative editing
"""

import hashlib
import time
import logging
from typing import Dict, List, Set, Tuple, Optional, Any, Union

from .operational_transform import Operation, InsertOperation, DeleteOperation, apply_operation

logger = logging.getLogger(__name__)

# 1MB default chunk size (in characters)
DEFAULT_CHUNK_SIZE = 1024 * 1024
# Maximum content size before chunking (1MB)
MAX_UNCHUNKED_SIZE = 1024 * 1024

class DocumentChunk:
    """Represents a chunk of a large document"""
    
    def __init__(self, chunk_id: str, content: str, start_offset: int):
        """
        Initialize a document chunk
        
        Args:
            chunk_id: Unique identifier for this chunk
            content: Content of this chunk
            start_offset: Offset of this chunk in the full document
        """
        self.chunk_id = chunk_id
        self.content = content
        self.start_offset = start_offset
        self.length = len(content)
        self.end_offset = start_offset + self.length
        self.last_modified = time.time()
        
    def apply_operation(self, operation: Operation) -> Optional[Tuple[Operation, Operation]]:
        """
        Apply an operation to this chunk
        
        Args:
            operation: Operation to apply
            
        Returns:
            Optional tuple of (overflow_before, overflow_after) operations if the operation
            affects content outside this chunk boundaries
        """
        # Check if operation is completely outside this chunk
        if isinstance(operation, InsertOperation):
            if operation.position < self.start_offset or operation.position > self.end_offset:
                return None
                
            # Apply operation with adjusted position
            local_position = operation.position - self.start_offset
            self.content = apply_operation(self.content, 
                InsertOperation(local_position, operation.text))
            self.length = len(self.content)
            self.end_offset = self.start_offset + self.length
            self.last_modified = time.time()
            return None
            
        elif isinstance(operation, DeleteOperation):
            delete_end = operation.position + operation.length
            
            # Operation completely outside this chunk
            if delete_end <= self.start_offset or operation.position >= self.end_offset:
                return None
                
            # Operation overlaps this chunk boundary
            if operation.position < self.start_offset or delete_end > self.end_offset:
                # Calculate overlap with this chunk
                overlap_start = max(operation.position, self.start_offset)
                overlap_end = min(delete_end, self.end_offset)
                overlap_length = overlap_end - overlap_start
                
                # Create operations for the part inside this chunk
                local_position = overlap_start - self.start_offset
                local_op = DeleteOperation(local_position, overlap_length)
                
                # Apply the local operation
                self.content = apply_operation(self.content, local_op)
                self.length = len(self.content)
                self.end_offset = self.start_offset + self.length
                self.last_modified = time.time()
                
                # Create overflow operations
                overflow_before = None
                overflow_after = None
                
                if operation.position < self.start_offset:
                    before_length = self.start_offset - operation.position
                    overflow_before = DeleteOperation(operation.position, before_length)
                    
                if delete_end > self.end_offset:
                    after_length = delete_end - self.end_offset
                    overflow_after = DeleteOperation(self.end_offset, after_length)
                
                return (overflow_before, overflow_after)
            
            # Operation completely inside this chunk
            local_position = operation.position - self.start_offset
            self.content = apply_operation(self.content, 
                DeleteOperation(local_position, operation.length))
            self.length = len(self.content)
            self.end_offset = self.start_offset + self.length
            self.last_modified = time.time()
            return None
            
        return None


class ChunkedDocument:
    """Manages a large document split into chunks for efficient collaboration"""
    
    def __init__(self, file_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE):
        """
        Initialize a chunked document
        
        Args:
            file_path: Path to the document
            chunk_size: Size of each chunk in characters
        """
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.chunks: List[DocumentChunk] = []
        self.total_length = 0
        self.is_chunked = False
        self.content_cache: Optional[str] = None
        self.cache_timestamp = 0
        self.cache_valid = False
        
    def set_content(self, content: str) -> None:
        """
        Set the document content, chunking if necessary
        
        Args:
            content: Document content
        """
        content_len = len(content)
        self.total_length = content_len
        
        # If content is small enough, don't chunk
        if content_len <= MAX_UNCHUNKED_SIZE:
            self.is_chunked = False
            self.chunks = [DocumentChunk("single", content, 0)]
            self.content_cache = content
            self.cache_timestamp = time.time()
            self.cache_valid = True
            return
            
        # Content needs chunking
        self.is_chunked = True
        self.chunks = []
        
        # Split content into chunks
        for i in range(0, content_len, self.chunk_size):
            chunk_content = content[i:i + self.chunk_size]
            chunk_id = f"chunk_{i}_{hashlib.md5(chunk_content.encode()).hexdigest()[:8]}"
            self.chunks.append(DocumentChunk(chunk_id, chunk_content, i))
            
        # Reset cache
        self.content_cache = None
        self.cache_valid = False
        
    def get_content(self) -> str:
        """
        Get the full document content
        
        Returns:
            Document content
        """
        # Return cached content if valid
        if self.content_cache is not None and self.cache_valid:
            return self.content_cache
            
        # Build content from chunks
        content = ""
        for chunk in self.chunks:
            content += chunk.content
            
        # Cache the result
        self.content_cache = content
        self.cache_timestamp = time.time()
        self.cache_valid = True
        
        return content
        
    def apply_operation(self, operation: Operation) -> None:
        """
        Apply an operation to the document
        
        Args:
            operation: Operation to apply
        """
        # Invalidate cache
        self.cache_valid = False
        
        # Find affected chunks
        affected_chunks = []
        for chunk in self.chunks:
            # For inserts, find the chunk containing the position
            if isinstance(operation, InsertOperation):
                if chunk.start_offset <= operation.position <= chunk.end_offset:
                    affected_chunks.append(chunk)
                    
            # For deletes, find all chunks in the delete range
            elif isinstance(operation, DeleteOperation):
                delete_end = operation.position + operation.length
                if (chunk.start_offset <= operation.position < chunk.end_offset or
                    chunk.start_offset < delete_end <= chunk.end_offset or
                    (operation.position <= chunk.start_offset and 
                     delete_end >= chunk.end_offset)):
                    affected_chunks.append(chunk)
                    
        if not affected_chunks:
            logger.warning(f"No chunks affected by operation: {operation}")
            return
            
        pending_operations = [operation]
        processed_operations = []
        
        # Process all pending operations
        while pending_operations:
            op = pending_operations.pop(0)
            processed_operations.append(op)
            
            # Apply to each affected chunk
            for chunk in affected_chunks:
                result = chunk.apply_operation(op)
                
                # Handle overflow operations
                if result:
                    overflow_before, overflow_after = result
                    if overflow_before and overflow_before not in processed_operations:
                        pending_operations.append(overflow_before)
                    if overflow_after and overflow_after not in processed_operations:
                        pending_operations.append(overflow_after)
                        
        # Update total length
        self.total_length = sum(chunk.length for chunk in self.chunks)
        
        # Check if we need to rebalance chunks
        self._rebalance_chunks_if_needed()
        
    def _rebalance_chunks_if_needed(self) -> None:
        """
        Rebalance chunks if they've become too uneven
        """
        # Skip rebalancing if we only have one chunk
        if len(self.chunks) <= 1:
            return
            
        # Check if any chunk is too large or too small
        needs_rebalance = False
        for chunk in self.chunks:
            if (chunk.length > self.chunk_size * 1.5 or 
                (chunk.length < self.chunk_size * 0.5 and len(self.chunks) > 1)):
                needs_rebalance = True
                break
                
        if not needs_rebalance:
            return
            
        # Rebalance by rebuilding from the full content
        content = self.get_content()
        self.set_content(content)
        
    def get_chunk_containing_position(self, position: int) -> Optional[DocumentChunk]:
        """
        Find the chunk containing a specific position
        
        Args:
            position: Document position
            
        Returns:
            Chunk containing the position or None if not found
        """
        for chunk in self.chunks:
            if chunk.start_offset <= position < chunk.end_offset:
                return chunk
        return None
        
    def get_chunk_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the document chunks
        
        Returns:
            Dictionary of chunk statistics
        """
        return {
            "file_path": self.file_path,
            "is_chunked": self.is_chunked,
            "total_length": self.total_length,
            "chunk_count": len(self.chunks),
            "chunk_size": self.chunk_size,
            "chunks": [
                {
                    "id": chunk.chunk_id,
                    "start": chunk.start_offset,
                    "end": chunk.end_offset,
                    "length": chunk.length,
                    "last_modified": chunk.last_modified
                }
                for chunk in self.chunks
            ]
        }
        
    def get_incremental_update(self, last_known_chunks: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get incremental update for the document
        
        Args:
            last_known_chunks: Last known chunk information from the client
            
        Returns:
            Dictionary with only the chunks that have changed
        """
        # Get current chunk information
        current_chunks = {
            chunk.chunk_id: {
                "content": chunk.content,
                "start_offset": chunk.start_offset,
                "length": chunk.length,
                "last_modified": chunk.last_modified
            }
            for chunk in self.chunks
        }
        
        # Find chunks that have changed
        changed_chunks = {}
        new_chunk_ids = set(current_chunks.keys())
        old_chunk_ids = set(last_known_chunks.keys())
        
        # New and modified chunks
        for chunk_id in new_chunk_ids:
            if (chunk_id not in last_known_chunks or 
                current_chunks[chunk_id]["last_modified"] > 
                last_known_chunks[chunk_id]["last_modified"]):
                changed_chunks[chunk_id] = current_chunks[chunk_id]
                
        # Deleted chunk IDs
        deleted_chunks = old_chunk_ids - new_chunk_ids
        
        return {
            "changed_chunks": changed_chunks,
            "deleted_chunks": list(deleted_chunks),
            "total_length": self.total_length,
            "is_chunked": self.is_chunked
        }


class DocumentChunkManager:
    """Manages chunked documents for the collaboration system"""
    
    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE):
        """
        Initialize a document chunk manager
        
        Args:
            chunk_size: Default chunk size in characters
        """
        self.chunk_size = chunk_size
        self.documents: Dict[str, ChunkedDocument] = {}
        
    def get_document(self, file_path: str) -> ChunkedDocument:
        """
        Get or create a chunked document
        
        Args:
            file_path: Path to the document
            
        Returns:
            ChunkedDocument instance
        """
        if file_path not in self.documents:
            self.documents[file_path] = ChunkedDocument(file_path, self.chunk_size)
            
        return self.documents[file_path]
        
    def remove_document(self, file_path: str) -> None:
        """
        Remove a document from the manager
        
        Args:
            file_path: Path to the document
        """
        if file_path in self.documents:
            del self.documents[file_path]
            
    def get_all_documents(self) -> List[str]:
        """
        Get all managed document paths
        
        Returns:
            List of document paths
        """
        return list(self.documents.keys())