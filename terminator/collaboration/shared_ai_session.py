"""
Shared AI Session Module - Enables multiple users to interact with the same AI assistant context
"""

import time
import json
import asyncio
import logging
import uuid
from typing import Dict, List, Any, Optional, Set, Tuple, Union, Callable

from .session import (
    SessionManager,
    CollaborationSession,
    User
)
from ..utils.performance import (
    PerformanceOptimizer,
    TimingProfiler
)

logger = logging.getLogger(__name__)

class AIMessage:
    """Represents a message in the AI conversation"""
    
    def __init__(self, 
                 message_id: str,
                 content: str,
                 role: str,
                 user_id: Optional[str] = None,
                 username: Optional[str] = None,
                 timestamp: Optional[float] = None):
        """
        Initialize an AI message
        
        Args:
            message_id: Unique message ID
            content: Message content
            role: Message role (user, assistant, system)
            user_id: Optional user ID for user messages
            username: Optional username for user messages
            timestamp: Optional message timestamp
        """
        self.message_id = message_id
        self.content = content
        self.role = role
        self.user_id = user_id
        self.username = username
        self.timestamp = timestamp or time.time()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary representation"""
        result = {
            "message_id": self.message_id,
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp
        }
        
        if self.user_id:
            result["user_id"] = self.user_id
            
        if self.username:
            result["username"] = self.username
            
        return result
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'AIMessage':
        """Create message from dictionary representation"""
        return AIMessage(
            message_id=data["message_id"],
            content=data["content"],
            role=data["role"],
            user_id=data.get("user_id"),
            username=data.get("username"),
            timestamp=data.get("timestamp")
        )


class SharedAIContext:
    """Manages shared context for an AI assistant session"""
    
    def __init__(self, 
                 context_id: str,
                 system_prompt: str = "You are a helpful AI coding assistant.",
                 max_history: int = 100,
                 max_token_limit: int = 16000):
        """
        Initialize a shared AI context
        
        Args:
            context_id: Unique context ID
            system_prompt: System prompt for the AI
            max_history: Maximum number of messages to keep in history
            max_token_limit: Maximum token limit for the context
        """
        self.context_id = context_id
        self.created_at = time.time()
        self.messages: List[AIMessage] = []
        self.max_history = max_history
        self.max_token_limit = max_token_limit
        self.current_token_count = 0
        self.last_updated = time.time()
        self.is_generating = False
        self.active_users: Set[str] = set()
        
        # Add system message
        self.add_message(
            content=system_prompt,
            role="system"
        )
        
    def add_message(self, 
                   content: str,
                   role: str,
                   user_id: Optional[str] = None,
                   username: Optional[str] = None) -> AIMessage:
        """
        Add a message to the context
        
        Args:
            content: Message content
            role: Message role (user, assistant, system)
            user_id: Optional user ID for user messages
            username: Optional username for user messages
            
        Returns:
            The created message
        """
        message_id = str(uuid.uuid4())
        message = AIMessage(
            message_id=message_id,
            content=content,
            role=role,
            user_id=user_id,
            username=username
        )
        
        self.messages.append(message)
        self.last_updated = time.time()
        
        # Estimate token count (approximate)
        new_tokens = len(content) // 4
        self.current_token_count += new_tokens
        
        # Trim history if needed
        self._trim_history_if_needed()
        
        return message
    
    def _trim_history_if_needed(self) -> None:
        """Trim message history if it exceeds limits"""
        # First check message count limit
        if len(self.messages) > self.max_history:
            # Remove oldest messages, but keep system messages
            to_remove = len(self.messages) - self.max_history
            
            # Count non-system messages from the start
            non_system_count = 0
            for i, msg in enumerate(self.messages):
                if msg.role != "system":
                    non_system_count += 1
                    if non_system_count > to_remove:
                        # Remove messages up to this point
                        self.messages = self.messages[i:]
                        break
        
        # Then check token count limit (approximate)
        if self.current_token_count > self.max_token_limit:
            # Recalculate token count and remove messages if needed
            self._recalculate_token_count()
            
            while self.current_token_count > self.max_token_limit and len(self.messages) > 1:
                # Remove oldest non-system message
                for i, msg in enumerate(self.messages):
                    if msg.role != "system":
                        removed_msg = self.messages.pop(i)
                        self.current_token_count -= len(removed_msg.content) // 4
                        break
    
    def _recalculate_token_count(self) -> None:
        """Recalculate the token count (approximate)"""
        self.current_token_count = sum(len(msg.content) // 4 for msg in self.messages)
    
    def get_messages_for_ai(self) -> List[Dict[str, str]]:
        """
        Get messages formatted for sending to an AI model
        
        Returns:
            List of message dictionaries in the format expected by AI models
        """
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages
        ]
    
    def get_recent_messages(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent messages
        
        Args:
            count: Number of recent messages to get
            
        Returns:
            List of recent message dictionaries
        """
        return [msg.to_dict() for msg in self.messages[-count:]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary representation"""
        return {
            "context_id": self.context_id,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "is_generating": self.is_generating,
            "active_users": list(self.active_users),
            "message_count": len(self.messages),
            "recent_messages": self.get_recent_messages()
        }


class SharedAIManager:
    """Manages shared AI contexts and integrates with collaboration sessions"""
    
    def __init__(self):
        """Initialize a shared AI manager"""
        self.contexts: Dict[str, SharedAIContext] = {}
        self.session_to_context: Dict[str, str] = {}  # session_id -> context_id
        self.ai_client: Optional[Any] = None
        self.generate_callback: Optional[Callable[[str, List[Dict[str, str]]], Awaitable[str]]] = None
    
    @PerformanceOptimizer.memoize(ttl=5)
    def get_context_count(self) -> int:
        """
        Get the number of active AI contexts
        
        Returns:
            Number of active contexts
        """
        return len(self.contexts)
    
    def create_context(self, 
                      system_prompt: str = "You are a helpful AI coding assistant.",
                      context_id: Optional[str] = None) -> SharedAIContext:
        """
        Create a new shared AI context
        
        Args:
            system_prompt: System prompt for the AI
            context_id: Optional context ID
            
        Returns:
            The created context
        """
        context_id = context_id or str(uuid.uuid4())
        context = SharedAIContext(
            context_id=context_id,
            system_prompt=system_prompt
        )
        self.contexts[context_id] = context
        return context
    
    def get_context(self, context_id: str) -> Optional[SharedAIContext]:
        """
        Get a shared AI context by ID
        
        Args:
            context_id: Context ID
            
        Returns:
            The context or None if not found
        """
        return self.contexts.get(context_id)
    
    def link_session_to_context(self, session_id: str, context_id: str) -> None:
        """
        Link a collaboration session to an AI context
        
        Args:
            session_id: Collaboration session ID
            context_id: AI context ID
        """
        self.session_to_context[session_id] = context_id
    
    def get_context_for_session(self, session_id: str) -> Optional[SharedAIContext]:
        """
        Get the AI context for a collaboration session
        
        Args:
            session_id: Collaboration session ID
            
        Returns:
            The AI context or None if not found
        """
        context_id = self.session_to_context.get(session_id)
        if context_id:
            return self.get_context(context_id)
        return None
    
    def register_ai_client(self, client: Any) -> None:
        """
        Register an AI client for generating responses
        
        Args:
            client: AI client
        """
        self.ai_client = client
    
    def register_generate_callback(self, callback: Callable[[str, List[Dict[str, str]]], Awaitable[str]]) -> None:
        """
        Register a callback for generating AI responses
        
        Args:
            callback: Function that takes a context ID and messages, returns a response
        """
        self.generate_callback = callback
    
    @TimingProfiler.async_profile
    async def generate_response(self, context_id: str) -> Optional[AIMessage]:
        """
        Generate an AI response for the given context
        
        Args:
            context_id: Context ID
            
        Returns:
            The generated message or None if generation failed
        """
        context = self.get_context(context_id)
        if not context:
            logger.error(f"Context not found: {context_id}")
            return None
        
        if context.is_generating:
            logger.warning(f"Already generating a response for context: {context_id}")
            return None
        
        try:
            context.is_generating = True
            
            if not self.generate_callback:
                logger.error("No generate callback registered")
                return None
            
            # Get messages for AI
            messages = context.get_messages_for_ai()
            
            # Generate response
            response = await self.generate_callback(context_id, messages)
            
            # Add response to context
            message = context.add_message(
                content=response,
                role="assistant"
            )
            
            return message
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return None
        finally:
            context.is_generating = False
    
    def get_all_contexts(self) -> List[Dict[str, Any]]:
        """
        Get information about all contexts
        
        Returns:
            List of context info dictionaries
        """
        return [context.to_dict() for context in self.contexts.values()]


class SharedAICollaborationIntegration:
    """Integrates shared AI sessions with the collaboration system"""
    
    def __init__(self, 
                 session_manager: SessionManager,
                 ai_manager: SharedAIManager):
        """
        Initialize integration between collaboration and AI systems
        
        Args:
            session_manager: Collaboration session manager
            ai_manager: Shared AI manager
        """
        self.session_manager = session_manager
        self.ai_manager = ai_manager
        
    async def handle_ai_message(self, 
                              session_id: str, 
                              client_id: str, 
                              message: str) -> Dict[str, Any]:
        """
        Handle an AI message from a client
        
        Args:
            session_id: Collaboration session ID
            client_id: Client ID
            message: Message content
            
        Returns:
            Response data including status and message info
        """
        # Get the session
        session = self.session_manager.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": f"Session not found: {session_id}"
            }
        
        # Get the client user
        user = None
        for uid, u in session.users.items():
            if uid == client_id:
                user = u
                break
                
        if not user:
            return {
                "status": "error",
                "error": f"User not found in session: {client_id}"
            }
        
        # Get or create AI context for this session
        context = self.ai_manager.get_context_for_session(session_id)
        if not context:
            # Create a new context for this session
            context = self.ai_manager.create_context()
            self.ai_manager.link_session_to_context(session_id, context.context_id)
            
        # Add user to active users
        context.active_users.add(client_id)
            
        # Add user message to context
        user_message = context.add_message(
            content=message,
            role="user",
            user_id=client_id,
            username=user.username
        )
        
        # Broadcast message to all clients in session
        await session.broadcast({
            "type": "ai_message",
            "message": user_message.to_dict(),
            "context_id": context.context_id
        })
        
        # Generate AI response
        ai_message = await self.ai_manager.generate_response(context.context_id)
        
        if not ai_message:
            return {
                "status": "error",
                "error": "Failed to generate AI response"
            }
            
        # Broadcast AI response to all clients in session
        await session.broadcast({
            "type": "ai_message",
            "message": ai_message.to_dict(),
            "context_id": context.context_id
        })
        
        return {
            "status": "success",
            "user_message": user_message.to_dict(),
            "ai_message": ai_message.to_dict()
        }
    
    async def get_ai_context(self, session_id: str) -> Dict[str, Any]:
        """
        Get the AI context for a session
        
        Args:
            session_id: Collaboration session ID
            
        Returns:
            Response data including status and context info
        """
        # Get the session
        session = self.session_manager.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": f"Session not found: {session_id}"
            }
        
        # Get AI context for this session
        context = self.ai_manager.get_context_for_session(session_id)
        if not context:
            return {
                "status": "error",
                "error": "No AI context for this session"
            }
            
        return {
            "status": "success",
            "context": context.to_dict()
        }
    
    async def handle_message_stream(self, 
                                 session_id: str, 
                                 client_id: str,
                                 callback: Callable[[str, bool], Awaitable[None]]) -> None:
        """
        Handle streaming AI messages back to the client
        
        Args:
            session_id: Collaboration session ID
            client_id: Client ID
            callback: Function to call with each chunk of the message
        """
        # Implementation for streaming AI messages
        # This would require integration with a streaming AI client
        pass