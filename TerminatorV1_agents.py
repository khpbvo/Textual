"""
TerminatorV1 Agents - Agent integration for the Terminator IDE
Provides OpenAI agent-based code assistance, analysis, and generation
"""
import os
import logging
import json
import time
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import httpx
# Temporary compatibility shim for OpenAI client type changes
try:
    from openai.types.responses import tool as _oai_tool_mod
    # In newer openai clients, web search filters live under web_search_tool.Filters
    if not hasattr(_oai_tool_mod, "WebSearchToolFilters"):
        from openai.types.responses import web_search_tool as _oai_web_search_tool
        # Provide alias expected by Agents SDK
        _oai_tool_mod.WebSearchToolFilters = _oai_web_search_tool.Filters  # type: ignore[attr-defined]
except Exception:
    # If the client layout differs further, defer to SDK imports (may still fail)
    pass

# Import OpenAI and agent framework
import openai
from openai import OpenAI
from agents import (
    Agent,
    ModelSettings, 
    Runner, 
    function_tool, 
    RunContextWrapper, 
    handoff,
    set_default_openai_key,
    input_guardrail,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    TResponseInputItem,
    ItemHelpers,
    RunConfig,
)

# Import tools for the agents to use
from TerminatorV1_tools import FileSystem, CodeAnalyzer, GitManager, PythonRunner

# Set up logging
logger = logging.getLogger("terminator_agents")
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.WARNING)

# Set API key from environment
OpenAI.api_key = os.getenv("OPENAI_API_KEY")
set_default_openai_key(os.getenv("OPENAI_API_KEY"))

# Global clients for OpenAI
_openai_client = None
_async_openai_client = None

def set_openai_clients(client, async_client):
    """Set global OpenAI clients with custom configurations"""
    global _openai_client, _async_openai_client
    _openai_client = client
    _async_openai_client = async_client

def get_openai_client():
    """Get the configured OpenAI client"""
    return _openai_client

def get_async_openai_client():
    """Get the configured async OpenAI client"""
    return _async_openai_client

# Define security guardrail for malicious inputs
class SecurityCheckOutput(BaseModel):
    """Output model for security check guardrail"""
    is_malicious: bool = Field(..., description="Whether the input appears to be malicious")
    risk_type: Optional[str] = Field(None, description="Type of security risk identified")
    reasoning: str = Field(..., description="Reasoning behind the security assessment")

# Define the context for the agent
class AgentContext(BaseModel):
    """Context object to pass between agents and tools"""
    current_dir: str
    history_summary: str = ""
    token_count: int = 0
    max_tokens: int = 150000
    accessed_files: List[str] = Field(default_factory=list)
    executed_commands: List[str] = Field(default_factory=list)
    last_operation: Optional[str] = None
    session_id: str = Field(default_factory=lambda: f"session_{int(time.time())}")
    
    def update_token_count(self, new_tokens: int) -> bool:
        """
        Update token count and check if summarization is needed
        
        Args:
            new_tokens: Number of tokens to add to the count
            
        Returns:
            bool: True if summarization is needed, False otherwise
        """
        self.token_count += new_tokens
        return self.token_count >= self.max_tokens
    
    def reset_token_count(self) -> None:
        """Reset token count after summarization"""
        self.token_count = 0
        
    def track_file_access(self, file_path: str) -> None:
        """
        Track file access in the context
        
        Args:
            file_path: Path of the accessed file
        """
        if file_path not in self.accessed_files:
            self.accessed_files.append(file_path)
            
    def track_command(self, command: str) -> None:
        """
        Track command execution in the context
        
        Args:
            command: The executed command
        """
        self.executed_commands.append(command)
        
    def set_operation(self, operation: str) -> None:
        """
        Set the last operation performed
        
        Args:
            operation: Description of the operation
        """
        self.last_operation = operation

# Create a security check agent
# Create a security check agent with more permissive file system rules
security_check_agent = Agent(
    name="Security Guardrail",
    instructions="""You are a security guardrail for a Python development environment. Your job is to analyze user input and 
    determine if it might be trying to:
    
    1. Execute clearly malicious code with harmful intent
    2. Access highly sensitive system information (like /etc/passwd, SSH keys, etc.)
    3. Perform destructive operations with clear intent to damage (rm -rf /, format drives, etc.)
    4. Use the system for hacking, attacks, or other explicitly harmful purposes
    5. Execute code injections, XSS, or other attack vectors against external systems
    
    IMPORTANT: The following actions are ALLOWED and should NOT be flagged:
    - Normal directory traversal and searching (cd, ls, find, etc.)
    - Reading code files and documentation
    - File operations within the project directory structure 
    - Searching in subdirectories, even recursively
    - Git operations
    - Running or debugging Python code that appears legitimate
    
    Only flag requests that have clear malicious intent, not legitimate development activities.
    Directory traversal within a development project is entirely legitimate and should be ALLOWED.
    
    Return a structured assessment with your conclusion.""",
    model="gpt-5",
    output_type=SecurityCheckOutput
)

@input_guardrail
async def security_guardrail(
    ctx: RunContextWrapper[AgentContext], 
    agent: Agent, 
    input: str | list[TResponseInputItem]
) -> GuardrailFunctionOutput:
    """
    Security guardrail to prevent malicious inputs, with exceptions for normal file operations
    
    Args:
        ctx: Context wrapper
        agent: The agent being protected
        input: The user input
        
    Returns:
        GuardrailFunctionOutput with security assessment
    """
    # Check if the input is asking for a basic file system operation that should be allowed
    try:
        input_str = input if isinstance(input, str) else json.dumps(input)
    except Exception:
        input_str = str(input)
    
    # List of patterns that should be explicitly allowed
    safe_patterns = [
        r'search.*file',
        r'search.*directory',
        r'find.*file',
        r'look for.*file',
        r'search in subdirectory',
        r'search recursively',
        r'list.*directory',
        r'list.*file',
        r'explore.*directory',
        r'navigate.*directory',
        r'change directory',
        r'cd ',
        r'ls ',
        r'dir ',
        r'find ',
        r'open.*file',
        r'read.*file',
        r'edit.*file',
        r'modify.*file',
        r'change.*file',
        r'update.*code',
        r'edit.*current.*file',
        r'update.*current.*file'
    ]
    
    # Check if input matches any safe pattern
    for pattern in safe_patterns:
        if re.search(pattern, input_str, re.IGNORECASE):
            logger.info(f"Security guardrail: Allowing file operation matching pattern: {pattern}")
            return GuardrailFunctionOutput(
                output_info=SecurityCheckOutput(
                    is_malicious=False,
                    risk_type=None,
                    reasoning="This is a legitimate file system operation for development purposes."
                ),
                tripwire_triggered=False
            )

    # Run the security check agent on the input
    result = await Runner.run(security_check_agent, input, context=ctx.context)
    security_check = result.final_output
    
    # Double-check for file operation false positives
    if security_check.is_malicious and "directory" in input_str.lower():
        # Reduce false positives for directory operations
        logger.info("Security guardrail: Overriding false positive for directory operation")
        return GuardrailFunctionOutput(
            output_info=SecurityCheckOutput(
                is_malicious=False,
                risk_type=None,
                reasoning="File system operation appears to be legitimate."
            ),
            tripwire_triggered=False
        )
    
    # Return the guardrail result
    return GuardrailFunctionOutput(
        output_info=security_check,
        tripwire_triggered=security_check.is_malicious,
    )

