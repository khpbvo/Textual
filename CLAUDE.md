# Textual Agents Development Guide

## Build/Run Commands
- Run application: `python3 TerminatorV1_main.py`
- Run tests: `pytest`
- Lint code: `black . && pylint TerminatorV1_*.py`
- Run single test: `pytest -xvs test_file.py::test_function`

## Code Style
- Follow PEP 8 guidelines
- Use docstrings for all functions, classes, and modules
- Maximum line length: 100 characters
- Use type hints for all function parameters and return values
- Use Pydantic v2 syntax without default values (define in function body)
- Prefer async functions to avoid blocking the main event loop

## Project Structure
- Keep new functionality in modules outside TerminatorV1_main.py
- Implement agent tools in TerminatorV1_tools.py
- Agent definitions in TerminatorV1_agents.py
- Use modular structure (in the `terminator/` package) for new components:
  - `terminator/ui/`: User interface components (panels, diff view)
  - `terminator/utils/`: Utility functions (git management)
  - `terminator/agents/`: Agent functionality (context management)
- Use consistent error handling with try/except blocks

## Development Guidelines
- All OpenAI integrations must follow openaiAgentSDK.md reference
- Use latest package versions (no pinned dependencies)
- Create automated context summarization when token limit is reached
- Implement proper error handling for all operations
- Add docstrings for all public functions and classes

## Tasks Completed
- ✅ Task #5: Fixed file explorer functionality
- ✅ Task #6: Improved agent context summarization
- ✅ Task #8: Implemented adjustable panel widths
- ✅ Task #9: Implemented diff view for code edits
- ✅ Task #10: Fixed Git commit popup escape functionality
- ✅ Task #11: Modularized new functionality into separate packages
- ✅ Task #12: Speed up application/API responses

## Next Steps
- All tasks in FOR CLAUDE.md have been completed
- Implemented features from FUTURE-FEATURES.md:
  - ✅ Language Server Protocol integration
  - ✅ Framework-specific tooling
- Continue with other features in FUTURE-FEATURES.md:
  - Team knowledge base
  - Performance profiling