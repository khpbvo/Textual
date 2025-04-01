"""
React Framework Module - Provides React-specific tooling
"""

import os
import sys
import json
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional, Set, Tuple, Callable

from .base import FrameworkProvider

logger = logging.getLogger(__name__)

class ReactFrameworkProvider(FrameworkProvider):
    """
    Provides React-specific tooling for Terminator IDE
    
    This class provides React-specific commands, project information,
    and code generation capabilities.
    """
    
    @property
    def framework_name(self) -> str:
        """Get the name of the framework"""
        return "React"
    
    @property
    def framework_icon(self) -> str:
        """Get an icon representation for React"""
        return "⚛️"  # React icon (atom symbol)
    
    @property
    def framework_commands(self) -> List[Dict[str, Any]]:
        """Get React-specific commands"""
        return [
            {
                "id": "start",
                "label": "Start Dev Server",
                "description": "Start the React development server",
                "action": "start_dev_server"
            },
            {
                "id": "build",
                "label": "Build",
                "description": "Build the React application",
                "action": "build"
            },
            {
                "id": "test",
                "label": "Run Tests",
                "description": "Run React tests",
                "action": "run_tests"
            },
            {
                "id": "lint",
                "label": "Lint",
                "description": "Lint the React code",
                "action": "lint"
            },
            {
                "id": "new-component",
                "label": "New Component",
                "description": "Create a new React component",
                "action": "new_component"
            },
            {
                "id": "analyze",
                "label": "Analyze Bundle",
                "description": "Analyze the bundle size",
                "action": "analyze_bundle"
            },
            {
                "id": "storybook",
                "label": "Storybook",
                "description": "Start Storybook",
                "action": "storybook"
            },
            {
                "id": "eject",
                "label": "Eject",
                "description": "Eject from Create React App",
                "action": "eject"
            }
        ]
    
    async def get_project_info(self) -> Dict[str, Any]:
        """Get React project information"""
        info = {}
        
        try:
            # Look for package.json
            package_json_path = os.path.join(self.workspace_path, "package.json")
            
            if os.path.exists(package_json_path):
                with open(package_json_path, "r") as f:
                    package_data = json.load(f)
                    
                # Get React version
                dependencies = package_data.get("dependencies", {})
                dev_dependencies = package_data.get("devDependencies", {})
                
                if "react" in dependencies:
                    info["React Version"] = dependencies["react"]
                    
                # Check for common React frameworks/libraries
                frameworks = []
                
                # Next.js
                if "next" in dependencies or "next" in dev_dependencies:
                    frameworks.append("Next.js")
                    
                # Create React App
                if ("react-scripts" in dependencies or "react-scripts" in dev_dependencies):
                    frameworks.append("Create React App")
                    
                # Gatsby
                if "gatsby" in dependencies or "gatsby" in dev_dependencies:
                    frameworks.append("Gatsby")
                    
                # Remix
                if "@remix-run/react" in dependencies or "@remix-run/react" in dev_dependencies:
                    frameworks.append("Remix")
                
                if frameworks:
                    info["Frameworks"] = ", ".join(frameworks)
                    
                # State management
                state_libs = []
                
                if "redux" in dependencies or "redux" in dev_dependencies:
                    state_libs.append("Redux")
                    
                if "mobx" in dependencies or "mobx" in dev_dependencies:
                    state_libs.append("MobX")
                    
                if "recoil" in dependencies or "recoil" in dev_dependencies:
                    state_libs.append("Recoil")
                    
                if "jotai" in dependencies or "jotai" in dev_dependencies:
                    state_libs.append("Jotai")
                    
                if "zustand" in dependencies or "zustand" in dev_dependencies:
                    state_libs.append("Zustand")
                    
                if state_libs:
                    info["State Management"] = ", ".join(state_libs)
                    
                # UI libraries
                ui_libs = []
                
                if "material-ui" in dependencies or "@mui/material" in dependencies:
                    ui_libs.append("Material UI")
                    
                if "antd" in dependencies:
                    ui_libs.append("Ant Design")
                    
                if "chakra-ui" in dependencies or "@chakra-ui/react" in dependencies:
                    ui_libs.append("Chakra UI")
                    
                if "tailwindcss" in dependencies or "tailwindcss" in dev_dependencies:
                    ui_libs.append("Tailwind CSS")
                    
                if "styled-components" in dependencies:
                    ui_libs.append("styled-components")
                    
                if "emotion" in dependencies or "@emotion/react" in dependencies:
                    ui_libs.append("Emotion")
                    
                if ui_libs:
                    info["UI Libraries"] = ", ".join(ui_libs)
                    
                # Testing
                test_libs = []
                
                if "jest" in dependencies or "jest" in dev_dependencies:
                    test_libs.append("Jest")
                    
                if "testing-library" in json.dumps(dependencies) or "testing-library" in json.dumps(dev_dependencies):
                    test_libs.append("Testing Library")
                    
                if "cypress" in dependencies or "cypress" in dev_dependencies:
                    test_libs.append("Cypress")
                    
                if test_libs:
                    info["Testing"] = ", ".join(test_libs)
                    
                # Scripts
                scripts = package_data.get("scripts", {})
                if scripts:
                    available_scripts = list(scripts.keys())
                    info["Available Scripts"] = ", ".join(available_scripts[:5])
                    if len(available_scripts) > 5:
                        info["Available Scripts"] += f" (and {len(available_scripts) - 5} more)"
                
        except Exception as e:
            logger.error(f"Error getting React project info: {str(e)}", exc_info=True)
            info["Error"] = str(e)
            
        return info
    
    async def run_command(self, command_id: str) -> str:
        """Run a React-specific command"""
        # Check for package.json
        package_json_path = os.path.join(self.workspace_path, "package.json")
        
        if not os.path.exists(package_json_path):
            return "Error: package.json not found. Is this a React project?"
            
        # Call the appropriate method based on command_id
        command_map = {
            "start": self._start_dev_server,
            "build": self._build,
            "test": self._run_tests,
            "lint": self._lint,
            "new-component": self._new_component,
            "analyze": self._analyze_bundle,
            "storybook": self._storybook,
            "eject": self._eject
        }
        
        if command_id in command_map:
            return await command_map[command_id]()
        else:
            return f"Error: Unknown command '{command_id}'"
    
    async def _start_dev_server(self) -> str:
        """Start the React development server"""
        # Check if we should use npm or yarn
        package_manager = await self._get_package_manager()
        
        # Get the start script from package.json
        with open(os.path.join(self.workspace_path, "package.json"), "r") as f:
            package_data = json.load(f)
            
        scripts = package_data.get("scripts", {})
        
        # Determine the start command
        start_script = None
        
        if "start" in scripts:
            start_script = "start"
        elif "dev" in scripts:
            start_script = "dev"
            
        if not start_script:
            return "Error: No start script found in package.json"
            
        # Build the command
        if package_manager == "yarn":
            cmd = ["yarn", start_script]
        else:
            cmd = ["npm", "run", start_script]
            
        if self.output_callback:
            # Start the server in a new process and capture output incrementally
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            # Initial message
            initial_output = f"Starting React development server with {package_manager}...\n"
            if self.output_callback:
                self.output_callback(initial_output)
                
            # Read stdout incrementally
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                    
                line_str = line.decode("utf-8")
                if self.output_callback:
                    self.output_callback(initial_output + line_str)
                    initial_output = ""  # Only include it once
            
            return "React development server stopped"
        else:
            # Run in blocking mode and return full output
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workspace_path
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    return stdout.decode("utf-8")
                else:
                    return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                    
            except Exception as e:
                logger.error(f"Error starting React development server: {str(e)}", exc_info=True)
                return f"Error: {str(e)}"
    
    async def _build(self) -> str:
        """Build the React application"""
        # Check if we should use npm or yarn
        package_manager = await self._get_package_manager()
        
        # Get the build script from package.json
        with open(os.path.join(self.workspace_path, "package.json"), "r") as f:
            package_data = json.load(f)
            
        scripts = package_data.get("scripts", {})
        
        if "build" not in scripts:
            return "Error: No build script found in package.json"
            
        # Build the command
        if package_manager == "yarn":
            cmd = ["yarn", "build"]
        else:
            cmd = ["npm", "run", "build"]
            
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Check for build directory
                build_dirs = ["build", "dist", "out", ".next", "public/build"]
                build_dir = None
                
                for dir_name in build_dirs:
                    if os.path.exists(os.path.join(self.workspace_path, dir_name)):
                        build_dir = dir_name
                        break
                        
                result = stdout.decode("utf-8")
                
                if build_dir:
                    result += f"\n\nBuild output directory: {build_dir}/"
                    
                return result
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error building React application: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _run_tests(self) -> str:
        """Run React tests"""
        # Check if we should use npm or yarn
        package_manager = await self._get_package_manager()
        
        # Get the test script from package.json
        with open(os.path.join(self.workspace_path, "package.json"), "r") as f:
            package_data = json.load(f)
            
        scripts = package_data.get("scripts", {})
        
        if "test" not in scripts:
            return "Error: No test script found in package.json"
            
        # Build the command
        if package_manager == "yarn":
            cmd = ["yarn", "test"]
        else:
            cmd = ["npm", "run", "test", "--", "--watchAll=false"]
            
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error running React tests: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _lint(self) -> str:
        """Lint the React code"""
        # Check if we should use npm or yarn
        package_manager = await self._get_package_manager()
        
        # Get the lint script from package.json
        with open(os.path.join(self.workspace_path, "package.json"), "r") as f:
            package_data = json.load(f)
            
        scripts = package_data.get("scripts", {})
        
        lint_script = None
        
        if "lint" in scripts:
            lint_script = "lint"
        elif "eslint" in scripts:
            lint_script = "eslint"
            
        if not lint_script:
            # Check if eslint is installed
            eslint_path = os.path.join(self.workspace_path, "node_modules", ".bin", "eslint")
            
            if os.path.exists(eslint_path):
                # Run eslint directly
                cmd = [eslint_path, "src", "--ext", ".js,.jsx,.ts,.tsx"]
            else:
                return "Error: No lint script found and ESLint is not installed"
        else:
            # Build the command
            if package_manager == "yarn":
                cmd = ["yarn", lint_script]
            else:
                cmd = ["npm", "run", lint_script]
                
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8") or "Linting passed! No issues found."
            else:
                return f"Linting found issues:\n{stderr.decode('utf-8')}" if stderr else stdout.decode("utf-8")
                
        except Exception as e:
            logger.error(f"Error linting React code: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _new_component(self) -> str:
        """Create a new React component"""
        # In a real implementation, this would prompt for component name and type
        component_template = """import React from 'react';
import './NewComponent.css';

interface NewComponentProps {
  title: string;
  description?: string;
}

const NewComponent: React.FC<NewComponentProps> = ({ title, description }) => {
  return (
    <div className="new-component">
      <h2>{title}</h2>
      {description && <p>{description}</p>}
    </div>
  );
};

export default NewComponent;
"""

        css_template = """.new-component {
  padding: 1rem;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.new-component h2 {
  margin-top: 0;
  color: #333;
}

.new-component p {
  color: #666;
}
"""

        test_template = """import React from 'react';
import { render, screen } from '@testing-library/react';
import NewComponent from './NewComponent';

describe('NewComponent', () => {
  it('renders the title', () => {
    render(<NewComponent title="Test Title" />);
    const titleElement = screen.getByText(/Test Title/i);
    expect(titleElement).toBeInTheDocument();
  });

  it('renders the description when provided', () => {
    render(<NewComponent title="Test Title" description="Test Description" />);
    const descElement = screen.getByText(/Test Description/i);
    expect(descElement).toBeInTheDocument();
  });

  it('does not render the description when not provided', () => {
    render(<NewComponent title="Test Title" />);
    const descElement = screen.queryByText(/Test Description/i);
    expect(descElement).not.toBeInTheDocument();
  });
});
"""

        return f"""To create a new React component, create the following files:

1. src/components/NewComponent/NewComponent.tsx
```tsx
{component_template}
```

2. src/components/NewComponent/NewComponent.css
```css
{css_template}
```

3. src/components/NewComponent/NewComponent.test.tsx
```tsx
{test_template}
```

4. src/components/NewComponent/index.ts
```ts
export { default } from './NewComponent';
```

Then you can use the component like this:
```tsx
import NewComponent from './components/NewComponent';

function App() {
  return (
    <div className="App">
      <NewComponent title="Hello World" description="This is a new component" />
    </div>
  );
}
```"""
    
    async def _analyze_bundle(self) -> str:
        """Analyze the bundle size"""
        # Check if we should use npm or yarn
        package_manager = await self._get_package_manager()
        
        # Check if source-map-explorer is installed
        with open(os.path.join(self.workspace_path, "package.json"), "r") as f:
            package_data = json.load(f)
            
        dependencies = package_data.get("dependencies", {})
        dev_dependencies = package_data.get("devDependencies", {})
        
        has_source_map_explorer = "source-map-explorer" in dependencies or "source-map-explorer" in dev_dependencies
        
        if not has_source_map_explorer:
            return """Error: source-map-explorer not found in dependencies.
            
Install it with:
npm install --save-dev source-map-explorer

Then add to package.json scripts:
"analyze": "source-map-explorer 'build/static/js/*.js'"

Or run the build with sourcemaps enabled:
GENERATE_SOURCEMAP=true npm run build
"""
            
        # Build first
        build_result = await self._build()
        
        # Now analyze the bundle
        if package_manager == "yarn":
            cmd = ["yarn", "source-map-explorer", "build/static/js/*.js"]
        else:
            cmd = ["npx", "source-map-explorer", "build/static/js/*.js"]
            
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8")
            else:
                return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                
        except Exception as e:
            logger.error(f"Error analyzing bundle: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def _storybook(self) -> str:
        """Start Storybook"""
        # Check if we should use npm or yarn
        package_manager = await self._get_package_manager()
        
        # Check if Storybook is installed
        with open(os.path.join(self.workspace_path, "package.json"), "r") as f:
            package_data = json.load(f)
            
        scripts = package_data.get("scripts", {})
        
        storybook_script = None
        
        if "storybook" in scripts:
            storybook_script = "storybook"
        elif "start-storybook" in scripts:
            storybook_script = "start-storybook"
            
        if not storybook_script:
            return """Error: Storybook not found in scripts.
            
Install it with:
npx sb init
"""
            
        # Build the command
        if package_manager == "yarn":
            cmd = ["yarn", storybook_script]
        else:
            cmd = ["npm", "run", storybook_script]
            
        if self.output_callback:
            # Start Storybook in a new process and capture output incrementally
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            
            # Initial message
            initial_output = f"Starting Storybook with {package_manager}...\n"
            if self.output_callback:
                self.output_callback(initial_output)
                
            # Read stdout incrementally
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                    
                line_str = line.decode("utf-8")
                if self.output_callback:
                    self.output_callback(initial_output + line_str)
                    initial_output = ""  # Only include it once
            
            return "Storybook stopped"
        else:
            # Run in blocking mode and return full output
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workspace_path
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    return stdout.decode("utf-8")
                else:
                    return f"Error ({process.returncode}):\n{stderr.decode('utf-8')}"
                    
            except Exception as e:
                logger.error(f"Error starting Storybook: {str(e)}", exc_info=True)
                return f"Error: {str(e)}"
    
    async def _eject(self) -> str:
        """Eject from Create React App"""
        # Check if we should use npm or yarn
        package_manager = await self._get_package_manager()
        
        # Check if this is a Create React App project
        with open(os.path.join(self.workspace_path, "package.json"), "r") as f:
            package_data = json.load(f)
            
        dependencies = package_data.get("dependencies", {})
        dev_dependencies = package_data.get("devDependencies", {})
        
        is_cra = "react-scripts" in dependencies or "react-scripts" in dev_dependencies
        
        if not is_cra:
            return "Error: This doesn't appear to be a Create React App project (react-scripts not found)"
            
        return """Warning: Ejecting is a permanent action and cannot be undone!
        
Ejecting gives you full control over the webpack configuration, babel, etc., but you'll have to maintain these yourself in the future.

It's recommended to use alternatives like craco (Create React App Configuration Override) before ejecting.

If you still want to eject, run this command in your terminal:
npm run eject

or

yarn eject"""
    
    async def _get_package_manager(self) -> str:
        """Determine whether to use npm or yarn"""
        # Check for yarn.lock
        if os.path.exists(os.path.join(self.workspace_path, "yarn.lock")):
            return "yarn"
        else:
            return "npm"