# Define Pydantic models for structured agent outputs
class CodeGenerationOutput(BaseModel):
    code: str = Field(..., description="The generated Python code")
    explanation: str = Field(..., description="Explanation of what the code does")
    file_path: Optional[str] = Field(None, description="Suggested file path for the code")

class CodeAnalysisOutput(BaseModel):
    issues: List[Dict[str, Any]] = Field(default_factory=list, description="List of identified issues")
    improvements: List[str] = Field(default_factory=list, description="Suggested improvements")
    summary: str = Field(..., description="Summary of code analysis")

class ProjectAnalysisOutput(BaseModel):
    structure: Dict[str, Any] = Field(..., description="Project structure information")
    dependencies: List[str] = Field(default_factory=list, description="Project dependencies")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations for improvement")
    summary: str = Field(..., description="Summary of project analysis")

class TerminalAgentOutput(BaseModel):
    response: str = Field(..., description="The agent's response to the user query")
    files_accessed: List[str] = Field(default_factory=list, description="Files accessed during processing")
    commands_executed: List[str] = Field(default_factory=list, description="Commands executed during processing")

# File System Tools
@function_tool
async def list_directory(ctx: RunContextWrapper[AgentContext], path: Optional[str] = None) -> str:
    """
    List the contents of a directory.
    
    Args:
        path: Optional path to list. If not provided, uses current directory.
    
    Returns:
        A string representation of the directory contents.
    """
    try:
        # Validate context
        if not ctx.context or not ctx.context.current_dir:
            logger.error("Invalid agent context or missing current_dir")
            return "Error: Agent context is invalid or missing current directory information."
        
        # Resolve target path
        target_path = path if path is not None else ctx.context.current_dir
        
        # Log the target path for debugging
        logger.info(f"Attempting to list directory: {target_path}")
        
        # Handle relative paths
        if not os.path.isabs(target_path):
            target_path = os.path.join(ctx.context.current_dir, target_path)
            logger.info(f"Resolved to absolute path: {target_path}")
        
        # Check if directory exists
        if not os.path.exists(target_path):
            logger.error(f"Directory not found: {target_path}")
            return f"Error: Directory not found: {target_path}"
            
        if not os.path.isdir(target_path):
            logger.error(f"Path is not a directory: {target_path}")
            return f"Error: Path is not a directory: {target_path}"
        
        # Use the FileSystem utility with max_depth=2 (handled inside function)
        structure = FileSystem.get_directory_structure(target_path, max_depth=2)
        
        # Check if we got an error
        if isinstance(structure, dict) and "error" in structure:
            logger.error(f"Error getting directory structure: {structure['error']}")
            return f"Error listing directory: {structure['error']}"
        
        # Log success
        logger.info(f"Successfully listed directory: {target_path}")
        
        # Track operation
        ctx.context.set_operation(f"Listed directory: {os.path.basename(target_path) or target_path}")
        
        return json.dumps(structure, indent=2)
    except Exception as e:
        logger.error(f"Exception listing directory {path}: {str(e)}", exc_info=True)
        return f"Error listing directory: {str(e)}"

@function_tool
async def find_file(
    ctx: RunContextWrapper[AgentContext], 
    filename: str,
    start_path: Optional[str] = None,
    recursive: Optional[bool] = None
) -> str:
    """
    Safely find a file by name in the filesystem
    
    Args:
        filename: Name of the file to find
        start_path: Directory to start searching from (uses current directory if not specified)
        recursive: Whether to search recursively in subdirectories (default True)
        
    Returns:
        Path to the file if found, or error message
    """
    # Handle default inside function
    if recursive is None:
        recursive = True
        
    try:
        # Validate context
        if not ctx.context or not ctx.context.current_dir:
            logger.error("Invalid agent context or missing current_dir")
            return json.dumps({
                "error": "Agent context is invalid or missing current directory information."
            })
        
        # Get the starting search path
        search_path = start_path or ctx.context.current_dir
        
        # Handle special paths
        if search_path == "~" or search_path.startswith("~/"):
            search_path = os.path.expanduser(search_path)
        
        # Handle relative paths
        if not os.path.isabs(search_path):
            search_path = os.path.join(ctx.context.current_dir, search_path)
        
        logger.info(f"Searching for file: '{filename}', starting from: '{search_path}', recursive: {recursive}")
        
        # Check if the starting path exists
        if not os.path.exists(search_path):
            logger.error(f"Search path not found: {search_path}")
            return json.dumps({
                "error": f"Search path not found: {search_path}",
                "found": False
            })
            
        if not os.path.isdir(search_path):
            logger.error(f"Search path is not a directory: {search_path}")
            return json.dumps({
                "error": f"Search path is not a directory: {search_path}",
                "found": False
            })
        
        found_files = []
        
        # Function to recursively walk directories and find files
        def find_in_directory(current_path, max_depth=30, current_depth=0):
            if current_depth > max_depth:
                return
            
            try:
                # List all items in the current directory
                items = os.listdir(current_path)
                
                for item in items:
                    item_path = os.path.join(current_path, item)
                    
                    # Check if it's a file that matches
                    if os.path.isfile(item_path) and item == filename:
                        found_files.append(item_path)
                        logger.info(f"Found matching file: {item_path}")
                    
                    # If it's a directory and recursive search is enabled, search it too
                    elif os.path.isdir(item_path) and recursive:
                        find_in_directory(item_path, max_depth, current_depth + 1)
            
            except Exception as e:
                logger.warning(f"Error accessing directory {current_path}: {str(e)}")
                # Continue the search in other directories
        
        # Start the search
        find_in_directory(search_path)
        
        # Return the results
        if not found_files:
            return json.dumps({
                "found": False,
                "message": f"File '{filename}' not found starting from '{search_path}'"
            })
        
        return json.dumps({
            "found": True,
            "file_count": len(found_files),
            "files": found_files,
            "message": f"Found {len(found_files)} matching files"
        })
        
    except Exception as e:
        logger.error(f"Exception in find_file: {str(e)}", exc_info=True)
        return json.dumps({
            "error": f"Error searching for file: {str(e)}",
            "found": False
        })

@function_tool
async def read_file(ctx: RunContextWrapper[AgentContext], file_path: str) -> str:
    """
    Read and return the contents of a file.
    
    Args:
        file_path: Path to the file to read. Can be absolute or relative to current directory.
    
    Returns:
        The contents of the file as a string.
    """
    try:
        # Log the original file path for debugging
        logger.info(f"Attempting to read file: {file_path}")
        logger.info(f"Current directory: {ctx.context.current_dir}")
        
        # Validate context
        if not ctx.context or not ctx.context.current_dir:
            logger.error("Invalid agent context or missing current_dir")
            return "Error: Agent context is invalid or missing current directory information."
        
        # Handle relative paths
        if not os.path.isabs(file_path):
            file_path = os.path.join(ctx.context.current_dir, file_path)
        
        # Log the resolved file path
        logger.info(f"Resolved file path: {file_path}")
        
        # Check if file exists before trying to read it
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return f"Error: File not found: {file_path}"
            
        if not os.path.isfile(file_path):
            logger.error(f"Path is not a file: {file_path}")
            return f"Error: Path is not a file: {file_path}"
        
        # Use the FileSystem utility
        success, content = FileSystem.read_file(file_path)
        
        if not success:
            logger.error(f"Failed to read file: {content}")
            return f"Error reading file: {content}"
        
        # Log success
        logger.info(f"Successfully read file: {file_path}")
        
        # Update token count (rough estimate)
        tokens_added = len(content.split())
        needs_summary = ctx.context.update_token_count(tokens_added)
        
        # Track file access in context
        ctx.context.track_file_access(file_path)
        ctx.context.set_operation(f"Read file: {os.path.basename(file_path)}")
        
        # Trigger summarization if token threshold is reached
        if needs_summary:
            logger.info(f"Token threshold reached ({ctx.context.token_count}/{ctx.context.max_tokens}), triggering summarization")
            # Call the summarize_context function
            await summarize_context(ctx)
            logger.info(f"Context summarized, new token count: {ctx.context.token_count}")
        
        return content
    except Exception as e:
        logger.error(f"Exception reading file {file_path}: {str(e)}", exc_info=True)
        return f"Error reading file: {str(e)}"

