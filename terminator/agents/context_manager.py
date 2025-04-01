"""
Context Manager Module - Provides agent context management and summarization for Terminator IDE
"""

import logging
import time
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI

# Import necessary components from OpenAI Agent SDK
# Note: This is a placeholder for actual imports needed
try:
    from openai_agent_sdk import RunContextWrapper, AgentContext, function_tool
except ImportError:
    # Create placeholder classes for development
    class RunContextWrapper:
        def __init__(self, context=None):
            self.context = context
    
    class AgentContext:
        def __init__(self):
            self.token_count = 0
            self.max_tokens = 8000
            self.accessed_files = []
            self.executed_commands = []
            self.last_operation = None
            self.session_id = "dev-session"
            self.history_summary = ""
        
        def reset_token_count(self):
            self.token_count = 0
    
    def function_tool(func):
        return func

# Set up logging
logger = logging.getLogger(__name__)

class AgentContextManager:
    """Manages and maintains AI agent context in Terminator IDE"""
    
    def __init__(self, max_tokens: int = 8000, token_warning_threshold: float = 0.8):
        """
        Initialize the agent context manager
        
        Args:
            max_tokens: Maximum tokens to keep in context
            token_warning_threshold: Threshold (as percentage of max_tokens) to trigger warning
        """
        self.max_tokens = max_tokens
        self.token_warning_threshold = token_warning_threshold
        
        # Initialize a new context
        self.initialize_context()
    
    def initialize_context(self) -> AgentContext:
        """
        Initialize a new agent context
        
        Returns:
            The new agent context
        """
        # Create a new context with our parameters
        context = AgentContext()
        context.max_tokens = self.max_tokens
        context.token_count = 0
        context.accessed_files = []
        context.executed_commands = []
        context.last_operation = None
        context.session_id = f"session-{int(time.time())}"
        context.history_summary = ""
        
        self.context = context
        return context
    
    def get_context(self) -> AgentContext:
        """
        Get the current agent context
        
        Returns:
            The current agent context
        """
        return self.context
    
    def update_token_count(self, tokens: int) -> bool:
        """
        Update the token count and check if summarization is needed
        
        Args:
            tokens: Number of tokens to add to the count
            
        Returns:
            True if summarization is needed, False otherwise
        """
        self.context.token_count += tokens
        
        # Check if we've crossed the warning threshold
        warning_threshold = self.max_tokens * self.token_warning_threshold
        
        if self.context.token_count >= self.max_tokens:
            logger.warning(f"Token limit reached ({self.context.token_count}/{self.max_tokens})")
            return True
        elif self.context.token_count >= warning_threshold:
            logger.info(f"Token warning threshold reached ({self.context.token_count}/{self.max_tokens})")
            
        return False
    
    def add_accessed_file(self, file_path: str) -> bool:
        """
        Add a file to the list of accessed files
        
        Args:
            file_path: Path to the file that was accessed
            
        Returns:
            True if summarization is needed, False otherwise
        """
        self.context.accessed_files.append(file_path)
        # This is a rough estimation of tokens added
        return self.update_token_count(len(file_path) // 4)
    
    def add_executed_command(self, command: str) -> bool:
        """
        Add a command to the list of executed commands
        
        Args:
            command: Command that was executed
            
        Returns:
            True if summarization is needed, False otherwise
        """
        self.context.executed_commands.append(command)
        # This is a rough estimation of tokens added
        return self.update_token_count(len(command) // 4)
    
    def set_last_operation(self, operation: str) -> bool:
        """
        Set the last operation performed
        
        Args:
            operation: Description of the operation
            
        Returns:
            True if summarization is needed, False otherwise
        """
        self.context.last_operation = operation
        # This is a rough estimation of tokens added
        return self.update_token_count(len(operation) // 4)

@function_tool
async def summarize_context(ctx: RunContextWrapper[AgentContext]) -> str:
    """
    Summarize the current conversation context to manage token usage.
    This is automatically called when the context reaches the token limit.
    
    Returns:
        A confirmation message after summarizing.
    """
    try:
        logger.info(f"Summarizing context with token count: {ctx.context.token_count}")
        
        # Create a structured summary of recent operations
        summary = {
            "accessed_files": ctx.context.accessed_files[-10:],  # Keep last 10 files
            "executed_commands": ctx.context.executed_commands[-10:], # Keep last 10 commands
            "last_operation": ctx.context.last_operation,
            "session_id": ctx.context.session_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # Use OpenAI to create a more natural language summary
        try:
            # Create a summary using OpenAI
            client = OpenAI()
            
            # Create the prompt for summarization
            prompt = f"""
            Please summarize the following context from a development session:
            
            Files accessed: {', '.join(summary['accessed_files']) if summary['accessed_files'] else 'None'}
            Commands executed: {', '.join(summary['executed_commands']) if summary['executed_commands'] else 'None'}
            Last operation: {summary['last_operation'] or 'None'}
            
            Previous context summary:
            {ctx.context.history_summary or 'No previous summary'}
            
            Generate a concise summary (3-5 sentences) that preserves the most important context information.
            Focus on key files accessed, commands executed, and general operations performed.
            """
            
            # Call the API to generate a summary
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a context summarization assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7,
            )
            
            # Extract the summary from the response
            ai_summary = response.choices[0].message.content.strip()
            
            # Update the context's history summary with the new summary
            ctx.context.history_summary = ai_summary
            logger.info(f"Generated AI summary: {ai_summary[:100]}...")
            
        except Exception as e:
            # Fallback to a basic summary if OpenAI API fails
            logger.error(f"Error generating summary with OpenAI: {str(e)}", exc_info=True)
            ctx.context.history_summary += f"\n[Session {ctx.context.session_id} - {time.strftime('%Y-%m-%d %H:%M:%S')}] "
            ctx.context.history_summary += f"Accessed {len(summary['accessed_files'])} files. "
            ctx.context.history_summary += f"Executed {len(summary['executed_commands'])} commands. "
            ctx.context.history_summary += f"Last operation: {summary['last_operation'] or 'None'}."
            
        # Reset token count after summarization
        ctx.context.reset_token_count()
        
        return "Context summarized successfully. The conversation will continue with the summarized context."
    
    except Exception as e:
        logger.error(f"Error in summarize_context: {str(e)}", exc_info=True)
        # Ensure token count is reset even if summarization fails
        ctx.context.reset_token_count()
        ctx.context.history_summary += f"[Context window reached {ctx.context.max_tokens} tokens and was summarized with an error: {str(e)}]"
        return f"Context summarization encountered an error: {str(e)}, but token count was reset."