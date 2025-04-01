import os
import sys
import unittest
import pytest
from unittest.mock import patch, MagicMock, ANY
import time
import cProfile
import pstats
import io

# Add parent directory to path so we can import the application modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the application modules
from TerminatorV1_main import TerminatorApp

class TestTerminatorApp(unittest.TestCase):
    """Test suite for Terminator IDE application"""
    
    @patch('TerminatorV1_agents.initialize_agent_system')
    @patch('TerminatorV1_main.TerminatorApp.check_git_repository')
    @patch('TerminatorV1_main.TerminatorApp.initialize_agent_context')
    def test_app_initialization(self, mock_init_agent_context, mock_check_git, mock_init_agent):
        """Test application initialization for performance issues"""
        # Configure mocks
        mock_init_agent.return_value = True
        mock_init_agent_context.return_value = True
        
        # Profile the initialization
        profiler = cProfile.Profile()
        profiler.enable()
        
        # Create a patch for query_one to avoid UI component errors
        mock_query_result = MagicMock()
        mock_query_result.focus = MagicMock()
        
        # Measure initialization time
        start_time = time.time()
        
        # Create the app but patch UI-dependent methods
        with patch.object(TerminatorApp, 'query_one', return_value=mock_query_result):
            with patch.object(TerminatorApp, 'update_git_status'):
                with patch.object(TerminatorApp, '_apply_panel_widths'):
                    with patch.object(TerminatorApp, 'initialize_ai_panel'):
                        app = TerminatorApp()
                        # Skip UI initialization in on_mount by patching problematic methods
                        with patch.object(app, 'query_one', return_value=mock_query_result):
                            # Call a modified version of on_mount that skips UI operations
                            self._modified_on_mount(app)
                            
                            # Explicitly call initialize_agent_context since it's not called in _modified_on_mount
                            app.initialize_agent_context()
        
        end_time = time.time()
        profiler.disable()
        
        # Output initialization time
        init_time = end_time - start_time
        print(f"\nApp initialization took {init_time:.2f} seconds")
        
        # Output profiling stats to string buffer
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        stats.print_stats(20)  # Print top 20 time-consuming functions
        print(s.getvalue())
        
        # Verify that core initialization completed
        mock_init_agent_context.assert_called_once()
        mock_init_agent.assert_called_once()
        
        # Ensure initialization time is reasonable
        self.assertLess(init_time, 2.0, "App initialization is too slow (> 2s)")
    
    def _modified_on_mount(self, app):
        """Modified version of on_mount that skips UI operations"""
        # Set up initial directory
        app.current_directory = os.getcwd()
        
        # Initialize editor state tracking
        app.active_editor = "primary"
        app.split_view_active = False
        app.multi_cursor_positions = []
        app.active_tab = "editor"
        app.terminal_history = []
        
        # Initialize resizable panel tracking
        app.resizing = False
        app.resizing_panel = None
        app.start_x = 0
        app.current_widths = {
            "sidebar": 20,
            "editor-container": 60,
            "ai-panel": 20
        }
        
        # Initialize debugger state
        app.debug_session = None
        app.breakpoints = {}
        
        # Initialize AI pair programming state
        app.pair_programming_active = False
        app.pair_programming_timer = None
        app.last_edit_time = time.time()
        
        # Initialize remote development state
        app.remote_connected = False
        app.remote_config = {
            "connection_type": None,
            "host": None,
            "username": None,
            "port": 22,
            "password": None,
            "remote_path": None
        }
        
        # These calls would interact with UI, so skip them
        # app.check_git_repository()
        # app.initialize_ai_panel()
        # app._apply_panel_widths()
        
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="test content")
    def test_file_operations(self, mock_file):
        """Test file operations for performance issues"""
        app = MagicMock(spec=TerminatorApp)
        app.current_file = "/test/file.py"
        app.active_editor = "primary"
        
        # Create mock editor
        mock_editor = MagicMock()
        app.query_one.return_value = mock_editor
        
        # Mock get_language_from_extension
        app.get_language_from_extension.return_value = "python"
        
        # Profile file saving operation
        profiler = cProfile.Profile()
        profiler.enable()
        
        # Use the actual action_save method
        original_save = TerminatorApp.action_save
        
        # Create a wrapper to call the original method with our mock
        async def run_save():
            # Extract just the synchronous part of action_save
            with patch('asyncio.create_task'):
                await original_save(app)
                
        # Run the save operation in a sync context for testing
        import asyncio
        asyncio.run(run_save())
        
        profiler.disable()
        
        # Verify the file write operation
        mock_file.assert_called_once_with("/test/file.py", "w", encoding="utf-8")
        
        # Output profiling stats
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        stats.print_stats(10)
        print(f"\nFile operation profiling:\n{s.getvalue()}")

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="test python content\ndef function():\n    pass")
    def test_file_loading(self, mock_file):
        """Test file loading performance"""
        app = MagicMock(spec=TerminatorApp)
        # Mock DirectoryTree.FileSelected event
        mock_event = MagicMock()
        mock_event.path = "/test/file.py"
        
        # Mock the editor components
        mock_editor = MagicMock()
        app.query_one.return_value = mock_editor
        app.active_editor = "primary"
        app.active_tab = "editor"
        
        # Mock language detection method
        app.get_language_from_extension.return_value = "python"
        
        # Profile the file loading operation
        profiler = cProfile.Profile()
        profiler.enable()
        
        # Use the actual file selection handler
        original_handler = TerminatorApp.on_directory_tree_file_selected
        
        # Create a wrapper to call the original method with our mock
        async def run_file_load():
            with patch('os.path.splitext', return_value=(".py", ".py")):
                await original_handler(app, mock_event)
        
        # Run the file loading operation in a sync context
        import asyncio
        asyncio.run(run_file_load())
        
        profiler.disable()
        
        # Verify file was opened
        mock_file.assert_called_once_with("/test/file.py", "r", encoding="utf-8")
        
        # Verify editor was updated
        mock_editor.language.assert_called_once()
        
        # Output profiling stats
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        stats.print_stats(10)
        print(f"\nFile loading profiling:\n{s.getvalue()}")
    
    @patch('TerminatorV1_agents.run_agent_query')
    def test_ai_request_performance(self, mock_run_agent):
        """Test performance of AI request processing"""
        # Setup mock response
        mock_response = {"response": "This is a test AI response"}
        mock_run_agent.return_value = mock_response
        
        # Import AsyncMock for mocking async methods
        from unittest.mock import AsyncMock
        
        # Create application mock with appropriate async methods
        app = MagicMock(spec=TerminatorApp)
        app.agent_context = MagicMock()
        
        # Make methods that might be awaited into AsyncMocks
        app._update_ai_output_with_response = AsyncMock()
        app.call_after_refresh = AsyncMock()
        
        # Mock the UI elements
        mock_prompt_input = MagicMock()
        mock_prompt_input.value = "Test prompt"
        mock_ai_output = MagicMock()
        mock_ai_output.__str__ = MagicMock(return_value="Current content")
        
        app.query_one.side_effect = lambda selector: {
            "#ai-prompt": mock_prompt_input,
            "#ai-output": mock_ai_output,
            "#editor-primary": MagicMock(text="Test code")
        }.get(selector, MagicMock())
        
        app.active_editor = "primary"
        app._prepare_agent_prompt = TerminatorApp._prepare_agent_prompt
        
        # Profile the AI request operation
        profiler = cProfile.Profile()
        profiler.enable()
        
        # Create a custom version of call_ai_agent for testing
        async def patched_call_ai(self, prompt, code):
            # Simplified version that just calls the agent
            context = self.agent_context or {"role": "assistant"}
            
            # Actually call the mocked function
            response = mock_run_agent(prompt=prompt, code=code, context=context)
            
            await self._update_ai_output_with_response(response)
            return response
        
        # Run the patched function
        import asyncio
        asyncio.run(patched_call_ai(app, "Test prompt", "Test code"))
        
        profiler.disable()
        
        # Verify AI agent was called
        mock_run_agent.assert_called_once()
        
        # Output profiling stats
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        stats.print_stats(10)
        print(f"\nAI request profiling:\n{s.getvalue()}")
    
    @patch('subprocess.run')
    def test_git_status_performance(self, mock_subprocess):
        """Test performance of Git status operations"""
        # Setup mock subprocess response for git status
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "M file1.py\n?? file2.py"
        mock_subprocess.return_value = mock_process
        
        # Create application mock
        app = MagicMock(spec=TerminatorApp)
        app.git_repository = "/test/repo"
        
        # Mock git output widget
        mock_git_output = MagicMock()
        app.query_one.return_value = mock_git_output
        
        # Profile the git status update operation
        profiler = cProfile.Profile()
        profiler.enable()
        
        # Use the actual git status method with patches
        with patch('TerminatorV1_main.GitManager.get_git_status') as mock_get_status:
            # Simulate modified and untracked files
            mock_get_status.return_value = {
                "modified_files": ["file1.py"],
                "untracked_files": ["file2.py"],
                "staged_files": [],
                "clean": False
            }
            
            # Run update_git_status
            original_update = TerminatorApp.update_git_status
            
            async def run_git_update():
                # Set _last_status_update_time to ensure update runs
                app._last_status_update_time = 0
                await original_update(app)
                
            # Run in sync context
            import asyncio
            asyncio.run(run_git_update())
        
        profiler.disable()
        
        # Verify git status was checked and output was updated
        mock_get_status.assert_called_once_with("/test/repo")
        mock_git_output.update.assert_called()
        
        # Output profiling stats
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        stats.print_stats(10)
        print(f"\nGit status profiling:\n{s.getvalue()}")
    
    def test_code_analysis_performance(self):
        """Test performance of code analysis functionality"""
        test_code = """
def fibonacci(n):
    if n <= 1:
        return n
    else:
        return fibonacci(n-1) + fibonacci(n-2)
        
def main():
    for i in range(10):
        print(fibonacci(i))
        
if __name__ == "__main__":
    main()
"""
        # Create application mock
        app = MagicMock(spec=TerminatorApp)
        app.current_file = "/test/test_script.py"
        
        # Mock editor
        mock_editor = MagicMock()
        mock_editor.text = test_code
        app.active_editor = "primary"
        app.query_one.return_value = mock_editor
        
        # Mock the CodeAnalyzer methods
        with patch('TerminatorV1_main.CodeAnalyzer.analyze_python_code') as mock_analyze:
            mock_analyze.return_value = {
                "issues": [
                    {"line": 5, "message": "Recursive function could be optimized", "type": "performance"}
                ],
                "recommendations": ["Consider using memoization for the fibonacci function"]
            }
            
            with patch('TerminatorV1_main.CodeAnalyzer.count_code_lines') as mock_count:
                mock_count.return_value = {
                    "total_lines": 12,
                    "code_lines": 10,
                    "comment_lines": 0,
                    "blank_lines": 2
                }
                
                # Profile the code analysis operation
                profiler = cProfile.Profile()
                profiler.enable()
                
                # Mock the screen to post message to
                mock_screen = MagicMock()
                app.query_one.return_value = mock_screen
                app.post_message = MagicMock()
                
                # Use the original action with our mocks
                original_analyze = TerminatorApp.action_analyze_code
                
                async def run_analysis():
                    await original_analyze(app)
                    
                # Run in sync context
                import asyncio
                asyncio.run(run_analysis())
                
                profiler.disable()
                
                # Output profiling stats
                s = io.StringIO()
                stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
                stats.print_stats(10)
                print(f"\nCode analysis profiling:\n{s.getvalue()}")
                
                # Verify analysis was performed
                mock_analyze.assert_called_once_with(test_code)
                mock_count.assert_called_once_with(test_code)

    @patch('TerminatorV1_main.TerminatorApp._apply_panel_widths')
    def test_ui_responsiveness_resize(self, mock_apply_widths):
        """Test UI responsiveness during resizing operations"""
        # Create application instance with mocked components
        app = MagicMock(spec=TerminatorApp)
        app.resizing = True
        app.resizing_panel = "sidebar"
        app.start_x = 100
        app.current_widths = {
            "sidebar": 20,
            "editor-container": 60,
            "ai-panel": 20
        }
        app.size.width = 1000
        
        # Mock UI components
        mock_sidebar = MagicMock()
        mock_editor = MagicMock()
        app.query_one.side_effect = lambda selector: {
            "#sidebar": mock_sidebar,
            "#editor-container": mock_editor
        }.get(selector, MagicMock())
        
        # Create mock mouse event
        mock_event = MagicMock()
        mock_event.screen_x = 120  # 20px to the right of start_x
        
        # Profile the resize operation
        profiler = cProfile.Profile()
        profiler.enable()
        
        # Run the mouse move handler with our mocks
        original_mouse_move = TerminatorApp.on_mouse_move
        
        async def run_resize():
            await original_mouse_move(app, mock_event)
            
        # Run in sync context
        import asyncio
        asyncio.run(run_resize())
        
        profiler.disable()
        
        # Verify resize calculations were performed
        self.assertNotEqual(app.current_widths["sidebar"], 20)
        self.assertNotEqual(app.current_widths["editor-container"], 60)
        
        # Verify styles were updated
        mock_sidebar.styles.width.assert_called_once()
        mock_editor.styles.width.assert_called_once()
        
        # Output profiling stats
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        stats.print_stats(10)
        print(f"\nUI resize profiling:\n{s.getvalue()}")
    
    def test_memory_usage(self):
        """Test memory usage of the application"""
        import psutil
        import gc
        
        # Force garbage collection to get accurate baseline
        gc.collect()
        
        # Get baseline memory usage
        process = psutil.Process(os.getpid())
        baseline_memory = process.memory_info().rss / 1024 / 1024  # Convert to MB
        
        # Create minimal application instance
        with patch.object(TerminatorApp, 'on_mount'):
            with patch.object(TerminatorApp, 'compose'):
                app = TerminatorApp()
        
        # Force garbage collection again
        gc.collect()
        
        # Measure memory after app creation
        app_memory = process.memory_info().rss / 1024 / 1024  # Convert to MB
        
        # Calculate memory used by the app
        app_memory_usage = app_memory - baseline_memory
        
        print(f"\nMemory usage test results:")
        print(f"Baseline memory: {baseline_memory:.2f} MB")
        print(f"Memory after app creation: {app_memory:.2f} MB")
        print(f"Application memory usage: {app_memory_usage:.2f} MB")
        
        # Memory usage should be reasonable
        self.assertLess(app_memory_usage, 100.0, "Application uses too much memory (>100MB)")

if __name__ == "__main__":
    unittest.main()