@function_tool
async def search_files(
    ctx: RunContextWrapper[AgentContext], 
    search_term: str, 
    path: Optional[str] = None,
    file_pattern: Optional[str] = None,
    recursive: Optional[bool] = None,
    case_sensitive: Optional[bool] = None
) -> str:
    """
    Enhanced file search with improved robustness for finding files across directories
    
    Args:
        search_term: Term to search for (filename or content)
        path: Directory to search in (uses current directory if not specified)
        file_pattern: File pattern to match (e.g., "*.py")
        recursive: Whether to search recursively in subdirectories (default True)
        case_sensitive: Whether the search is case sensitive (default False)
        
    Returns:
        Structured search results
    """
    # Set default values for optional parameters inside the function body
    if recursive is None:
        recursive = True
    if case_sensitive is None:
        case_sensitive = False
        
    try:
        # Validate context
        if not ctx.context or not ctx.context.current_dir:
            logger.error("Invalid agent context or missing current_dir")
            return json.dumps({
                "error": "Agent context is invalid or missing current directory information."
            })
        
        # Validate search term
        if not search_term or not isinstance(search_term, str):
            logger.error(f"Invalid search term: {search_term}")
            return json.dumps({
                "error": "Search term is required and must be a string."
            })
            
        # Get the target path, expanding user directory
        target_path = path or ctx.context.current_dir
        
        # Handle special paths
        if target_path == "~" or target_path.startswith("~/"):
            target_path = os.path.expanduser(target_path)
        
        # Handle relative paths
        if not os.path.isabs(target_path):
            target_path = os.path.join(ctx.context.current_dir, target_path)
        
        logger.info(f"Search request - term: '{search_term}', path: '{target_path}', pattern: '{file_pattern}', recursive: {recursive}")
        
        # Check if directory exists
        if not os.path.exists(target_path):
            logger.error(f"Directory not found: {target_path}")
            return json.dumps({
                "error": f"Directory not found: {target_path}"
            })
            
        if not os.path.isdir(target_path):
            logger.error(f"Path is not a directory: {target_path}")
            return json.dumps({
                "error": f"Path is not a directory: {target_path}"
            })
        
        results = {
            "filename_matches": [],
            "content_matches": []
        }
        
        # Track operation in context
        ctx.context.set_operation(f"Searching for '{search_term}' in {target_path}")
        
        # Function to recursively walk directories and find files
        def walk_directory(current_path, max_depth=20, current_depth=0):
            if current_depth > max_depth:
                return
            
            try:
                # List all items in the current directory
                items = os.listdir(current_path)
                
                for item in items:
                    item_path = os.path.join(current_path, item)
                    
                    # Check if it's a file
                    if os.path.isfile(item_path):
                        # Check if file matches search criteria
                        if file_pattern:
                            import fnmatch
                            if not fnmatch.fnmatch(item, file_pattern):
                                continue
                        
                        # Check for filename match
                        filename_match = False
                        if case_sensitive:
                            if search_term == item:
                                filename_match = True
                                match_type = "exact match"
                            elif search_term in item:
                                filename_match = True
                                match_type = "partial match"
                        else:
                            if search_term.lower() == item.lower():
                                filename_match = True
                                match_type = "exact match"
                            elif search_term.lower() in item.lower():
                                filename_match = True
                                match_type = "partial match"
                        
                        if filename_match:
                            results["filename_matches"].append({
                                "path": item_path,
                                "type": match_type
                            })
                            logger.info(f"Found filename match: {item_path}")
                        
                        # Check for content match if there's a search term
                        if search_term:
                            try:
                                success, content = FileSystem.read_file(item_path, max_size_mb=5)
                                if success:
                                    content_matches = []
                                    for i, line in enumerate(content.splitlines()):
                                        if (case_sensitive and search_term in line) or \
                                            (not case_sensitive and search_term.lower() in line.lower()):
                                            content_matches.append({
                                                "line": i + 1,
                                                "content": line.strip()
                                            })
                                    
                                    if content_matches:
                                        results["content_matches"].append({
                                            "file": item_path,
                                            "matches": content_matches[:5]  # Limit to 5 matches per file
                                        })
                                        logger.info(f"Found content matches in: {item_path}")
                                        ctx.context.track_file_access(item_path)
                            except Exception as e:
                                logger.warning(f"Error reading file {item_path}: {str(e)}")
                    
                    # If it's a directory and recursive search is enabled, search it too
                    elif os.path.isdir(item_path) and recursive:
                        walk_directory(item_path, max_depth, current_depth + 1)
            
            except Exception as e:
                logger.warning(f"Error accessing directory {current_path}: {str(e)}")
        
        # Start the directory walk from the target path
        walk_directory(target_path)
        
        # Clean up and format the results
        if not results["filename_matches"] and not results["content_matches"]:
            return json.dumps({
                "found": False,
                "message": f"No matches found for '{search_term}' in {target_path}"
            })
        
        return json.dumps({
            "found": True,
            "filename_matches": results["filename_matches"],
            "content_matches": results["content_matches"],
            "message": f"Found {len(results['filename_matches'])} files matching '{search_term}' and {len(results['content_matches'])} files with matching content"
        })
        
    except Exception as e:
        logger.error(f"Exception in search_files: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Error searching files: {str(e)}"})

