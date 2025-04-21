import asyncio
import os
import tempfile
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple
import shutil
import time
import re # For parsing agent output
import json # For parsing potential JSON output from agent

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
MAX_CODE_CONTEXT_CHARS = 150000 # Example limit, depends on model
MAX_TREE_CHARS = 200000 # Limit for file tree representation

# --- Helper Function ---
async def _run_camel_agent_step(system_prompt: str, user_prompt: str, api_key: str, model_type = ModelType.GPT_4O) -> Optional[str]:
    """Helper to run a single step of a temporary CAMEL agent."""
    if not ChatAgent: return None # Guard against import failure
    try:
        agent_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=model_type,
            api_key=api_key,
            model_config_dict={"temperature": 0.1},
        )
        agent = ChatAgent(system_message=system_prompt, model=agent_model)
        agent.reset()
        response = await agent.astep(user_prompt)
        if response and response.msgs:
            return response.msgs[0].content
        else:
            print("Warning: CAMEL agent step returned no message.")
            return None
    except Exception as e:
        print(f"Error during CAMEL agent step: {e}")
        return None

class GitHubCoralizer:
    def __init__(self,
                 repo_url: str,
                 coral_server_url: str,
                 agent_id: str,
                 branch: Optional[str] = None,
                 openai_api_key: Optional[str] = None):
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
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass it.")
        self.temp_dir = None

    async def _clone_repo(self) -> Path:
        """Clones the repository into a temporary directory."""
        self.temp_dir = tempfile.mkdtemp(prefix="coral_git_")
        repo_path = Path(self.temp_dir)
        print(f"Cloning {self.repo_url} into {repo_path}...")
        try:
            clone_options = {}
            if self.branch:
                clone_options['branch'] = self.branch
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
        """Generates a simplified directory tree structure, prioritizing Python files."""
        print("Generating file tree...")
        tree_str = ""
        entries = []
        for item in repo_path.rglob('*'):
            if '.git' in item.parts:
                continue # Skip .git contents

            depth = len(item.relative_to(repo_path).parts) -1
            indent = '  ' * depth
            if item.is_dir():
                entries.append(f"{indent}└─ {item.name}/")
            elif item.is_file():
                # Optional: Prioritize showing .py files, requirements, etc.
                if item.name.endswith('.py') or item.name in ['requirements.txt', 'pyproject.toml', 'setup.py']:
                     entries.append(f"{indent}└─ {item.name}")
                # else: # Option to hide non-essential files
                #     entries.append(f"{indent}└─ (other file)") # Placeholder

        tree_str = "\n".join(entries)

        if len(tree_str) > MAX_TREE_CHARS:
            print(f"Warning: File tree truncated at {MAX_TREE_CHARS} characters.")
            tree_str = tree_str[:MAX_TREE_CHARS] + "\n..."

        print(f"Generated file tree ({len(tree_str)} chars).")
        return tree_str

    async def _identify_entry_points_with_camel_agent(self, file_tree: str) -> List[str]:
        """Uses a CAMEL agent to suggest potential entry point files based on the tree."""
        print("Asking CAMEL agent to identify potential entry points...")
        system_prompt = """
You are an expert code analyzer. Your task is to identify the most likely main entry point Python files for an application or agent based on the provided file structure. Look for common names like `main.py`, `app.py`, `run.py`, `agent.py`, or files located at the root or in relevant subdirectories (e.g., `src/`, `app/`).

Analyze the following file tree:
```
{file_tree}
```

List the top 3-5 most probable Python entry point file paths relative to the repository root. Output the result as a JSON list of strings. Example: ["main.py", "src/agent.py", "app/run.py"]
Respond ONLY with the JSON list.
"""
        user_prompt = f"Identify the most likely Python entry point files from this file tree:\n{file_tree}\nRespond only with a JSON list of relative file paths."

        response = await _run_camel_agent_step(system_prompt, user_prompt, self.openai_api_key, ModelType.GPT_4O) # Use cheaper model for analysis

        if not response:
            print("Warning: Agent failed to identify entry points. Falling back to default candidates.")
            return ["main.py", "app.py", "agent.py", "run.py"] # Default fallback

        try:
            # Attempt to parse JSON list from response
            # Clean potential markdown formatting
            if response.startswith("```json"):
                 response = response.split("```json\n", 1)[1].split("\n```", 1)[0]
            elif response.startswith("```"):
                 response = response.split("```\n", 1)[1].split("\n```", 1)[0]

            candidate_files = json.loads(response)
            if isinstance(candidate_files, list) and all(isinstance(f, str) for f in candidate_files):
                 print(f"Agent suggested entry points: {candidate_files}")
                 return candidate_files
            else:
                 print(f"Warning: Agent response was not a valid JSON list of strings: {response}")
                 return ["main.py", "app.py", "agent.py", "run.py"]
        except json.JSONDecodeError:
            print(f"Warning: Could not parse JSON response from agent: {response}")
            # Attempt simple parsing if it looks like a plain list string
            if response.startswith('[') and response.endswith(']'):
                 try:
                     # Very basic parsing, might fail
                     items = response.strip('[]').split(',')
                     candidates = [item.strip().strip('\'"') for item in items if item.strip()]
                     if candidates:
                         print(f"Agent suggested entry points (parsed from string): {candidates}")
                         return candidates
                 except Exception:
                     pass # Ignore parsing errors here
            return ["main.py", "app.py", "agent.py", "run.py"] # Fallback

    def _get_focused_code_context(self, repo_path: Path, candidate_files: List[str]) -> str:
        """Reads content only from the candidate files."""
        print(f"Reading content from candidate files: {candidate_files}")
        code_context = ""
        total_chars = 0
        files_read_count = 0

        for filename in candidate_files:
            # Ensure filename is treated as relative path from repo_path
            filepath = repo_path / filename.strip() # Normalize path separators if needed
            if filepath.is_file():
                try:
                    content = filepath.read_text(encoding='utf-8', errors='ignore')
                    header = f"\n--- File: {filename} ---\n"
                    if total_chars + len(content) + len(header) <= MAX_CODE_CONTEXT_CHARS:
                        code_context += header
                        code_context += content
                        total_chars += len(content) + len(header)
                        files_read_count += 1
                    else:
                        print(f"Warning: Skipping content of {filename} due to context limit.")
                        # Optionally break here if hitting the limit is critical
                        # break
                except Exception as e:
                    print(f"Warning: Could not read candidate file {filepath}: {e}")
            else:
                 print(f"Warning: Candidate file not found: {filepath}")

        print(f"Read {files_read_count} candidate files ({total_chars} chars) for focused context.")
        if not code_context:
             print("Warning: No content could be read from candidate files.")
        return code_context

    def _parse_generated_code(self, response_content: str) -> Optional[str]:
        """Extracts Python code block from the agent's response."""
        # Look for ```python ... ``` code blocks
        match = re.search(r"```python\s*([\s\S]+?)\s*```", response_content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        else:
            # Fallback only if it looks like code
            if "import asyncio" in response_content and "MCPToolkit" in response_content:
                 print("Warning: Could not find ```python block, attempting to use raw response as code.")
                 return response_content.strip()
            else:
                 print("Error: Could not parse Python code from the wrapper generation agent's response.")
                 print("--- Agent Response ---")
                 print(response_content)
                 print("--- End Agent Response ---")
                 return None

    async def _generate_wrapper_with_camel_agent(self, focused_code_context: str, file_tree: str) -> Optional[str]:
        """Uses a CAMEL agent to generate the coral_wrapper.py content based on focused context."""
        print("Initializing CAMEL agent for wrapper generation...")

        system_prompt = f"""
You are an expert Python programmer specializing in multi-agent systems and the CAMEL AI framework.
Your task is to create the content for a Python script named 'coral_wrapper.py'.
This script MUST integrate an existing Python agent codebase (context provided below) with the Coral Protocol via the CAMEL AI MCPToolkit.

**Core Requirements for `coral_wrapper.py`:**
1.  **Imports:** Include necessary imports (`asyncio`, `os`, `sys`, `time`, `camel.agents.ChatAgent`, `camel.models.ModelFactory`, `camel.toolkits.MCPToolkit`, `camel.toolkits.mcp_toolkit.MCPClient`, `camel.types.*`). Also **infer and include** relevant imports FROM THE PROVIDED `Code Snippets` context below.
2.  **Environment Variables:** The script MUST read `CORAL_SERVER_URL` (default '{self.coral_server_url}') and `CORAL_AGENT_ID` (default '{self.agent_id}') from environment variables. It MUST also read `OPENAI_API_KEY`. Exit gracefully if `OPENAI_API_KEY` is missing.
3.  **`create_agent` Function:** Define `async def create_agent(connected_mcp_toolkit, agent_id: str)`.
    *   Get tools using `connected_mcp_toolkit.get_tools()`.
    *   Define a system message for the *runtime* agent (instructing it to use Coral tools).
    *   Create an OpenAI model using `ModelFactory.create` (e.g., `ModelType.GPT_4O`, platform `ModelPlatformType.OPENAI`, read API key from env). Use temperature 0.2.
    *   It must instantiate a client or entrypoint to the main agent in the github codebase, not just a camel agent, if the repo has a main agent, we replace the create agent with the entrypoint logic in the repo, otherwise if its a tool based repo, we can create an agent to use the tools
4.  **`main` Function:** Define `async def main()`.
    *   Read env vars, create `MCPClient` and `MCPToolkit`.
    *   Use `async with mcp_toolkit.connection()`.
    *   Call `create_agent`.
    *   **Register the Agent:** Call `await camel_agent.astep(f"Register yourself with the agent ID '{{agent_id}}'.")`.
    *   **Main Loop:** Implement `while True` loop with `await camel_agent.astep(...)` (e.g., checking for mentions) and `asyncio.sleep(10)`. Include basic error handling.
5.  **Entry Point:** Include `if __name__ == "__main__": asyncio.run(main())`.
6.  **Integration (Placeholder):** Include comments suggesting where to import/call original agent logic based on the `Code Snippets`, but DO NOT implement the integration.
7.  **Output Format:** Respond ONLY with the generated Python code enclosed in a single ```python ... ``` block. Do not include any other text.

**Context from Cloned Repository:**

**File Structure Overview:**
```
{file_tree}
```

**Code Snippets (Focus on these for imports/logic):**
```python
{focused_code_context if focused_code_context else "# No specific code context provided, focus on standard wrapper."}
```

Generate the `coral_wrapper.py` content based *only* on the requirements and the provided context.
"""
        user_prompt = "Generate the Python code for the `coral_wrapper.py` script based on the requirements and context provided in the system message."

        response = await _run_camel_agent_step(system_prompt, user_prompt, self.openai_api_key, ModelType.GPT_4O) # Use capable model

        if response:
            return self._parse_generated_code(response)
        else:
            print("Error: Wrapper generation agent failed to respond.")
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
        # Base dependencies
        install_commands.append("RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*")
        install_commands.append("RUN pip install --no-cache-dir --upgrade pip")

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
        """Orchestrates the multi-step coralization process."""
        repo_path = await self._clone_repo()
        if not repo_path: return None, None, None

        try:
            # Step 1: Identify entry points
            file_tree = self._get_file_tree(repo_path)
            candidate_files = await self._identify_entry_points_with_camel_agent(file_tree)

            # Step 2: Get focused context
            focused_context = self._get_focused_code_context(repo_path, candidate_files)

            # Step 3: Generate wrapper using focused context
            wrapper = await self._generate_wrapper_with_camel_agent(focused_context, file_tree)
            if not wrapper:
                 print("Error: Failed to generate wrapper code using CAMEL agent.")
                 self.cleanup()
                 return None, None, None # Indicate failure

            # Step 4: Generate Dockerfile
            dockerfile = self.generate_dockerfile(repo_path)

            return wrapper, dockerfile, repo_path
        except Exception as e:
            print(f"Error during coralization process: {e}")
            self.cleanup()
            raise e

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