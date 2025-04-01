"""
Operational Transform Module - Provides conflict-free editing for real-time collaboration
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union, Tuple

class Operation(ABC):
    """Base class for all operations in OT system"""
    
    @abstractmethod
    def apply(self, text: str) -> str:
        """Apply this operation to a text string"""
        pass
    
    @abstractmethod
    def transform(self, other: 'Operation') -> Tuple['Operation', 'Operation']:
        """Transform this operation against another concurrent operation"""
        pass
        
    @property
    @abstractmethod
    def position(self) -> int:
        """Get the position of this operation"""
        pass
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert operation to a dictionary representation"""
        pass
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Operation':
        """Create an operation from a dictionary representation"""
        if data["type"] == "insert":
            return InsertOperation(data["position"], data["text"])
        elif data["type"] == "delete":
            return DeleteOperation(data["position"], data["length"])
        else:
            raise ValueError(f"Unknown operation type: {data['type']}")


class InsertOperation(Operation):
    """Insert text at a specific position"""
    
    def __init__(self, position: int, text: str):
        """
        Initialize an insert operation
        
        Args:
            position: Position to insert at
            text: Text to insert
        """
        self._position = position
        self.text = text
        
    def apply(self, text: str) -> str:
        """
        Apply this insert operation to a text string
        
        Args:
            text: Text to apply operation to
            
        Returns:
            Modified text
        """
        return text[:self._position] + self.text + text[self._position:]
    
    def transform(self, other: Operation) -> Tuple[Operation, Operation]:
        """
        Transform this operation against another concurrent operation
        
        Args:
            other: Another operation happening concurrently
            
        Returns:
            Tuple of (this_prime, other_prime) transformed operations
        """
        if isinstance(other, InsertOperation):
            # Case 1: Both operations are inserts
            if other.position <= self._position:
                # Other insert comes before or at the same position
                # Shift this operation's position by the length of other's text
                return (InsertOperation(self._position + len(other.text), self.text), other)
            else:
                # This insert comes before other's position
                # Shift other operation's position by the length of this text
                return (self, InsertOperation(other.position + len(self.text), other.text))
                
        elif isinstance(other, DeleteOperation):
            # Case 2: This is insert, other is delete
            if other.position < self._position:
                # Delete comes before this insert
                if other.position + other.length <= self._position:
                    # Delete entirely before insert position
                    # Shift this operation's position by the delete length
                    return (InsertOperation(self._position - other.length, self.text), other)
                else:
                    # Delete overlaps with insert position
                    # Adjust this insert to be at the delete position
                    return (InsertOperation(other.position, self.text), 
                            DeleteOperation(other.position, other.length - (self._position - other.position)))
            else:
                # Insert comes before or at the same position as delete
                # Shift delete position by the length of the insert
                return (self, DeleteOperation(other.position + len(self.text), other.length))
                
        # Should never reach here if all operation types are handled
        raise NotImplementedError(f"Transform not implemented for {type(other)}")
    
    @property
    def position(self) -> int:
        """Get the position of this operation"""
        return self._position
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "type": "insert",
            "position": self._position,
            "text": self.text
        }