@function_tool
async def find_in_parent_directories(
    ctx: RunContextWrapper[AgentContext], 
    name: str,
    levels_up: Optional[int] = None,
    is_directory: Optional[bool] = None
) -> str:
    """
    Search for a file or directory in the current directory and parent directories
    
    Args:
        name: Name of the file or directory to find
        levels_up: Maximum number of parent directories to check (None for no limit)
        is_directory: Whether to look for a directory (True) or file (False). None means either.
        
    Returns:
        Path information if found, or error message
    """
    try:
        # Validate context
        if not ctx.context or not ctx.context.current_dir:
            logger.error("Invalid agent context or missing current_dir")
            return json.dumps({
                "error": "Agent context is invalid or missing current directory information.",
                "found": False
            })
        
        # Start with current directory
        current_path = ctx.context.current_dir
        logger.info(f"Starting search for {'directory' if is_directory else 'file'} '{name}' from {current_path}")
        
        # Keep track of searched directories
        searched_dirs = []
        level = 0
        
        # Check current and parent directories
        while current_path and (levels_up is None or level <= levels_up):
            searched_dirs.append(current_path)
            
            # First check for direct match
            target_path = os.path.join(current_path, name)
            logger.info(f"Checking {target_path}")
            
            if os.path.exists(target_path):
                # Check if it's the right type (file or directory)
                if is_directory is None:
                    # Either type is fine
                    logger.info(f"Found match: {target_path}")
                    return json.dumps({
                        "found": True,
                        "path": target_path,
                        "type": "directory" if os.path.isdir(target_path) else "file",
                        "parent_dir": current_path,
                        "levels_up": level
                    })
                elif is_directory and os.path.isdir(target_path):
                    # Found matching directory
                    logger.info(f"Found directory: {target_path}")
                    return json.dumps({
                        "found": True,
                        "path": target_path,
                        "type": "directory",
                        "parent_dir": current_path,
                        "levels_up": level
                    })
                elif not is_directory and os.path.isfile(target_path):
                    # Found matching file
                    logger.info(f"Found file: {target_path}")
                    return json.dumps({
                        "found": True,
                        "path": target_path,
                        "type": "file",
                        "parent_dir": current_path,
                        "levels_up": level
                    })
            
            # Next, search inside directory for sub-matches if we're looking for files
            if is_directory is not True:  # If we're looking for files or either type
                try:
                    # List the directory and see if we can find a partial match
                    for item in os.listdir(current_path):
                        item_path = os.path.join(current_path, item)
                        if os.path.isfile(item_path) and name in item:
                            logger.info(f"Found partial file match: {item_path}")
                            return json.dumps({
                                "found": True,
                                "path": item_path,
                                "type": "file",
                                "parent_dir": current_path,
                                "levels_up": level,
                                "note": f"Partial match for '{name}'"
                            })
                except Exception as e:
                    logger.warning(f"Error listing directory {current_path}: {str(e)}")
            
            # Move up to parent directory
            parent_path = os.path.dirname(current_path)
            if parent_path == current_path:
                # We've reached the root
                break
                
            current_path = parent_path
            level += 1
        
        # If we get here, we didn't find it
        return json.dumps({
            "found": False,
            "searched_directories": searched_dirs,
            "message": f"Could not find {'directory' if is_directory else 'file'} '{name}' in current or parent directories"
        })
        
    except Exception as e:
        logger.error(f"Exception in find_in_parent_directories: {str(e)}", exc_info=True)
        return json.dumps({
            "error": f"Error searching for {name}: {str(e)}",
            "found": False
        })

@function_tool
async def search_project_directories(
    ctx: RunContextWrapper[AgentContext], 
    name: str,
    directory_level: Optional[str] = None,
    search_type: Optional[str] = None
) -> str:
    """
    Perform a comprehensive search for files or directories in the project
    
    Args:
        name: Name of the file or directory to find
        directory_level: Where to search ('current', 'parent', 'parent_parent', 'all' or 'root')
        search_type: What to search for ('file', 'directory', or 'both')
        
    Returns:
        JSON result with search findings
    """
    try:
        # Validate context
        if not ctx.context or not ctx.context.current_dir:
            logger.error("Invalid agent context or missing current_dir")
            return json.dumps({
                "error": "Agent context is invalid or missing current directory information."
            })
        
        # Set default values
        if directory_level is None:
            directory_level = "all"
        
        if search_type is None:
            search_type = "both"
            
        # Determine what kind of object we're looking for
        is_directory = None
        if search_type == "file":
            is_directory = False
        elif search_type == "directory":
            is_directory = True
        # else leave as None for "both"
        
        # Determine starting directory
        current_dir = ctx.context.current_dir
        parent_dir = os.path.dirname(current_dir)
        parent_parent_dir = os.path.dirname(parent_dir)
        
        # Find the project root (usually the Git root if available)
        root_dir = None
        try:
            is_repo, repo_root = GitManager.check_git_repo(current_dir)
            if is_repo:
                root_dir = repo_root
        except Exception:
            # If we can't determine Git root, use 3 levels up as estimate
            temp = current_dir
            for _ in range(3):
                temp = os.path.dirname(temp)
                if temp == os.path.dirname(temp):  # We've hit the filesystem root
                    break
            root_dir = temp
        
        # Determine which directories to search
        dirs_to_search = []
        
        if directory_level == "current":
            dirs_to_search = [current_dir]
        elif directory_level == "parent":
            dirs_to_search = [parent_dir]
        elif directory_level == "parent_parent":
            dirs_to_search = [parent_parent_dir]
        elif directory_level == "root" and root_dir:
            dirs_to_search = [root_dir]
        else:  # "all" or unrecognized value
            # Build a path from root to current to search all relevant directories
            dirs_to_search = []
            temp = current_dir
            while temp and (not root_dir or os.path.commonpath([temp, root_dir]) == root_dir):
                dirs_to_search.append(temp)
                parent = os.path.dirname(temp)
                if parent == temp:  # We've hit the filesystem root
                    break
                temp = parent
            # Add project root if available and not already included
            if root_dir and root_dir not in dirs_to_search:
                dirs_to_search.append(root_dir)
        
        # Log search parameters
        logger.info(f"Searching for {search_type} '{name}' in: {dirs_to_search}")
        
        results = {
            "exact_matches": [],
            "partial_matches": [],
            "searched_directories": dirs_to_search
        }
        
        # Search each directory
        for dir_path in dirs_to_search:
            if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
                continue
                
            # First check for direct matches in this directory
            target_path = os.path.join(dir_path, name)
            if os.path.exists(target_path):
                # Check if it's the right type
                if is_directory is None or (is_directory and os.path.isdir(target_path)) or (not is_directory and os.path.isfile(target_path)):
                    results["exact_matches"].append({
                        "path": target_path,
                        "parent": dir_path,
                        "type": "directory" if os.path.isdir(target_path) else "file"
                    })
            
            # Then do a more comprehensive search inside this directory
            try:
                # Walk through the directory
                for root, dirs, files in os.walk(dir_path):
                    # Check files if we're looking for files or both
                    if is_directory is not True:  # False or None
                        for file in files:
                            if name == file:  # Exact match
                                file_path = os.path.join(root, file)
                                results["exact_matches"].append({
                                    "path": file_path,
                                    "parent": root,
                                    "type": "file"
                                })
                            elif name in file:  # Partial match
                                file_path = os.path.join(root, file)
                                results["partial_matches"].append({
                                    "path": file_path,
                                    "parent": root,
                                    "type": "file"
                                })
                    
                    # Check directories if we're looking for directories or both
                    if is_directory is not False:  # True or None
                        for dir_name in dirs:
                            if name == dir_name:  # Exact match
                                dir_path = os.path.join(root, dir_name)
                                results["exact_matches"].append({
                                    "path": dir_path,
                                    "parent": root,
                                    "type": "directory"
                                })
                            elif name in dir_name:  # Partial match
                                dir_path = os.path.join(root, dir_name)
                                results["partial_matches"].append({
                                    "path": dir_path,
                                    "parent": root,
                                    "type": "directory"
                                })
            except Exception as e:
                logger.warning(f"Error searching directory {dir_path}: {str(e)}")
                # Continue with other directories
        
        # Format results
        summary = {
            "found": len(results["exact_matches"]) > 0 or len(results["partial_matches"]) > 0,
            "exact_match_count": len(results["exact_matches"]),
            "partial_match_count": len(results["partial_matches"]),
            "search_locations": len(results["searched_directories"]),
            "results": results
        }
        
        return json.dumps(summary, indent=2)
        
    except Exception as e:
        logger.error(f"Exception in search_project_directories: {str(e)}", exc_info=True)
        return json.dumps({
            "error": f"Error searching for {name}: {str(e)}",
            "found": False
        })

