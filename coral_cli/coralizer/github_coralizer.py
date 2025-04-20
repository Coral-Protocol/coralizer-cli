import asyncio
import os
import tempfile
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple
import shutil
import time
import re # For parsing agent output

# GitPython for cloning
try:
    import git
except ImportError:
    print("Error: GitPython is not installed. Please run 'pip install GitPython'")
    git = None # Set to None if import fails

# CAMEL AI components
try:
    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType
except ImportError:
    print("Error: camel-ai library not found or incomplete.")
    print("Please ensure camel-ai is installed correctly (e.g., pip install 'camel-ai[web-tools]')")
    ChatAgent = ModelFactory = ModelPlatformType = ModelType = None # Set to None

# Max context size (in characters) to feed to the generator agent
MAX_CODE_CONTEXT_CHARS = 15000 # Example limit, depends on model
MAX_TREE_CHARS = 2000 # Limit for file tree representation

example_output = """
import asyncio
import os
from time import sleep
import sys

from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.toolkits import MCPToolkit
from camel.toolkits.mcp_toolkit import MCPClient
from camel.types import ModelPlatformType, ModelType

# Ensure OPENAI_API_KEY is set
if "OPENAI_API_KEY" not in os.environ:
    print("Error: OPENAI_API_KEY environment variable not set.")
    sys.exit(1)

def get_tools_description():
    return \"\"\"
        You have access to communication tools to interact with other agents.
        
        Before using the tools, you need to register yourself using the register tool. Name yourself with a name that describes your speciality well. Do not be too generic. For example, if you are a search agent, you can name yourself "search_agent".
        
        If there are no other agents, remember to re-list the agents periodically using the list tool.
        
        You should know that the user can't see any messages you send, you are expected to be autonomous and respond to the user only when you have finished working with other agents, using tools specifically for that.
        
        You can emit as many messages as you like before using that tool when you are finished or absolutely need user input. You are on a loop and will see a "user" message every 4 seconds, but it's not really from the user.
        
        Run the wait for mention tool when you are ready to receive a message from another agent. This is the preferred way to wait for messages from other agents.
        
        You'll only see messages from other agents since you last called the wait for mention tool. Remember to call this periodically.
        
        Don't try to guess any numbers or facts, only use reliable sources. If you are unsure, ask other agents for help.
    \"\"\"

def get_user_message():
    return "[automated] continue collaborating with other agents"

async def main():
    # Connect to Coral server
    coral_server = MCPClient("{self.coral_server_url}")
    coral_toolkit = MCPToolkit([coral_server])
    
    # Connect to target MCP server
    target_server = MCPClient("{self.target_mcp_url}")
    target_toolkit = MCPToolkit([target_server])

    async with coral_toolkit.connection() as connected_coral_toolkit:
        async with target_toolkit.connection() as connected_target_toolkit:
            # Create agent with tools from both servers
            camel_agent = await create_agent(connected_coral_toolkit, connected_target_toolkit)
            
            # Register with the specified agent ID
            print(f"Attempting to register agent as '{self.agent_id}'...")
            await camel_agent.astep("Register as {self.agent_id}")
            print(f"Agent '{self.agent_id}' registered.")
            
            # Main agent loop
            print("Starting main agent loop...")
            while True:
                try:
                    # A more specific prompt might be needed depending on the agent's role
                    # This prompt asks the agent to check for mentions and respond.
                    prompt = get_user_message()
                    resp = await camel_agent.astep(prompt)
                    if resp and resp.msgs:
                        print(f"Agent response: {{resp.msgs[0].content[:150]}}...")
                    else:
                        print("Agent did not produce a response message.")
                    await asyncio.sleep(7) # Increased sleep time slightly
                except asyncio.CancelledError:
                    print("Agent loop cancelled.")
                    break
                except Exception as e:
                    print(f"Error in agent loop: {{e}}")
                    print("Retrying in 30 seconds...")
                    await asyncio.sleep(30)

async def create_agent(connected_coral_toolkit, connected_target_toolkit):
    # Combine tools from both toolkits
    print("Fetching tools from Coral server...")
    coral_tools = connected_coral_toolkit.get_tools()
    print(f"Found {{len(coral_tools)}} tools from Coral.")

    print("Fetching tools from target MCP server...")
    target_tools = connected_target_toolkit.get_tools()
    print(f"Found {{len(target_tools)}} tools from target MCP.")

    tools = coral_tools + target_tools
    print(f"Total tools available: {{len(tools)}}")
    # print(f"Available tools: {{[tool.name for tool in tools]}}") # Uncomment for debugging

    # System message
    sys_msg = '''{self.system_message}'''
    sys_msg += f\"\"\"Here are the guidelines for using the communication tools:
            {{get_tools_description()}}
            \"\"\"
            
    # Create the model
    # Ensure model_config_dict is correctly formatted
    model_config_dict = {model_config_str}

    print(f"Creating model with config: {{model_config_dict}}")
    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=ModelType.GPT_4O, # Consider making this configurable
        api_key=os.getenv("OPENAI_API_KEY"),
        model_config_dict=model_config_dict,
    )
    
    # Create the agent
    print("Creating ChatAgent...")
    agent = ChatAgent(
        system_message=sys_msg,
        model=model,
        tools=tools,
        message_window_size=4096 * 50, # Consider making this configurable
        token_limit=20000 # Consider making this configurable
    )
    agent.reset()
    agent.memory.clear()
    print("Agent created successfully.")
    return agent

if __name__ == "__main__":
    print("Starting Coralizer wrapper script...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\\nScript interrupted by user.")
    finally:
        print("Coralizer wrapper script finished.")
"""