class DeleteOperation(Operation):
    """Delete text in a specific range"""
    
    def __init__(self, position: int, length: int):
        """
        Initialize a delete operation
        
        Args:
            position: Start position to delete from
            length: Length of text to delete
        """
        self._position = position
        self.length = length
        
    def apply(self, text: str) -> str:
        """
        Apply this delete operation to a text string
        
        Args:
            text: Text to apply operation to
            
        Returns:
            Modified text
        """
        return text[:self._position] + text[self._position + self.length:]
    
    def transform(self, other: Operation) -> Tuple[Operation, Operation]:
        """
        Transform this operation against another concurrent operation
        
        Args:
            other: Another operation happening concurrently
            
        Returns:
            Tuple of (this_prime, other_prime) transformed operations
        """
        if isinstance(other, InsertOperation):
            # Case 1: This is delete, other is insert
            if other.position <= self._position:
                # Insert comes before or at delete position
                # Shift delete position by the length of inserted text
                return (DeleteOperation(self._position + len(other.text), self.length), other)
            elif other.position < self._position + self.length:
                # Insert is inside the delete range
                # Split the delete into two parts: before and after the insert
                return (
                    DeleteOperation(self._position, other.position - self._position), 
                    InsertOperation(self._position, other.text)
                )
            else:
                # Insert comes after delete
                return (self, InsertOperation(other.position - self.length, other.text))
                
        elif isinstance(other, DeleteOperation):
            # Case 2: Both operations are deletes
            if other.position + other.length <= self._position:
                # Other delete entirely before this delete
                # Shift this delete position by other delete length
                return (DeleteOperation(self._position - other.length, self.length), other)
            elif self._position + self.length <= other.position:
                # This delete entirely before other delete
                # Shift other delete position by this delete length
                return (self, DeleteOperation(other.position - self.length, other.length))
            elif other.position <= self._position and other.position + other.length >= self._position + self.length:
                # Other delete contains this delete
                # This delete becomes a no-op
                return (DeleteOperation(other.position, 0), 
                        DeleteOperation(other.position, other.length - self.length))
            elif self._position <= other.position and self._position + self.length >= other.position + other.length:
                # This delete contains other delete
                # Other delete becomes a no-op
                return (DeleteOperation(self._position, self.length - other.length), 
                        DeleteOperation(self._position, 0))
            elif other.position < self._position:
                # Other delete overlaps with the beginning of this delete
                overlap = other.position + other.length - self._position
                return (DeleteOperation(other.position, self.length - overlap),
                        DeleteOperation(other.position, other.length - overlap))
            else:  # self._position < other.position
                # This delete overlaps with the beginning of other delete
                overlap = self._position + self.length - other.position
                return (DeleteOperation(self._position, self.length - overlap),
                        DeleteOperation(self._position + self.length - overlap, other.length - overlap))
                
        # Should never reach here if all operation types are handled
        raise NotImplementedError(f"Transform not implemented for {type(other)}")
    
    @property
    def position(self) -> int:
        """Get the position of this operation"""
        return self._position
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "type": "delete",
            "position": self._position,
            "length": self.length
        }


def transform(op1: Operation, op2: Operation) -> Tuple[Operation, Operation]:
    """
    Transform two operations against each other
    
    Args:
        op1: First operation
        op2: Second operation
        
    Returns:
        Tuple of transformed operations (op1_prime, op2_prime)
    """
    return op1.transform(op2)


def apply_operation(text: str, operation: Union[Operation, Dict[str, Any]]) -> str:
    """
    Apply an operation to a text string
    
    Args:
        text: Text to apply operation to
        operation: Operation or operation dictionary
        
    Returns:
        Modified text
    """
    if isinstance(operation, dict):
        operation = Operation.from_dict(operation)
        
    return operation.apply(text)


class OperationQueue:
    """Queue for storing and processing operations"""
    
    def __init__(self):
        """Initialize an empty operation queue"""
        self.operations: List[Tuple[str, Operation]] = []  # List of (client_id, operation) tuples
        self.versions: Dict[str, int] = {}  # Client ID -> version number
    
    def add_operation(self, client_id: str, operation: Operation, version: int) -> None:
        """
        Add an operation to the queue
        
        Args:
            client_id: Client ID
            operation: Operation to add
            version: Client's version number for this operation
        """
        # Update version number
        self.versions[client_id] = version
        
        # Add to operations list
        self.operations.append((client_id, operation))
    
    def get_operations_since(self, version: int) -> List[Tuple[str, Operation]]:
        """
        Get all operations since a specific version
        
        Args:
            version: Version number
            
        Returns:
            List of (client_id, operation) tuples
        """
        return self.operations[version:]
    
    def get_version(self, client_id: str) -> int:
        """
        Get the current version number for a client
        
        Args:
            client_id: Client ID
            
        Returns:
            Current version number
        """
        return self.versions.get(client_id, 0)
    
    def transform_operation(self, client_id: str, operation: Operation, client_version: int) -> Operation:
        """
        Transform an operation against all concurrent operations
        
        Args:
            client_id: Client ID
            operation: Operation to transform
            client_version: Client's version number
            
        Returns:
            Transformed operation
        """
        # Get all operations that happened concurrently
        concurrent_ops = self.operations[client_version:]
        
        # Transform this operation against all concurrent operations
        transformed_op = operation
        for _, other_op in concurrent_ops:
            transformed_op, _ = transform(transformed_op, other_op)
            
        return transformed_op