@function_tool
async def change_directory(ctx: RunContextWrapper[AgentContext], path: str) -> str:
    """
    Change the current working directory.
    
    Args:
        path: The path to change to. Can be absolute or relative.
    
    Returns:
        A message indicating success or failure.
    """
    try:
        # Handle special cases
        if path == "~":
            path = os.path.expanduser("~")
        elif path.startswith("~/"):
            path = os.path.expanduser(path)
        elif not os.path.isabs(path):
            # Handle relative paths
            path = os.path.normpath(os.path.join(ctx.context.current_dir, path))
        
        if not os.path.exists(path):
            return f"Error: Path {path} does not exist."
        
        if not os.path.isdir(path):
            return f"Error: {path} is not a directory."
        
        # Update the context
        ctx.context.current_dir = path
        
        return f"Changed directory to: {path}"
    except Exception as e:
        return f"Error changing directory: {str(e)}"

# Code Analysis Tools
@function_tool
async def analyze_python_file(
    ctx: RunContextWrapper[AgentContext], 
    file_path: str
) -> str:
    """
    Analyze a Python file to find potential bugs and issues.
    
    Args:
        file_path: Path to the Python file to analyze
    
    Returns:
        A string containing the analysis results.
    """
    try:
        # Handle relative paths
        if not os.path.isabs(file_path):
            file_path = os.path.join(ctx.context.current_dir, file_path)
        
        # Check file existence and type
        if not os.path.exists(file_path):
            return f"Error: File {file_path} does not exist."
        
        if not file_path.endswith('.py'):
            return f"Error: {file_path} is not a Python file."
        
        # Read the file
        success, content = FileSystem.read_file(file_path)
        if not success:
            return f"Error: {content}"
        
        # Use the CodeAnalyzer utility
        analysis = CodeAnalyzer.analyze_python_code(content)
        
        # Track file access
        ctx.context.track_file_access(file_path)
        
        return json.dumps(analysis, indent=2)
    except Exception as e:
        return f"Error analyzing Python file: {str(e)}"

@function_tool
async def compare_files(
    ctx: RunContextWrapper[AgentContext],
    original_file: str,
    modified_file: Optional[str] = None,
    original_content: Optional[str] = None,
    modified_content: Optional[str] = None
) -> str:
    """
    Compare two files or text contents and display their differences.
    
    Args:
        original_file: Path to the original file (or identifier if using content)
        modified_file: Path to the modified file (optional)
        original_content: Original content string (optional, instead of file)
        modified_content: Modified content string (optional, instead of file)
        
    Returns:
        A unified diff of the two files or contents
    """
    try:
        # Case 1: Compare file contents
        if modified_file and not (original_content or modified_content):
            # Read files
            if not os.path.isabs(original_file):
                original_file = os.path.join(ctx.context.current_dir, original_file)
            if not os.path.isabs(modified_file):
                modified_file = os.path.join(ctx.context.current_dir, modified_file)
                
            success1, original = FileSystem.read_file(original_file)
            if not success1:
                return f"Error with original file: {original}"
                
            success2, modified = FileSystem.read_file(modified_file)
            if not success2:
                return f"Error with modified file: {modified}"
                
            # Track file access
            ctx.context.track_file_access(original_file)
            ctx.context.track_file_access(modified_file)
            
        # Case 2: Compare original file with provided content
        elif original_file and modified_content and not modified_file:
            if not os.path.isabs(original_file):
                original_file = os.path.join(ctx.context.current_dir, original_file)
                
            success, original = FileSystem.read_file(original_file)
            if not success:
                return f"Error with original file: {original}"
                
            modified = modified_content
            
            # Track file access
            ctx.context.track_file_access(original_file)
            
        # Case 3: Compare provided content strings
        elif original_content and modified_content:
            original = original_content
            modified = modified_content
            
        else:
            return "Error: Must provide either two files, or a file and modified content, or two content strings."
            
        # Create diff
        diff = CodeAnalyzer.create_diff(original, modified)
        
        if not diff:
            return "No differences found."
        
        return diff
            
    except Exception as e:
        return f"Error comparing files: {str(e)}"

@function_tool
async def write_to_file(
    ctx: RunContextWrapper[AgentContext], 
    file_path: str, 
    content: str,
    mode: str
) -> str:
    """
    Write content to a file.
    
    Args:
        file_path: Path to the file to write to
        content: Content to write to the file
        mode: 'w' for write (overwrite), 'a' for append
        
    Returns:
        A message indicating success or failure
    """
    try:
        # Handle relative paths
        if not os.path.isabs(file_path):
            file_path = os.path.join(ctx.context.current_dir, file_path)
        
        # Use the FileSystem utility with create_dirs=True (handle this inside function)
        success, message = FileSystem.write_file(file_path, content, create_dirs=True)
        
        if success:
            # Track file access and operation in context
            ctx.context.track_file_access(file_path)
            operation = "Updated" if mode == 'w' else "Appended to"
            ctx.context.set_operation(f"{operation} file: {os.path.basename(file_path)}")
        
        return message
    except Exception as e:
        return f"Error writing to file: {str(e)}"
        
@function_tool
async def edit_current_file(
    ctx: RunContextWrapper[AgentContext], 
    content: str,
    show_diff: Optional[bool] = None
) -> str:
    """
    Edit the file that's currently open in the editor.
    Shows a diff view for the user to review and approve changes.
    
    Args:
        content: New content for the file
        show_diff: Whether to show diff view (True) or apply directly (False)
        
    Returns:
        A message indicating success or failure
    """
    try:
        # Handle default value inside function
        if show_diff is None:
            show_diff = True
            
        app = ctx.app
        
        # Check if there's a file open in the editor
        if not hasattr(app, 'current_file') or not app.current_file:
            return "Error: No file is currently open in the editor"
        
        current_file = app.current_file
        
        # Get current content from the editor
        editor = app.query_one(f"#{app.active_editor}")
        original_content = editor.text
        
        # Track file access and operation in context
        ctx.context.track_file_access(current_file)
        ctx.context.set_operation(f"Edited current file: {os.path.basename(current_file)}")
        
        if show_diff:
            # Create a diff and show it to the user
            app.show_code_suggestion(original_content, content, f"AI suggested changes for {os.path.basename(current_file)}")
            return f"Showing diff for {os.path.basename(current_file)}. User will need to approve changes."
        else:
            # Apply changes directly
            app.apply_diff_changes(content)
            return f"Changes applied to {os.path.basename(current_file)}"
    except Exception as e:
        return f"Error editing current file: {str(e)}"