class GitHubCoralizer:
    def __init__(self,
                 repo_url: str,
                 coral_server_url: str,
                 agent_id: str,
                 branch: Optional[str] = None,
                 openai_api_key: Optional[str] = None): # API key needed for the CAMEL agent
        if not git:
            raise ImportError("GitPython is required but not installed.")
        if not ChatAgent:
             raise ImportError("camel-ai library is required but not installed/imported.")

        self.repo_url = repo_url
        self.coral_server_url = coral_server_url
        self.agent_id = agent_id
        self.branch = branch
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            # The CAMEL agent needs the key to function
            raise ValueError("OpenAI API key is required for the code generation agent. Set OPENAI_API_KEY environment variable or pass it.")
        self.temp_dir = None # To store the path to the temporary directory

    async def _clone_repo(self) -> Path:
        """Clones the repository into a temporary directory."""
        self.temp_dir = tempfile.mkdtemp(prefix="coral_git_")
        repo_path = Path(self.temp_dir)
        print(f"Cloning {self.repo_url} into {repo_path}...")
        try:
            clone_options = {}
            if self.branch:
                clone_options['branch'] = self.branch
            # TODO: Add authentication for private repos if needed (requires more complex GitPython setup)
            git.Repo.clone_from(self.repo_url, repo_path, **clone_options)
            print("Repository cloned successfully.")
            return repo_path
        except git.GitCommandError as e:
            self.cleanup()
            raise RuntimeError(f"Failed to clone repository: {e.stderr}") from e
        except Exception as e:
            self.cleanup()
            raise RuntimeError(f"An unexpected error occurred during cloning: {e}") from e

    def _get_file_tree(self, repo_path: Path) -> str:
        """Generates a simplified directory tree structure."""
        print("Generating file tree...")
        tree_str = ""
        file_count = 0
        for root, dirs, files in os.walk(repo_path):
            # Skip .git directory
            if '.git' in dirs:
                dirs.remove('.git')

            level = root.replace(str(repo_path), '').count(os.sep)
            indent = ' ' * 4 * level
            tree_str += f"{indent}{os.path.basename(root)}/\n"
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                # Optional: Filter for specific file types (e.g., .py, requirements.txt)
                # if f.endswith(".py") or f == "requirements.txt":
                tree_str += f"{sub_indent}{f}\n"
                file_count += 1
                if len(tree_str) > MAX_TREE_CHARS:
                     print(f"Warning: File tree truncated at {MAX_TREE_CHARS} characters.")
                     tree_str += f"{sub_indent}...\n"
                     return tree_str # Return truncated tree

        print(f"Generated tree for {file_count} files.")
        return tree_str


    def _get_code_context(self, repo_path: Path) -> str:
        """Reads relevant code files to create context for the AI."""
        print("Reading Python files for AI context...")
        code_context = ""
        total_chars = 0
        files_read = 0

        # Prioritize common entry points or config files
        priority_files = ["main.py", "app.py", "agent.py", "run.py", "requirements.txt", "pyproject.toml", "setup.py"]
        processed_files = set()

        # Function to read and add content
        def add_content(filepath, filename_for_header):
            nonlocal code_context, total_chars, files_read
            if filepath.is_file() and filepath not in processed_files:
                try:
                    content = filepath.read_text(encoding='utf-8', errors='ignore')
                    header = f"\n--- File: {filename_for_header} ---\n"
                    if total_chars + len(content) + len(header) <= MAX_CODE_CONTEXT_CHARS:
                        code_context += header
                        code_context += content
                        total_chars += len(content) + len(header)
                        files_read += 1
                        processed_files.add(filepath)
                        return True # Content added
                    else:
                        print(f"Warning: Skipping content of {filename_for_header} due to context limit.")
                        return False # Limit hit
                except Exception as e:
                    print(f"Warning: Could not read file {filepath}: {e}")
            return True # Continue if file not found or already processed

        # Process priority files
        for filename in priority_files:
            filepath = repo_path / filename
            if not add_content(filepath, filename):
                 break # Stop if limit hit

        # Read other Python files if space permits
        if total_chars < MAX_CODE_CONTEXT_CHARS:
            for filepath in repo_path.rglob('*.py'):
                 # Skip files in .git or other ignored directories if needed
                 if '.git' in filepath.parts: continue

                 if filepath not in processed_files:
                    relative_path = filepath.relative_to(repo_path)
                    if not add_content(filepath, str(relative_path)):
                        print(f"Warning: Skipping remaining files due to context limit.")
                        break # Stop reading other files

        print(f"Read {files_read} files ({total_chars} chars) for context.")
        if not code_context:
             # Don't raise error, let the agent try with just the tree
             print("Warning: No readable code files found or context limit too small. Agent will rely on file tree.")
        return code_context

    def _parse_generated_code(self, response_content: str) -> Optional[str]:
        """Extracts Python code block from the agent's response."""
        # Look for ```python ... ``` code blocks
        match = re.search(r"```python\s*([\s\S]+?)\s*```", response_content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        else:
            # Fallback: maybe the agent just returned raw code? (Less likely with good prompting)
            # Be cautious with this fallback.
            if "import asyncio" in response_content and "MCPToolkit" in response_content:
                 print("Warning: Could not find ```python block, attempting to use raw response as code.")
                 return response_content.strip()
            else:
                 print("Error: Could not parse Python code from the agent's response.")
                 print("--- Agent Response ---")
                 print(response_content)
                 print("--- End Agent Response ---")
                 return None

    async def _generate_wrapper_with_camel_agent(self, repo_path: Path) -> Optional[str]:
        """Uses a CAMEL agent to generate the coral_wrapper.py content."""
        print("Initializing CAMEL agent for code generation...")

        # 1. Prepare Context
        file_tree = self._get_file_tree(repo_path)
        code_context = self._get_code_context(repo_path)

        # 2. Define System Message for Generator Agent
        system_message = f"""
You are an expert Python programmer specializing in multi-agent systems and the CAMEL AI framework.
Your task is to create the content for a Python script named 'coral_wrapper.py'.
This script MUST integrate an existing Python agent codebase (context provided below) with the Coral Protocol via the CAMEL AI MCPToolkit.

**Core Requirements for `coral_wrapper.py`:**
1.  **Imports:** Include necessary imports (`asyncio`, `os`, `sys`, `time`, `camel.agents.ChatAgent`, `camel.models.ModelFactory`, `camel.toolkits.MCPToolkit`, `camel.toolkits.mcp_toolkit.MCPClient`, `camel.types.*`). Also try to include relevant imports from the original codebase context if identifiable.
2.  **Environment Variables:** The script MUST read `CORAL_SERVER_URL` and `CORAL_AGENT_ID` from environment variables. Provide sensible defaults (e.g., '{self.coral_server_url}' and '{self.agent_id}'). It MUST also read `OPENAI_API_KEY`. Exit gracefully if `OPENAI_API_KEY` is missing.
3.  **`create_agent` Function:** Define an `async def create_agent(connected_mcp_toolkit, agent_id: str)` function.
    *   It should get tools using `connected_mcp_toolkit.get_tools()`.
    *   Define a system message for the *runtime* agent. This message should clearly state its `agent_id` and instruct it to use the Coral tools (register, list, send, wait_for_mentions).
    *   Create an OpenAI model using `ModelFactory.create` (e.g., `ModelType.GPT_4_TURBO` or `GPT_4O`, platform `ModelPlatformType.OPENAI`, read API key from env var). Use a low temperature (e.g., 0.2).
    *   Instantiate a `camel.agents.ChatAgent` with the system message, model, and tools.
    *   Return the created agent.
4.  **`main` Function:** Define an `async def main()` function.
    *   Print status messages (connecting, creating agent, registering, starting loop).
    *   Read `CORAL_AGENT_ID` and `CORAL_SERVER_URL` from environment variables (with defaults).
    *   Create `MCPClient` and `MCPToolkit`.
    *   Use `async with mcp_toolkit.connection() as connected_mcp_toolkit:` block.
    *   Call `create_agent` inside the `with` block.
    *   **Register the Agent:** Explicitly call `await camel_agent.astep(f"Register yourself with the agent ID '{{agent_id}}'.")`. Handle potential errors during registration.
    *   **Main Loop:** Implement a `while True` loop. Inside the loop:
        *   Use `await camel_agent.astep(...)` with a prompt instructing the agent to check for messages (e.g., using `wait_for_mentions` tool) and perform actions.
        *   Include `asyncio.sleep()` (e.g., 10 seconds) to prevent busy-waiting.
        *   Include basic error handling (`try...except Exception`).
5.  **Entry Point:** Include `if __name__ == "__main__": asyncio.run(main())`. Add basic `KeyboardInterrupt` handling.
6.  **Integration (Placeholder):** Include comments indicating where the original agent's logic/classes/functions (identified from the context) might be imported or called, but DO NOT implement this integration yourself. The goal is a functional CAMEL wrapper that connects to Coral.
7.  **Output Format:** Respond ONLY with the generated Python code enclosed in a single ```python ... ``` block. Do not include any other text, explanations, or introductions.

**Context from Cloned Repository:**

**File Structure:**
```
{file_tree}
```

**Code Snippets:**
```python
{code_context}
```

**Example Output:**
```python
{example_output}
```

Generate the `coral_wrapper.py` content based *only* on the requirements and the provided context.
"""

        # 3. Create Generator Agent
        try:
            # Use a capable model for code generation
            generator_model = ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI,
                model_type=ModelType.GPT_4O, # Or GPT_4_TURBO
                api_key=self.openai_api_key,
                model_config_dict={"temperature": 0.1}, # Low temp for deterministic code gen
            )
            code_generator_agent = ChatAgent(system_message=system_message, model=generator_model)
            code_generator_agent.reset() # Start fresh
        except Exception as e:
            print(f"Error creating code generation agent: {e}")
            return None

        # 4. Run Agent Step
        prompt = "Generate the Python code for the `coral_wrapper.py` script based on the requirements and context provided in the system message."
        print("Asking CAMEL agent to generate wrapper code...")
        try:
            response = await code_generator_agent.astep(prompt)
            if response and response.msgs:
                assistant_msg = response.msgs[0]
                print("Agent generation complete.")
                # 5. Parse Output
                return self._parse_generated_code(assistant_msg.content)
            else:
                print("Error: Code generation agent did not return a valid response.")
                return None
        except Exception as e:
            print(f"Error during code generation agent step: {e}")
            return None


    def generate_dockerfile(self, repo_path: Path) -> str:
        """Generates a Dockerfile for the GitHub repo."""
        # This Dockerfile attempts to install dependencies and run the wrapper.
        # It's generic and might need manual adjustment based on the repo.
        print("Generating Dockerfile...")

        # --- Dependency Detection ---
        requirements_content = ""
        has_req_txt = (repo_path / "requirements.txt").exists()
        has_setup_py = (repo_path / "setup.py").exists()
        has_pyproject = (repo_path / "pyproject.toml").exists() # Could be poetry, pdm, etc.

        install_commands = []
        if has_req_txt:
            print("Found requirements.txt.")
            install_commands.append("COPY requirements.txt .")
            install_commands.append("RUN pip install --no-cache-dir -r requirements.txt")
        if has_setup_py:
             print("Found setup.py. Adding 'pip install .'")
             # Copy necessary files for setup.py before running install
             install_commands.append("COPY setup.py .")
             # Heuristic: copy common config files if they exist
             if (repo_path / "setup.cfg").exists(): install_commands.append("COPY setup.cfg .")
             if (repo_path / "MANIFEST.in").exists(): install_commands.append("COPY MANIFEST.in .")
             # Heuristic: copy source directory if setup.py likely uses find_packages()
             # This is tricky - find the likely source dir name (often repo name or 'src')
             repo_name_dir = repo_path / repo_path.name
             src_dir = repo_path / "src"
             if repo_name_dir.is_dir(): install_commands.append(f"COPY {repo_path.name} ./{repo_path.name}")
             elif src_dir.is_dir(): install_commands.append("COPY src ./src")
             install_commands.append("RUN pip install --no-cache-dir .") # Install the package itself
        if has_pyproject:
             print("Found pyproject.toml. Attempting Poetry install (experimental).")
             # This assumes Poetry is used and installs *all* dependencies
             install_commands.append("COPY pyproject.toml .")
             install_commands.append("COPY poetry.lock .") # Copy lock file if it exists
             install_commands.append("RUN pip install --no-cache-dir poetry")
             install_commands.append("RUN poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi")
             # Note: This installs poetry globally in the image first.

        if not install_commands:
             print("Warning: No standard dependency file found (requirements.txt, setup.py, pyproject.toml). Only installing camel-ai.")
             install_commands.append("# Add necessary pip installs here if needed")

        # Ensure camel-ai is installed regardless
        install_commands.append("RUN pip install --no-cache-dir 'camel-ai[web-tools]>=0.2.0,<0.3.0'") # Match pyproject

        requirements_content = "\n".join(install_commands)

        # --- Dockerfile Content ---
        dockerfile = f"""FROM python:3.10-slim

WORKDIR /app

# Copy the entire cloned repository content first
# This allows subsequent COPY/RUN commands to work relative to /app
COPY . /app/

# Copy the generated Coral wrapper into the root of /app
COPY coral_wrapper.py /app/

# Install dependencies (commands determined above)
{requirements_content}

# Set environment variables (API key passed during run)
# ENV OPENAI_API_KEY=...
# ENV CORAL_SERVER_URL=...
# ENV CORAL_AGENT_ID=...

# Run the Coral wrapper (ensure it's executable if needed: RUN chmod +x /app/coral_wrapper.py)
# Use python -u for unbuffered output
CMD ["python", "-u", "/app/coral_wrapper.py"]
"""
        print("Dockerfile generated.")
        return dockerfile

    async def coralize(self) -> Tuple[Optional[str], Optional[str], Optional[Path]]:
        """Clones repo, generates wrapper (via CAMEL agent) and Dockerfile."""
        repo_path = await self._clone_repo()
        try:
            # Generate wrapper using the CAMEL agent method
            wrapper = await self._generate_wrapper_with_camel_agent(repo_path)
            if not wrapper:
                 print("Error: Failed to generate wrapper code using CAMEL agent.")
                 self.cleanup()
                 return None, None, None # Indicate failure

            dockerfile = self.generate_dockerfile(repo_path)
            # Return repo_path so build_and_run knows where the context is
            return wrapper, dockerfile, repo_path
        except Exception as e:
            print(f"Error during coralization process: {e}")
            self.cleanup() # Clean up temp dir on error
            raise e # Re-raise the exception

    def build_and_run(self, wrapper: str, dockerfile: str, repo_path: Path) -> None:
        """Builds and runs the Docker container for the GitHub repo."""
        if not self.openai_api_key: # Double check API key needed for runtime agent
             print("[bold red]Error: OPENAI_API_KEY is missing.[/bold red]")
             self.cleanup()
             return

        print(f"Preparing build context in {repo_path}...")
        # Write the generated files into the cloned repo directory (build context)
        wrapper_path = repo_path / "coral_wrapper.py"
        dockerfile_path = repo_path / "Dockerfile" # Dockerfile needs to be at root of context

        try:
            with open(wrapper_path, "w") as f:
                f.write(wrapper)
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile)
        except IOError as e:
            print(f"[bold red]Error writing generated files: {e}[/bold red]")
            self.cleanup()
            return

        # Build Docker image using the cloned repo path as context
        image_name = f"github-coralizer-{self.agent_id.lower().replace(' ', '-')}"
        print(f"Building Docker image: {image_name} from context {repo_path}...")
        try:
            build_process = subprocess.run(
                ["docker", "build", "-t", image_name, "."], # Use '.' as context path relative to cwd
                cwd=repo_path, # Execute docker build FROM the repo path
                capture_output=True, text=True, check=False
            )

            if build_process.returncode != 0:
                if "permission denied" in build_process.stderr.lower() and "docker.sock" in build_process.stderr.lower():
                     print("[bold red]Docker Permission Error Detected![/bold red]")
                     print("[bold yellow]The current user does not have permission to access the Docker daemon socket.[/bold yellow]")
                     print("[bold yellow]On Linux, try adding your user to the 'docker' group:[/bold yellow]")
                     print("  1. Run: [cyan]sudo usermod -aG docker $USER[/cyan]")
                     print("  2. Log out and log back in, or run: [cyan]newgrp docker[/cyan] in your terminal.")
                     print("[bold yellow]Then, try running the coral command again.[/bold yellow]")
                else:
                    print(f"[bold red]Error building Docker image (Return Code: {build_process.returncode}):[/bold red]")
                    print(build_process.stderr)
                self.cleanup()
                return # Stop if build fails

            print("Docker image built successfully.")

            # Run Docker container
            print(f"Running Docker container {image_name}...")
            print("[bold yellow]Using --network=host for potential local connections.[/bold yellow]")
            print("[bold yellow]Passing CORAL_SERVER_URL and CORAL_AGENT_ID as environment variables.[/bold yellow]")
            print("[bold yellow]Press Ctrl+C in this terminal to stop the container.[/bold yellow]")
            container_name = f"coral-agent-{self.agent_id.lower().replace(' ', '-')}"
            run_cmd = [
                "docker", "run", "--rm",
                "-e", f"OPENAI_API_KEY={self.openai_api_key}",
                "-e", f"CORAL_SERVER_URL={self.coral_server_url}", # Pass Coral URL
                "-e", f"CORAL_AGENT_ID={self.agent_id}",       # Pass Agent ID
                "--network=host",
                "--name", container_name,
                image_name
            ]
            print(f"Executing: {' '.join(run_cmd)}") # Show the command being run
            subprocess.run(run_cmd, check=True) # check=True will raise CalledProcessError if run fails

        except FileNotFoundError:
             print("[bold red]Error: 'docker' command not found. Is Docker installed and in your PATH?[/bold red]")
        except subprocess.CalledProcessError as e:
            print(f"[bold red]Error running Docker command: {e}[/bold red]")
            if e.stderr:
                print(f"[bold red]Stderr:[/bold red]\n{e.stderr}")
        except KeyboardInterrupt:
            print("\n[bold yellow]Stopping Docker container...[/bold yellow]")
            stop_cmd = ["docker", "stop", container_name]
            subprocess.run(stop_cmd, capture_output=True) # Attempt to stop
            print("[bold green]Container stop command issued.[/bold green]")
        finally:
            # --- Important: Clean up the temporary directory ---
            self.cleanup()

    def cleanup(self):
        """Removes the temporary directory used for cloning."""
        if self.temp_dir and Path(self.temp_dir).exists():
            try:
                # Add error handling for Windows file locking issues
                retries = 3
                delay = 1
                while retries > 0:
                    try:
                        shutil.rmtree(self.temp_dir)
                        print(f"Cleaned up temporary directory: {self.temp_dir}")
                        self.temp_dir = None
                        break # Success
                    except OSError as e:
                        # Specifically catch permission errors which might happen on Windows
                        if isinstance(e, PermissionError) or "Access is denied" in str(e):
                             retries -= 1
                             if retries == 0:
                                 print(f"Warning: Failed to clean up temporary directory {self.temp_dir} after multiple retries: {e}")
                             else:
                                 print(f"Warning: Permission error cleaning up {self.temp_dir}, retrying in {delay}s...")
                                 time.sleep(delay)
                        else:
                             # Re-raise other OS errors immediately
                             raise e
            except Exception as e:
                print(f"Warning: Failed to clean up temporary directory {self.temp_dir}: {e}")

    def __del__(self):
        """Ensure cleanup happens when the object is garbage collected."""
        self.cleanup()