@function_tool
async def execute_python(
    ctx: RunContextWrapper[AgentContext], 
    code: str,
    use_file: Optional[bool] = None,
    file_path: Optional[str] = None
) -> str:
    """
    Execute Python code and return the result.
    
    Args:
        code: The Python code to execute
        use_file: Whether to write the code to a file first (default False)
        file_path: Optional path to write the code to before executing
    
    Returns:
        The output of the executed code.
    """
    # Handle default inside function
    if use_file is None:
        use_file = False
        
    try:
        # Track command execution
        command_description = "Execute Python code"
        
        # Use the PythonRunner utility
        if use_file:
            if file_path:
                # Use the specified file path
                if not os.path.isabs(file_path):
                    file_path = os.path.join(ctx.context.current_dir, file_path)
                
                # Write the file
                success, message = FileSystem.write_file(file_path, code)
                if not success:
                    return f"Error writing file: {message}"
                
                # Track file access
                ctx.context.track_file_access(file_path)
                command_description = f"Execute Python script: {os.path.basename(file_path)}"
            else:
                # Use temp file
                command_description = "Execute Python script from temporary file"
            
            # Execute the code
            result = PythonRunner.run_code(code, timeout=30)
            
            output = ""
            if result.get("stdout"):
                output += f"STDOUT:\n{result['stdout']}\n\n"
            if result.get("stderr"):
                output += f"STDERR:\n{result['stderr']}\n\n"
            if "error" in result:
                output += f"ERROR:\n{result['error']}\n\n"
            
            # If there's no output, mention it
            if not output:
                output = "Code executed successfully with no output."
        else:
            # Execute code directly via PythonRunner
            result = PythonRunner.run_code(code, timeout=10)
            
            output = ""
            if result.get("stdout"):
                output += f"STDOUT:\n{result['stdout']}\n\n"
            if result.get("stderr"):
                output += f"STDERR:\n{result['stderr']}\n\n"
            if "error" in result:
                output += f"ERROR:\n{result['error']}\n\n"
        
        # Track command and operation in context
        ctx.context.track_command(command_description)
        ctx.context.set_operation(command_description)
        
        return output
    except Exception as e:
        return f"Error executing Python code: {str(e)}"

# Git Tools
@function_tool
async def git_status(
    ctx: RunContextWrapper[AgentContext],
    repo_path: Optional[str] = None
) -> str:
    """
    Get the status of a Git repository.
    
    Args:
        repo_path: Path to the Git repository (optional, uses current directory if not specified)
        
    Returns:
        Git status information
    """
    try:
        path = repo_path or ctx.context.current_dir
        
        # Check if it's a git repository
        is_repo, repo_root = GitManager.check_git_repo(path)
        
        if not is_repo:
            return json.dumps({"error": "Not a Git repository"})
        
        # Get status
        status = GitManager.get_git_status(repo_root)
        
        # Track operation
        ctx.context.set_operation("Checked Git status")
        
        return json.dumps(status, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error getting Git status: {str(e)}"})

@function_tool
async def git_commit(
    ctx: RunContextWrapper[AgentContext],
    message: str,
    repo_path: Optional[str] = None
) -> str:
    """
    Commit changes to a Git repository.
    
    Args:
        message: Commit message
        repo_path: Path to the Git repository (optional, uses current directory if not specified)
        
    Returns:
        Result of the commit operation
    """
    try:
        path = repo_path or ctx.context.current_dir
        
        # Check if it's a git repository
        is_repo, repo_root = GitManager.check_git_repo(path)
        
        if not is_repo:
            return json.dumps({"error": "Not a Git repository"})
        
        # Commit
        success, result = GitManager.git_commit(repo_root, message)
        
        # Track operation
        ctx.context.track_command(f"Git commit: {message}")
        ctx.context.set_operation("Created Git commit")
        
        if success:
            return json.dumps({"success": True, "message": result})
        else:
            return json.dumps({"error": result})
    except Exception as e:
        return json.dumps({"error": f"Error committing to Git: {str(e)}"})

# Context Management Tool
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
                model="gpt-5",
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

# Define agents for specific tasks
# 1. Code Generation Agent
code_generation_agent = Agent(
    name="Code Generator",
    instructions="""You are an expert Python code generator. Your task is to write clean, efficient, 
    and well-documented Python code based on user requirements. Follow these guidelines:
    
    1. Always include docstrings for functions and classes
    2. Follow PEP 8 style guidelines
    3. Include error handling where appropriate
    4. Write modular, reusable code
    5. Include comments for complex sections
    
    You must return your response as a structured output with:
    - The generated code
    - An explanation of what the code does
    - Python code always in triple backticks ```python ...```
    - Always output in Markdown format
    - An optional suggested file path for the code""",
    model="gpt-5",
    output_type=CodeGenerationOutput,
    tools=[write_to_file, read_file, list_directory, compare_files]
)

# Create specialized variants using clone
data_science_code_generator = code_generation_agent.clone(
    name="Data Science Code Generator",
    instructions="""You are an expert Python code generator specialized in data science. 
    Your task is to write clean, efficient, and well-documented Python code for data science tasks.
    Focus on libraries like pandas, numpy, scikit-learn, matplotlib, and other data science tools.
    
    Follow these guidelines:
    1. Always include docstrings for functions and classes
    2. Follow PEP 8 style guidelines
    3. Include error handling where appropriate
    4. Write modular, reusable code
    5. Include visualizations where appropriate
    6. Always include data validation steps
    
    You must return your response as a structured output with:
    - Python code always in triple backticks ```python ...```
    - Always output in Markdown format
    - The generated code
    - An explanation of what the code does
    - An optional suggested file path for the code"""
)

web_code_generator = code_generation_agent.clone(
    name="Web Development Code Generator",
    instructions="""You are an expert Python code generator specialized in web development.
    Your task is to write clean, efficient, and well-documented Python code for web applications.
    Focus on frameworks like Flask, Django, FastAPI, and related web technologies.
    
    Follow these guidelines:
    1. Always include docstrings for functions and classes
    2. Follow PEP 8 style guidelines
    3. Include error handling where appropriate
    4. Write modular, reusable code
    5. Include security best practices
    6. Consider performance and scalability
    
    You must return your response as a structured output with:
    - Python code always in triple backticks ```python ...```
    - Always output in Markdown format
    - The generated code
    - An explanation of what the code does
    - An optional suggested file path for the code"""
)

# 2. Code Analysis Agent
code_analysis_agent = Agent(
    name="Code Analyzer",
    instructions="""You are an expert code analyzer. Your task is to review Python code, 
    identify issues, and suggest improvements. Focus on:
    
    1. Code quality and adherence to best practices
    2. Potential bugs and error cases
    3. Performance issues
    4. Security vulnerabilities
    5. Readability and maintainability
    
    Use the analysis tools to help identify issues in the code.
    
    You can use the compare_files tool to show differences between original code and your suggested improvements.
    This provides a visual diff that makes it easier for users to understand your proposed changes.
    
    You must return your response as a structured output with:
    - Python code always in triple backticks ```python ...```
    - Always output in Markdown format
    - A list of identified issues
    - A list of suggested improvements
    - A summary of your analysis""",
    model="gpt-5",
    output_type=CodeAnalysisOutput,
    tools=[analyze_python_file, read_file, list_directory, search_files, compare_files]
)

# 3. Project Analysis Agent
project_analysis_agent = Agent(
    name="Project Analyzer",
    instructions="""You are an expert project analyzer. Your task is to review Python projects, 
    understand their structure, dependencies, and architecture. You should:
    
    1. Identify the key components and their relationships
    2. Analyze the project structure and organization
    3. Identify dependencies and their versions
    4. Look for patterns and anti-patterns
    5. Suggest improvements to the project structure
    
    When suggesting structural changes or improvements to files, you can use the compare_files tool
    to show the differences between the original and your suggested version.
    
    You must return your response as a structured output with:
    - Python code always in triple backticks ```python ...```
    - Always output in Markdown format
    - Project structure information
    - A list of project dependencies
    - A list of recommendations for improvement
    - A summary of your analysis""",
    model="gpt-5",
    output_type=ProjectAnalysisOutput,
    tools=[list_directory, read_file, search_files, compare_files]
)

# Define dynamic instructions function for terminal agent
def terminal_agent_instructions(ctx: RunContextWrapper[AgentContext], agent: Agent[AgentContext]) -> str:
    """
    Dynamic instructions for terminal agent that incorporates context information.
    
    Args:
        ctx: Context wrapper containing AgentContext
        agent: The agent object
        
    Returns:
        Formatted instruction string
    """
    # Build accessed files and commands for context
    accessed_files = ", ".join(ctx.context.accessed_files[-5:]) if ctx.context.accessed_files else "None yet"
    executed_commands = ", ".join(ctx.context.executed_commands[-5:]) if ctx.context.executed_commands else "None yet"
    
    # Include history summary if available
    history_context = ""
    if ctx.context.history_summary:
        history_context = f"""
    Previous Context Summary:
    {ctx.context.history_summary}
    """
    
    return f"""You are a Terminal Agent for macOS and Linux, an expert coding assistant designed to help with 
    Python development tasks. You can navigate the file system, read and analyze code, execute Python code, 
    and provide expert assistance with coding tasks.
    
    You have access to the following capabilities:
    
    1. File System Operations: 
        - List directories, read files, change directories
        - Enhanced file search capabilities:
         * search_files: Search for files in a directory
         * find_file: Find a specific file by name
         * find_in_parent_directories: Search in current and parent directories
         * search_project_directories: Comprehensive project-wide search

    2. Code Analysis: Analyze Python files for bugs and issues using pylint
    3. Project Analysis: Analyze the structure and organization of Python projects
    4. Code Generation and Execution: Write code to files and execute Python code
    5. Code Comparison and Diff: Compare files or content and display differences with side-by-side highlighting
    6. Context Management: Maintain conversation context even for long sessions
    7. Editor Integration: Edit the file currently open in the editor with the edit_current_file function
    
    When searching for files or directories:
    - If not found in the current directory, try parent directories
    - Use search_project_directories for a comprehensive search
    - For recursive searches, make sure to explicitly set recursive=True
    
    IMPORTANT - ALWAYS USE ONE OF THESE TWO METHODS WHEN SUGGESTING CODE CHANGES:
    
    1. For direct file modifications, use the edit_current_file() tool function:
        ```python
        await edit_current_file(content="complete updated file content goes here", show_diff=True)
        ```
        This will automatically show a diff view to the user before applying changes.
    
    2. For code examples or partial changes, wrap ALL code in triple backticks:
        ```python
        def example_function():
            return "This is an example"
        ```
        The system will automatically detect these code blocks and offer to show them in a diff view.
    
    NEVER simply paste code without using one of these two methods, as the user will not see the diff view.
    
    You can also delegate tasks to specialized agents when needed:
    - Code Generator: For writing Python code
    - Code Analyzer: For in-depth code analysis
    - Project Analyzer: For analyzing project structure
    - Data Science Code Generator: For generating data science code
    - Web Development Code Generator: For generating web application code
    {history_context}
    Current working directory: {ctx.context.current_dir}
    Current session ID: {ctx.context.session_id}
    Last operation: {ctx.context.last_operation or "None"}
    Recently accessed files: {accessed_files}
    Recent commands: {executed_commands}
    
    When helping with coding tasks:
    1. Be specific and thorough in your explanations
    2. Provide code examples when relevant
    3. Suggest best practices and improvements
    4. Explain your reasoning
    5. Be aware of the limitations of the tools
    6. ALWAYS use edit_current_file() when suggesting changes to the file currently open in the editor
    7. ALWAYS show a diff view for the user to review changes unless explicitly asked not to
    8. When suggesting code changes, first explain the changes, then show the diff using one of the two methods above
    
    You must return your response as a structured output with:
    - Python code always in triple backticks ```python ...```
    - Always output in Markdown format
    - Your response to the user query
    - A list of files accessed during processing
    - A list of commands executed during processing
    """
# Main Terminal Agent
terminal_agent = Agent[AgentContext](
    name="Terminal Agent",
    instructions=terminal_agent_instructions,
    model="gpt-5",
    output_type=TerminalAgentOutput,
    input_guardrails=[security_guardrail],  # Using our updated security guardrail
    tools=[
        list_directory,
        read_file,
        search_files,
        find_file,  # Basic file finder
        find_in_parent_directories,  # Find in parent directories
        search_project_directories,  # Comprehensive project search
        change_directory,
        analyze_python_file,
        compare_files,
        git_status,
        git_commit,
        write_to_file,
        edit_current_file,  # Edit the file currently open in the editor
        execute_python,
        summarize_context,
        # Add specialized agents as tools
        code_generation_agent.as_tool(
            tool_name="generate_code",
            tool_description="Generate Python code based on a detailed description. Returns code and explanation."
        ),
        data_science_code_generator.as_tool(
            tool_name="generate_data_science_code",
            tool_description="Generate Python code for data science tasks (pandas, numpy, scikit-learn, matplotlib)."
        ),
        web_code_generator.as_tool(
            tool_name="generate_web_code",
            tool_description="Generate Python code for web applications (Flask, Django, FastAPI)."
        ),
        code_analysis_agent.as_tool(
            tool_name="analyze_code",
            tool_description="Analyze Python code for issues and improvements. Returns issues, improvements, and summary."
        ),
        project_analysis_agent.as_tool(
            tool_name="analyze_project",
            tool_description="Analyze a Python project's structure and dependencies. Returns structure, dependencies, and recommendations."
        )
    ],
    handoffs=[
        handoff(
            code_generation_agent, 
            tool_name_override="handoff_to_code_generator",
            tool_description_override="Hand off the conversation to the Code Generator agent for in-depth code writing."
        ),
        handoff(
            data_science_code_generator,
            tool_name_override="handoff_to_data_science_generator",
            tool_description_override="Hand off the conversation to the Data Science Code Generator for specialized data science coding."
        ),
        handoff(
            web_code_generator,
            tool_name_override="handoff_to_web_generator",
            tool_description_override="Hand off the conversation to the Web Development Code Generator for specialized web application coding."
        ),
        handoff(
            code_analysis_agent,
            tool_name_override="handoff_to_code_analyzer", 
            tool_description_override="Hand off the conversation to the Code Analyzer agent for comprehensive code analysis."
        ),
        handoff(
            project_analysis_agent,
            tool_name_override="handoff_to_project_analyzer",
            tool_description_override="Hand off the conversation to the Project Analyzer agent for detailed project structure analysis."
        )
    ]
)

# Function to run a query through the agent system
async def run_agent_query(
    query: str,
    context: AgentContext,
    stream_callback = None,
    timeout: int = 120  # Add timeout parameter with default of 120 seconds
) -> Dict[str, Any]:
    """
    Run a query through the agent system
    
    Args:
        query: The user's query string
        context: The agent context
        stream_callback: Optional callback function for streaming responses
        timeout: Maximum time in seconds to wait for API response (default: 120)
        
    Returns:
        Dictionary with the agent's response
    """
    try:
        # Log the query
        logger.info(f"Processing agent query: {query}")
        
        # Validate context
        if not context or not hasattr(context, 'current_dir') or not context.current_dir:
            logger.error("Invalid agent context or missing current_dir")
            return {
                "error": "Agent context is invalid or missing current directory information.",
                "response": "I couldn't process that request because of an issue with the agent context."
            }
            
        # Validate the current directory exists
        if not os.path.exists(context.current_dir):
            logger.error(f"Current directory in context doesn't exist: {context.current_dir}")
            return {
                "error": f"Current directory doesn't exist: {context.current_dir}",
                "response": "I couldn't process that request because the working directory doesn't exist."
            }
            
        # Check if token count is close to limit and trigger summarization if needed
        # We're using 80% of max_tokens as a threshold to trigger summarization proactively
        # before processing a new query
        summarization_threshold = int(context.max_tokens * 0.8)
        if context.token_count >= summarization_threshold:
            logger.info(f"Token count ({context.token_count}) exceeds threshold ({summarization_threshold}), summarizing before processing query")
            
            # Create a wrapper for the context
            ctx_wrapper = RunContextWrapper(context=context)
            
            # Call summarize_context function
            await summarize_context(ctx_wrapper)
            
            logger.info(f"Context summarized before processing query, new token count: {context.token_count}")
            
        # Add the query to token count (approximate)
        query_tokens = len(query.split())
        context.update_token_count(query_tokens)
        logger.info(f"Added {query_tokens} tokens for query, total: {context.token_count}")
        
        # Set up run config with timeout
        run_config = RunConfig(
            model_settings=ModelSettings(),
            trace_metadata={
                "user_id": "terminator_user",
                "session_type": "streaming" if stream_callback else "standard",
            },
            trace_include_sensitive_data=True,
            workflow_name="Terminator Agent Session",
            group_id=context.session_id,
        )
        
        if stream_callback:
            # Run with streaming
            try:
                result = Runner.run_streamed(
                    starting_agent=terminal_agent,
                    input=query,
                    context=context,
                    run_config=run_config
                )
                
                # Process streaming events if callback provided
                async for event in result.stream_events():
                    if stream_callback and callable(stream_callback):
                        await stream_callback(event)
                        
                # Return the final result
                final = getattr(result, 'final_output', None)
                if final is None:
                    logger.error("No final_output from streaming agent query")
                    return {
                        "error": "No response from agent",
                        "response": "I couldn't process that request. No response was generated."
                    }
                # Coerce final output into a string response and optional metadata
                response_text = getattr(final, 'response', None)
                if response_text is None:
                    response_text = str(final)
                files_accessed = getattr(final, 'files_accessed', []) or []
                commands_executed = getattr(final, 'commands_executed', []) or []
                logger.info("Successfully completed streaming agent query")
                return {
                    "response": response_text,
                    "files_accessed": files_accessed,
                    "commands_executed": commands_executed,
                }
            except Exception as stream_error:
                logger.error(f"Error in streaming agent query: {str(stream_error)}", exc_info=True)
                return {
                    "error": f"Streaming error: {str(stream_error)}",
                    "response": f"I encountered an error while processing your request: {str(stream_error)}"
                }
                    
        else:
            # Run without streaming
            try:
                result = await Runner.run(
                    starting_agent=terminal_agent,
                    input=query,
                    context=context,
                    run_config=run_config
                )
                
                # Return the result
                final = getattr(result, 'final_output', None)
                if final is not None:
                    response_text = getattr(final, 'response', None)
                    if response_text is None:
                        response_text = str(final)
                    files_accessed = getattr(final, 'files_accessed', []) or []
                    commands_executed = getattr(final, 'commands_executed', []) or []
                    logger.info("Successfully completed agent query")
                    return {
                        "response": response_text,
                        "files_accessed": files_accessed,
                        "commands_executed": commands_executed,
                    }
                else:
                    logger.error("No response from agent query")
                    return {
                        "error": "No response from agent",
                        "response": "I couldn't process that request. No response was generated."
                    }
            except openai.APITimeoutError as timeout_error:
                # Specific handling for timeout errors
                logger.error(f"API timeout error in agent query: {str(timeout_error)}")
                return {
                    "error": f"The request timed out after {timeout} seconds.",
                    "response": "I couldn't complete this request because it took too long. Please try again with a simpler query or check your network connection."
                }
            except Exception as run_error:
                logger.error(f"Error in agent query: {str(run_error)}", exc_info=True)
                return {
                    "error": f"Run error: {str(run_error)}",
                    "response": f"I encountered an error while processing your request: {str(run_error)}"
                }
                
    except openai.APITimeoutError as e:
        # Catch timeout errors at the outer level
        logger.error(f"API timeout error in agent query: {str(e)}")
        return {
            "error": f"The request timed out after {timeout} seconds.",
            "response": "I couldn't complete this request because it took too long. Please try again with a simpler query or check your network connection."
        }
    except InputGuardrailTripwireTriggered as guard_error:
        # Handle security guardrail trigger
        try:
            if hasattr(guard_error.guardrail_result, 'output_info'):
                security_check = guard_error.guardrail_result.output_info
                risk_type = getattr(security_check, 'risk_type', 'Potential security risk')
                reasoning = getattr(security_check, 'reasoning', 'Security guardrail triggered')
            else:
                risk_type = "Potential security risk"
                reasoning = "Your request triggered a security guardrail"
                
            logger.warning(f"Security guardrail triggered: {risk_type} - {reasoning}")
            return {
                "error": f"Security Warning: {risk_type}",
                "details": reasoning,
                "response": f"I can't process that request because it was flagged as a potential security risk: {risk_type}. {reasoning}"
            }
        except Exception as e:
            logger.error(f"Error processing security guardrail result: {str(e)}", exc_info=True)
            return {
                "error": "Security Warning: Request blocked by security guardrail",
                "response": "I can't process that request because it was flagged by my security systems."
            }
            
    except Exception as e:
        logger.error(f"Exception running agent query: {str(e)}", exc_info=True)
        return {
            "error": f"Error: {str(e)}",
            "response": f"I encountered an unexpected error while processing your request: {str(e)}"
        }

# Initialize the agent system
def initialize_agent_system():
    """Initialize the agent system with API keys and logging"""
    try:
        # Set up logging if not already configured
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            # Try to add a file handler if one not present
            has_agent_file = any(
                isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '').endswith('terminator_agent.log')
                for h in logger.handlers
            )
            if not has_agent_file:
                file_handler = logging.FileHandler("terminator_agent.log")
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("openai").setLevel(logging.WARNING)
            logging.getLogger("openai._base_client").setLevel(logging.WARNING)
            logging.getLogger("httpcore").setLevel(logging.WARNING)
        
        # Check for API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY not set in environment variables")
            return False
            
        # Set the API key for both OpenAI and agents
        from openai import OpenAI, AsyncOpenAI
        
        # Configure with higher timeout and better retry settings
        OpenAI.api_key = api_key
        set_default_openai_key(api_key)
        
        # Create a custom client with increased timeouts
        http_client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),  # Increase timeout to 60 seconds
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        async_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),  # Increase timeout to 60 seconds
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        
        # Use custom client for both sync and async OpenAI clients
        client = OpenAI(api_key=api_key, http_client=http_client)
        async_client = AsyncOpenAI(api_key=api_key, http_client=async_http_client)
        
        # Make these clients available globally
        set_openai_clients(client, async_client)
        
        return True
        
    except Exception as e:
        logger.error(f"Error initializing agent system: {str(e)}", exc_info=True)
        return False

def set_logging_level(level_name: str) -> bool:
        """
        Set the logging level for the terminator_agents logger
        
        Args:
            level_name: Name of logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Map string names to logging levels
            levels = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            
            if level_name.upper() not in levels:
                logger.error(f"Unknown logging level: {level_name}")
                return False
                
            level = levels[level_name.upper()]
            logger.setLevel(level)
            
            # Also set for file handler if it exists
            for handler in logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    handler.setLevel(level)
                    
            return True
        except Exception as e:
            print(f"Error setting logging level: {str(e)}")
            return False
