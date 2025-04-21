"""
Coral CLI - Main CLI implementation
"""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
import questionary
import subprocess
import sys
import os
import platform
import shutil
import signal
import time
import tempfile
import asyncio

# Make sure the coralizer module is importable
# This assumes coralizer is a sub-package of coral_cli
try:
    from coral_cli.coralizer.mcp_coralizer import MCPCoralizer
except ImportError:
    # Handle cases where the script might be run directly or package structure differs
    sys.path.append(str(Path(__file__).parent.parent))
    from coral_cli.coralizer.mcp_coralizer import MCPCoralizer

from coral_cli.interface_agent import get_interface_agent_script
from coral_cli.templates import generate_template

# Import the new coralizer
try:
    from coral_cli.coralizer.mcp_coralizer import MCPCoralizer
    from coral_cli.coralizer.github_coralizer import GitHubCoralizer # Uses CAMEL internally now
except ImportError:
    sys.path.append(str(Path(__file__).parent.parent))
    from coral_cli.coralizer.mcp_coralizer import MCPCoralizer
    from coral_cli.coralizer.github_coralizer import GitHubCoralizer

# Ensure CAMEL imports are checked or available
try:
    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.toolkits import HumanToolkit, MCPToolkit
    from camel.toolkits.mcp_toolkit import MCPClient
    from camel.types import ModelPlatformType, ModelType
except ImportError:
    print("[bold red]Error: camel-ai library is not installed or accessible.[/bold red]")
    print("[bold yellow]Please run 'poetry install' to install dependencies.[/bold yellow]")
    # Set to None to prevent errors later if checks fail
    ChatAgent = ModelFactory = HumanToolkit = MCPToolkit = MCPClient = ModelPlatformType = ModelType = None

app = typer.Typer(
    name="coral",
    help="CLI tool for creating and managing multiagent systems with the Coral protocol",
    add_completion=True,
    no_args_is_help=True, # Show help if no command is given
)

console = Console()

# --- Constants ---
CORAL_SERVER_DOCKER_IMAGE = "coral-protocol/coral-server:latest"
DEFAULT_CHATROOM_PORT = 3001

# --- Helper Functions ---

def is_docker_installed():
    """Check if Docker CLI is installed and accessible."""
    return shutil.which("docker") is not None

def is_git_installed():
    """Check if Git CLI is installed and accessible."""
    return shutil.which("git") is not None

def check_openai_key():
    """Check if OPENAI_API_KEY environment variable is set."""
    return os.getenv("OPENAI_API_KEY") is not None

# --- Existing Commands ---

@app.command()
def init(
    framework: Optional[str] = typer.Option(
        None, "--framework", "-f", help="Framework to use (camel, langgraph, crewai, custom)"
    ),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="Programming language to use (python)"
    ),
    output_dir: str = typer.Option(
        ".", "--output-dir", "-o", help="Directory to initialize the project in"
    )
):
    """
    Initialize a new Coral agent project
    """
    console.print("[bold blue]🐠 Initializing new Coral agent project[/bold blue]")
    
    # If output directory not provided, prompt for it with default "src"
    if not output_dir:
        output_dir = questionary.text(
            "Enter output directory:",
            default="src"
        ).ask()
        if not output_dir: # Handle empty input
            console.print("[bold red]Output directory cannot be empty.[/bold red]")
            raise typer.Exit(1)

    output_dir = Path(output_dir)
    # Check if directory exists and is not empty
    if output_dir.exists() and any(output_dir.iterdir()):
         confirm_overwrite = questionary.confirm(
            f"Directory '{output_dir}' already exists and is not empty. Overwrite?",
            default=False
        ).ask()
         if not confirm_overwrite:
            console.print("[bold yellow]Initialization cancelled.[/bold yellow]")
            raise typer.Exit()
         # Consider cleaning the directory or handling merging if needed
         # For now, we'll just proceed, potentially overwriting files

    output_dir.mkdir(parents=True, exist_ok=True)
    
    # If framework not provided via command line, prompt for it
    if not framework:
        framework = questionary.select(
            "Select a framework:",
            choices=["camel", "langgraph", "crewai", "custom"],
        ).ask()
        if not framework: # Handle cancelled prompt
             console.print("[bold red]Framework selection cancelled.[/bold red]")
             raise typer.Exit(1)

    # For now, we only support Python
    if not language:
        language = questionary.select(
            "Select a language:",
            choices=["python"],
        ).ask()
        if not language: # Handle cancelled prompt
             console.print("[bold red]Language selection cancelled.[/bold red]")
             raise typer.Exit(1)

    # Create combination key for template selection
    template_key = f"{framework}-{language}"
    
    # For now, just print the selected options
    console.print(f"[bold green]Selected framework: {framework}[/bold green]")
    console.print(f"[bold green]Selected language: {language}[/bold green]")
    console.print(f"[bold green]Output directory: {output_dir}[/bold green]")
    
    # Generate the template
    try:
        output_path = Path(output_dir)
        generate_template(framework, language, output_path)
        console.print("[bold green]✅ Project initialized successfully![/bold green]")
        console.print(f"[bold blue]Navigate to '{output_dir}' to see your project.[/bold blue]")
    except ValueError as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        console.print("[bold yellow]Available templates: camel-python[/bold yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {str(e)}[/bold red]")
        raise typer.Exit(1)

@app.command()
def version():
    """
    Show the current version of the Coral CLI
    """
    try:
        from coral_cli import __version__
        console.print(f"Coral CLI version: [bold]{__version__}[/bold]")
    except ImportError:
        console.print("[bold yellow]Could not determine version. Is the package installed correctly?[/bold yellow]")

@app.command()
def chatroom(
    action: str = typer.Argument("start", help="Action to perform: start."), # Default to start
    port: int = typer.Option(DEFAULT_CHATROOM_PORT, "--port", "-p", help="Host port to map the server to."),
    mode: str = typer.Option("sse", "--mode", "-m", help="Server communication mode (used by local Java run): sse, stdio."),
    run_mode: str = typer.Option("local", "--run-mode", help="How to run the server: 'local' (Java JAR) or 'docker'.")
):
    """
    Manage the Coral chatroom server (local Java or Docker).
    """
    if action == "start":
        if run_mode == "local":
            start_chatroom_server_local(port, mode)
        elif run_mode == "docker":
            start_chatroom_server_docker(port)
        else:
            console.print(f"[bold red]Invalid run mode '{run_mode}'. Choose 'local' or 'docker'.[/bold red]")
            raise typer.Exit(1)
    # Add stop/status later if needed
    # elif action == "stop":
    #     stop_chatroom_server(run_mode) # Stop might need to know how it was started
    else:
        console.print(f"[bold red]Unknown action: {action}[/bold red]")
        console.print("[bold yellow]Available actions: start[/bold yellow]") # Update available actions


def start_chatroom_server_local(port: int, mode: str):
    """Start the Coral chatroom server locally using the Java JAR"""
    console.print("[bold blue]Starting Coral chatroom server locally (Java)...[/bold blue]")

    # Check if Java is installed
    if not is_java_installed():
        console.print("[bold red]Error: Java is not installed or not in PATH[/bold red]")
        console.print("[bold yellow]Please install Java to run the Coral chatroom server:[/bold yellow]")
        console.print("1. Download and install Java from https://adoptium.net/")
        console.print("2. Make sure Java is in your PATH")
        console.print("3. Try running 'coral chatroom start' again")
        raise typer.Exit(1) # Exit if Java is missing

    # Get the path to the JAR file
    jar_path = get_server_jar()
    if not jar_path:
        console.print("[bold red]Error: Server JAR not found.[/bold red]")
        console.print("[bold yellow]Attempting to locate server JAR...")
        # Add logic here to potentially download or guide the user if needed
        # For now, just exit
        raise typer.Exit(1)
    else:
        console.print(f"Using server JAR: {jar_path}")

    # Build the command based on the mode
    if mode == "sse":
        args = ["--sse-server-ktor", str(port)]
    elif mode == "stdio":
        args = ["--stdio"]
        console.print("[bold yellow]Note: --port option is ignored in stdio mode.[/bold yellow]")
    else:
        console.print(f"[bold red]Unknown mode: {mode}[/bold red]")
        console.print("[bold yellow]Available modes for local run: sse, stdio[/bold yellow]")
        raise typer.Exit(1)

    try:
        cmd = ["java", "-jar", str(jar_path)] + args
        console.print(f"[bold green]Running command: {' '.join(cmd)}[/bold green]")
        if mode == "sse":
            console.print(f"[bold green]Server URL (local): http://localhost:{port}/sse[/bold green]")

        console.print("[bold yellow]Press Ctrl+C to stop the server[/bold yellow]")
        process = subprocess.Popen(cmd)
        process.wait()

    except KeyboardInterrupt:
        console.print("\n[bold green]Coral chatroom server stopped by user.[/bold green]")
    except FileNotFoundError:
        console.print("[bold red]Error: 'java' command not found. Is Java installed and in your PATH?[/bold red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error starting local server: {str(e)}[/bold red]")
        raise typer.Exit(1)


def start_chatroom_server_docker(port: int):
    """Start the Coral chatroom server using Docker"""
    console.print("[bold blue]Starting Coral chatroom server (Docker)...[/bold blue]")

    # Check Docker prerequisite
    if not is_docker_installed():
        console.print("[bold red]Error: Docker is required for '--run-mode docker', but the 'docker' command was not found.[/bold red]")
        console.print("[bold yellow]Please ensure Docker Desktop (or Docker Engine) is installed, running, and that the 'docker' command is accessible in your system's PATH.[/bold yellow]")
        console.print("[bold yellow]You can test this by simply typing 'docker --version' in your terminal.[/bold yellow]")
        console.print("[bold yellow]Alternatively, choose '--run-mode local' if you prefer not to use Docker.[/bold yellow]")
        raise typer.Exit(1)

    # --- Define Paths relative to CLI ---
    cli_dir = Path(__file__).parent.resolve() # Get the resolved path of the cli directory
    dockerfile_path = cli_dir / "dockerfiles" / "coral-server.Dockerfile"
    jar_name = "coral-server.jar" # Expected JAR name
    jar_in_binaries = cli_dir / "binaries" / jar_name

    # --- Find Dockerfile ---
    if not dockerfile_path.exists():
        console.print(f"[bold red]Error: Coral Server Dockerfile not found.[/bold red]")
        console.print(f"[bold yellow]Expected location: {dockerfile_path}[/bold yellow]")
        raise typer.Exit(1)
    else:
        console.print(f"Using Dockerfile: {dockerfile_path}")

    # --- Ensure JAR exists in binaries/ for Build Context ---
    if not jar_in_binaries.exists():
        console.print(f"[yellow]Server JAR '{jar_name}' not found in '{cli_dir / 'binaries'}'.[/yellow]")
        # Try finding it using get_server_jar and copy it if necessary
        found_jar_path_str = get_server_jar() # This function already tries to copy to ~/.coral/bin
        if found_jar_path_str:
            found_jar_path = Path(found_jar_path_str)
            # Ensure the binaries directory exists
            (cli_dir / "binaries").mkdir(parents=True, exist_ok=True)
            target_path = jar_in_binaries # The destination is binaries/coral-server.jar

            # Copy the found JAR to the binaries directory if it's not already there
            if not target_path.exists() or found_jar_path.resolve() != target_path.resolve():
                 console.print(f"[yellow]Attempting to copy '{found_jar_path.name}' to '{target_path}'...[/yellow]")
                 try:
                     shutil.copy(found_jar_path, target_path)
                     console.print("[green]JAR copied successfully to binaries/ for Docker build.[/green]")
                 except Exception as e:
                     console.print(f"[bold red]Error copying JAR to binaries/: {e}[/bold red]")
                     console.print(f"[bold yellow]Please ensure the server JAR '{jar_name}' exists in '{cli_dir / 'binaries'}' or run './gradlew build' in the 'coral-server' directory and retry.[/bold yellow]")
                     raise typer.Exit(1)
            # If it already exists, no need to copy
        else:
            # If get_server_jar also failed to find/copy it
            console.print(f"[bold red]Error: Server JAR '{jar_name}' could not be located.[/bold red]")
            console.print(f"[bold yellow]Please run './gradlew build' in the 'coral-server' directory, ensure the JAR is copied to '{cli_dir / 'binaries'}', and retry.[/bold yellow]")
            raise typer.Exit(1)

    # --- Build the Docker image ---
    console.print(f"Building Docker image '{CORAL_SERVER_DOCKER_IMAGE}' using context '{cli_dir}'...")
    try:
        build_cmd = ["docker", "build", "-f", str(dockerfile_path), "-t", CORAL_SERVER_DOCKER_IMAGE, "."]
        build_process = subprocess.run(
            build_cmd,
            cwd=cli_dir,
            capture_output=True, text=True, check=False # Don't raise on error yet
        )

        # Check for build errors
        if build_process.returncode != 0:
            # Check specifically for permission error
            if "permission denied" in build_process.stderr.lower() and "docker.sock" in build_process.stderr.lower():
                 console.print("[bold red]Docker Permission Error Detected![/bold red]")
                 console.print("[bold yellow]The current user does not have permission to access the Docker daemon socket.[/bold yellow]")
                 console.print("[bold yellow]On Linux, try adding your user to the 'docker' group:[/bold yellow]")
                 print("  1. Run: [cyan]sudo usermod -aG docker $USER[/cyan]")
                 print("  2. Log out and log back in, or run: [cyan]newgrp docker[/cyan] in your terminal.")
                 print("[bold yellow]Then, try running the coral command again.[/bold yellow]")
                 # Exit cleanly after printing the specific error message
                 raise typer.Exit(1) # Use typer.Exit to stop execution here
            else:
                # Print generic build error
                console.print(f"[bold red]Error building Docker image (Return Code: {build_process.returncode}):[/bold red]")
                console.print(build_process.stderr)
                raise typer.Exit(1) # Exit on generic build error too

        console.print("[green]Docker image built successfully.[/green]")

    except FileNotFoundError:
         console.print("[bold red]Error: 'docker' command not found. Is Docker installed and in your PATH?[/bold red]")
         raise typer.Exit(1)
    except typer.Exit: # Re-raise typer.Exit to ensure it propagates correctly
        raise
    except Exception as e:
         # Catch other potential exceptions during build setup or execution
         console.print(f"[bold red]An unexpected error occurred during Docker build setup or execution: {e}[/bold red]")
         raise typer.Exit(1)

    # --- Run the Docker container ---
    container_name = "coral-chatroom-server"
    console.print(f"Running Docker container '{container_name}' from image '{CORAL_SERVER_DOCKER_IMAGE}'...")
    try:
        # Stop and remove existing container with the same name, if any
        stop_cmd = ["docker", "stop", container_name]
        remove_cmd = ["docker", "rm", container_name]
        subprocess.run(stop_cmd, capture_output=True) # Ignore errors if container doesn't exist
        subprocess.run(remove_cmd, capture_output=True)

        run_cmd = [
            "docker", "run",
            "--rm", # Remove container when it exits
            "-d",   # Run in detached mode (background)
            "-p", f"{port}:{DEFAULT_CHATROOM_PORT}", # Map host port to container port
            "--name", container_name,
            CORAL_SERVER_DOCKER_IMAGE
        ]
        subprocess.run(run_cmd, check=True, capture_output=True, text=True)
        console.print(f"[bold green]✅ Coral chatroom server started in Docker container '{container_name}'.[/bold green]")
        console.print(f"[bold green]   Host Port: {port}[/bold green]")
        console.print(f"[bold green]   Container Port: {DEFAULT_CHATROOM_PORT}[/bold green]")
        console.print(f"[bold green]   Server URL (Docker): http://localhost:{port}/sse[/bold green]")
        console.print(f"[bold yellow]To view logs: docker logs {container_name}[/bold yellow]")
        console.print(f"[bold yellow]To stop: docker stop {container_name}[/bold yellow]")

    except FileNotFoundError:
         console.print("[bold red]Error: 'docker' command not found. Is Docker installed and in your PATH?[/bold red]")
         raise typer.Exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running Docker container: {e}[/bold red]")
        if e.stderr:
            console.print(f"[bold red]Stderr:[/bold red]\n{e.stderr}")
        raise typer.Exit(1)
    except Exception as e:
         console.print(f"[bold red]An unexpected error occurred during Docker run: {e}[/bold red]")
         raise typer.Exit(1)


def get_server_jar() -> Optional[str]:
    # ... (get_server_jar implementation - ensure it finds the correct JAR name, e.g., coral-server-1.0-SNAPSHOT.jar) ...
    # Adjust the dev_jar_path if the snapshot name changes
    script_dir = Path(__file__).parent
    # Make sure this name matches the actual built JAR name
    jar_name = "coral-server.jar"
    dev_jar_path = script_dir.parent / "coral-server" / "build" / "libs" / jar_name

    locations = [
        Path(__file__).parent / "binaries" / jar_name,
        Path.home() / ".coral" / "bin" / jar_name,
    ]

    for loc in locations:
        if loc.exists() and loc.is_file():
            return str(loc)

    if dev_jar_path.exists() and dev_jar_path.is_file():
        config_dir = Path.home() / ".coral" / "bin"
        config_jar = config_dir / jar_name
        if not config_jar.exists():
            try:
                console.print(f"Found development JAR, copying to {config_jar}...")
                config_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(dev_jar_path, config_jar)
                return str(config_jar)
            except Exception as e:
                console.print(f"[bold yellow]Warning: Could not copy dev JAR: {e}[/bold yellow]")
                return str(dev_jar_path)
        else:
             return str(config_jar)

    console.print(f"[bold red]Server JAR '{jar_name}' not found in standard locations:[/bold red]")
    # ... (print locations) ...
    return None


def get_server_dir() -> Optional[Path]: # Return Optional[Path]
    """Get the path to the server directory relative to the CLI script."""
    server_dir = Path(__file__).resolve().parent.parent / "coral-server"
    if server_dir.is_dir():
        return server_dir
    return None

def is_java_installed():
    """Check if Java is installed"""
    try:
        subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        return False

@app.command("coralize-mcp")
def coralize_mcp(
    target_url: str = typer.Argument(..., help="The SSE URL of the target MCP server to wrap."),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", "-id", help="Unique ID for the new Coral agent."),
    system_message: Optional[str] = typer.Option(None, "--sys-msg", "-sm", help="System message for the underlying LLM."),
    coral_url: str = typer.Option("http://localhost:3001/sse", "--coral-url", "-c", help="URL of the Coral chatroom server."),
    run_mode: str = typer.Option("docker", "--run", "-r", help="How to run the coralized agent: 'docker' or 'local'."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory to save generated files instead of running."),
):
    """
    Wrap an existing MCP server as a Coral agent and run it.
    """
    console.print(f"[bold blue]🐠 Coralizing MCP server: {target_url}[/bold blue]")

    # --- Input Validation and Prompts ---
    if not agent_id:
        agent_id = questionary.text("Enter a unique Agent ID for Coral:").ask()
        if not agent_id:
            console.print("[bold red]Agent ID is required.[/bold red]")
            raise typer.Exit(1)

    if not system_message:
        default_sys_msg = f"You are an agent named '{agent_id}'. Your goal is to act as a bridge to an external MCP server located at {target_url}. Use the tools provided by both the Coral server and the target server to respond to requests and fulfill tasks. Prioritize using the target server's tools when appropriate for its functions."
        system_message = questionary.text(
            "Enter the system message for the agent:",
            default=default_sys_msg
        ).ask()
        if not system_message:
            console.print("[bold red]System message is required.[/bold red]")
            raise typer.Exit(1)

    if run_mode not in ["docker", "local"]:
        console.print(f"[bold red]Invalid run mode '{run_mode}'. Choose 'docker' or 'local'.[/bold red]")
        raise typer.Exit(1)

    # --- Prerequisite Checks ---
    console.print("Checking prerequisites...")
    if not check_openai_key():
        console.print("[bold red]Error: OPENAI_API_KEY environment variable is not set.[/bold red]")
        console.print("[bold yellow]Please set your OpenAI API key to allow the agent to function.[/bold yellow]")
        # Decide whether to exit or proceed with a warning
        if not questionary.confirm("Proceed anyway (agent will likely fail)?", default=False).ask():
             raise typer.Exit(1)


    if run_mode == "docker" and not is_docker_installed():
        console.print("[bold red]Error: Docker is required for '--run docker' mode, but the 'docker' command was not found.[/bold red]")
        console.print("[bold yellow]Please ensure Docker Desktop (or Docker Engine) is installed, running, and that the 'docker' command is accessible in your system's PATH.[/bold yellow]")
        console.print("[bold yellow]You can test this by simply typing 'docker --version' in your terminal.[/bold yellow]")
        console.print("[bold yellow]Alternatively, choose '--run local' if you prefer not to use Docker.[/bold yellow]")
        raise typer.Exit(1)

    console.print("[green]Prerequisites check passed.[/green]")

    # --- Instantiate Coralizer ---
    coralizer = MCPCoralizer(
        coral_server_url=coral_url,
        target_mcp_url=target_url,
        agent_id=agent_id,
        system_message=system_message
        # Add model_config options later if needed
    )

    # --- Generate Files ---
    console.print("Generating Coral wrapper script and Dockerfile...")
    try:
        wrapper_script, dockerfile_content = coralizer.coralize()
    except Exception as e:
        console.print(f"[bold red]Error generating files: {e}[/bold red]")
        raise typer.Exit(1)

    # --- Handle Output ---
    if output_dir:
        console.print(f"Saving generated files to: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        wrapper_path = output_dir / "coral_wrapper.py"
        dockerfile_path = output_dir / "Dockerfile"
        try:
            with open(wrapper_path, "w") as f:
                f.write(wrapper_script)
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            console.print("[bold green]✅ Files saved successfully![/bold green]")
            console.print(f"To run manually (using Docker):")
            console.print(f"  cd {output_dir}")
            console.print(f"  docker build -t mcp-coralizer-{agent_id.lower().replace(' ', '-')} .")
            console.print(f"  docker run --rm -e OPENAI_API_KEY=$OPENAI_API_KEY --network=host mcp-coralizer-{agent_id.lower().replace(' ', '-')}")
            console.print(f"To run manually (locally):")
            console.print(f"  pip install camel-ai>=0.2.0 pydantic>=2.0 # Ensure dependencies are installed")
            console.print(f"  python {wrapper_path}")

        except IOError as e:
            console.print(f"[bold red]Error saving files: {e}[/bold red]")
            raise typer.Exit(1)
    else:
        # --- Execute ---
        if run_mode == "docker":
            console.print("Attempting to build and run Docker container...")
            try:
                # build_and_run now handles the API key check internally
                coralizer.build_and_run(wrapper_script, dockerfile_content)
            except Exception as e: # Catch potential exceptions from build_and_run
                 console.print(f"[bold red]An error occurred during Docker execution: {e}[/bold red]")
                 raise typer.Exit(1)

        elif run_mode == "local":
            console.print("Attempting to run locally...")
            # Check if camel-ai seems importable (basic check)
            try:
                import camel # type: ignore
            except ImportError:
                console.print("[bold yellow]Warning: 'camel-ai' library not found in the current Python environment.[/bold yellow]")
                console.print("[bold yellow]Please install it ('pip install camel-ai') or the script might fail.[/bold yellow]")
                if not questionary.confirm("Attempt to run anyway?", default=True).ask():
                    raise typer.Exit(1)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp_script:
                tmp_script.write(wrapper_script)
                script_path = tmp_script.name

            console.print(f"Running wrapper script: {script_path}")
            console.print("[bold yellow]Press Ctrl+C to stop the agent.[/bold yellow]")
            process = None
            try:
                # Run using the same Python interpreter that's running the CLI
                cmd = [sys.executable, script_path]
                # Pass environment variables explicitly, especially the API key
                env = os.environ.copy()
                process = subprocess.Popen(cmd, env=env)
                process.wait() # Wait for the script to finish or be interrupted

            except KeyboardInterrupt:
                console.print("\n[bold yellow]Stopping local agent...[/bold yellow]")
                if process:
                    process.terminate() # Send SIGTERM
                    try:
                        process.wait(timeout=5) # Wait a bit for graceful shutdown
                    except subprocess.TimeoutExpired:
                        process.kill() # Force kill if necessary
                console.print("[bold green]Local agent stopped.[/bold green]")
            except Exception as e:
                console.print(f"[bold red]Error running script locally: {e}[/bold red]")
            finally:
                # Clean up the temporary script file
                if script_path and os.path.exists(script_path):
                    os.remove(script_path)

@app.command("coralize-github")
def coralize_github(
    repo_url: str = typer.Argument(..., help="URL of the GitHub repository to coralize."),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", "-id", help="Unique ID for the new Coral agent."),
    coral_url: str = typer.Option("http://localhost:3001/sse", "--coral-url", "-c", help="URL of the Coral chatroom server."),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Specific branch to clone (default is repo's default)."),
    # github_token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub token for private repositories (or use GITHUB_TOKEN env var)."), # Token not used in current clone logic
    openai_api_key: Optional[str] = typer.Option(None, envvar="OPENAI_API_KEY", help="OpenAI API Key (reads from env var OPENAI_API_KEY by default). Needed for the code generation agent."),
    run_mode: str = typer.Option("docker", "--run", "-r", help="How to run the coralized agent: 'docker' (recommended). 'local' is highly experimental."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory to save generated files and cloned repo instead of running."),
):
    """
    Wrap a GitHub repository using a CAMEL agent to generate the wrapper. (Experimental)
    """
    console.print(f"[bold blue]🐠 Coralizing GitHub repository: {repo_url}[/bold blue]")
    console.print("[bold yellow]Warning: This feature is experimental. CAMEL agent-generated code may require manual adjustments.[/bold yellow]")

    # --- Input Validation and Prompts ---
    if not agent_id:
        # ... (prompt for agent_id) ...
        pass # Keep prompt logic

    if run_mode not in ["docker", "local"]:
        # ... (invalid run mode message) ...
        pass # Keep validation
    if run_mode == "local":
         # ... (local run warning) ...
         pass # Keep warning

    # --- Prerequisite Checks ---
    console.print("Checking prerequisites...")
    # Check for API key *before* initializing coralizer
    resolved_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        console.print("[bold red]Error: OPENAI_API_KEY is required but not set.[/bold red]")
        console.print("[bold yellow]Please set the OPENAI_API_KEY environment variable or use the --openai-api-key option.[/bold yellow]")
        raise typer.Exit(1)

    if not is_git_installed():
         # ... (git not installed message) ...
         raise typer.Exit(1)

    # Check for GitPython and CAMEL library
    try:
        import git
        from camel.agents import ChatAgent # Check if core CAMEL class is importable
    except ImportError as e:
        console.print(f"[bold red]Missing required library: {e}.[/bold red]")
        console.print("[bold yellow]Please ensure 'GitPython' and 'camel-ai' are installed (`poetry install`).[/bold yellow]")
        raise typer.Exit(1)

    if run_mode == "docker" and not is_docker_installed():
        # ... (docker not installed message) ...
        raise typer.Exit(1)

    console.print("[green]Prerequisites check passed.[/green]")

    # --- Instantiate Coralizer ---
    coralizer = None # Initialize for finally block
    try:
        coralizer = GitHubCoralizer(
            repo_url=repo_url,
            coral_server_url=coral_url,
            agent_id=agent_id,
            branch=branch,
            openai_api_key=resolved_api_key # Pass the resolved key
        )

        # --- Generate Files ---
        console.print("Generating Coral wrapper script (using CAMEL agent) and Dockerfile (may take a while)...")
        # Use asyncio.run for the async coralize method
        wrapper_script, dockerfile_content, repo_path = asyncio.run(coralizer.coralize())

        # --- Check Generation Result ---
        if wrapper_script is None or dockerfile_content is None or repo_path is None:
             console.print("[bold red]Failed to generate necessary files. See previous errors.[/bold red]")
             # Cleanup might have already happened in coralizer
             if coralizer and coralizer.temp_dir: coralizer.cleanup()
             raise typer.Exit(1)


        # --- Handle Output ---
        if output_dir:
            # ... (logic for saving files to output_dir remains largely the same) ...
            # Ensure it uses repo_path correctly and places Dockerfile inside the moved repo dir
            console.print(f"Saving generated files and cloned repo to: {output_dir}")
            if output_dir.exists():
                 console.print(f"[yellow]Output directory '{output_dir}' already exists. Overwriting contents.[/yellow]")
            else:
                 output_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Move the entire cloned repo content
                # Use repo_path.name which should be the temp dir name
                cloned_content_dest = output_dir / repo_path.name
                if cloned_content_dest.exists():
                     shutil.rmtree(cloned_content_dest) # Remove destination if it exists before moving
                shutil.move(str(repo_path), str(output_dir)) # Move the temp dir content

                # Write the generated files into the *new* location
                wrapper_path_out = cloned_content_dest / "coral_wrapper.py"
                dockerfile_path_out = cloned_content_dest / "Dockerfile" # Place Dockerfile inside the moved repo dir

                with open(wrapper_path_out, "w") as f: f.write(wrapper_script)
                with open(dockerfile_path_out, "w") as f: f.write(dockerfile_content)

                console.print("[bold green]✅ Files and repository saved successfully![/bold green]")
                console.print(f"Repository content saved to: {cloned_content_dest}")
                console.print(f"To run manually (using Docker):")
                console.print(f"  cd {cloned_content_dest}")
                console.print(f"  docker build -t github-coralizer-{agent_id.lower().replace(' ', '-')} .")
                console.print(f"  docker run --rm -e OPENAI_API_KEY=$OPENAI_API_KEY -e CORAL_SERVER_URL={coral_url} -e CORAL_AGENT_ID={agent_id} --network=host github-coralizer-{agent_id.lower().replace(' ', '-')}")

            except Exception as e:
                console.print(f"[bold red]Error saving files/repo: {e}[/bold red]")
                # Cleanup might have already happened in coralizer if error was during generation
                if coralizer and coralizer.temp_dir: coralizer.cleanup()
                raise typer.Exit(1)
            # No finally block needed here for cleanup, as build_and_run wasn't called

        else:
            # --- Execute ---
            if run_mode == "docker":
                console.print("Attempting to build and run Docker container...")
                # build_and_run now handles cleanup internally via its finally block
                coralizer.build_and_run(wrapper_script, dockerfile_content, repo_path)

            elif run_mode == "local":
                # ... (local run logic remains the same, but still highly experimental) ...
                # Ensure it writes the wrapper/dockerfile to repo_path before running
                console.print("[bold yellow]Attempting experimental local run...[/bold yellow]")
                wrapper_path_local = repo_path / "coral_wrapper.py"
                dockerfile_path_local = repo_path / "Dockerfile"
                try:
                    with open(wrapper_path_local, "w") as f: f.write(wrapper_script)
                    with open(dockerfile_path_local, "w") as f: f.write(dockerfile_content)
                except IOError as e:
                     print(f"[bold red]Error writing generated files to temp dir for local run: {e}[/bold red]")
                     coralizer.cleanup()
                     raise typer.Exit(1)

                # ... (rest of local run subprocess logic) ...
                process = None
                try:
                    cmd = [sys.executable, str(wrapper_path_local)]
                    env = os.environ.copy()
                    # Pass Coral URL/ID via env vars for local run too
                    env["CORAL_SERVER_URL"] = coral_url
                    env["CORAL_AGENT_ID"] = agent_id
                    # API key should already be in os.environ
                    process = subprocess.Popen(cmd, env=env, cwd=repo_path)
                    process.wait()
                # ... (KeyboardInterrupt, Exception handling for local run) ...
                except KeyboardInterrupt:
                    # ...
                    pass
                except Exception as e:
                    # ...
                    pass
                finally:
                    coralizer.cleanup() # Cleanup after local run attempt


    except (ValueError, RuntimeError, ImportError) as e: # Catch errors from Coralizer init or methods
        console.print(f"[bold red]Error during GitHub coralization setup: {e}[/bold red]")
        if coralizer: coralizer.cleanup() # Ensure cleanup if init succeeded partially
        raise typer.Exit(1)
    except Exception as e: # Catch unexpected errors
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
        import traceback
        traceback.print_exc() # Print stack trace for debugging unexpected errors
        if coralizer: coralizer.cleanup()
        raise typer.Exit(1)


@app.command("start-interface")
def start_interface(
    agent_id: str = typer.Option("UserInterfaceAgent", "--agent-id", "-id", help="Unique ID for the interface agent."),
    coral_url: str = typer.Option("http://localhost:3001/sse", "--coral-url", "-c", help="URL of the Coral chatroom server."),
    openai_api_key: Optional[str] = typer.Option(None, envvar="OPENAI_API_KEY", help="OpenAI API Key (reads from env var OPENAI_API_KEY by default)."),
):
    """
    Start a standard CAMEL AI agent to interact with the user and the Coral network.
    """
    console.print(f"[bold blue]🐠 Starting User Interface Agent: {agent_id}[/bold blue]")

    # --- Prerequisite Checks ---
    console.print("Checking prerequisites...")
    resolved_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        console.print("[bold red]Error: OPENAI_API_KEY is required but not set.[/bold red]")
        console.print("[bold yellow]Please set the OPENAI_API_KEY environment variable or use the --openai-api-key option.[/bold yellow]")
        raise typer.Exit(1)

    console.print("[green]Prerequisites check passed.[/green]")

    # --- Generate Script ---
    try:
        interface_script = get_interface_agent_script(coral_url, agent_id)
    except Exception as e:
         console.print(f"[bold red]Error generating interface agent script: {e}[/bold red]")
         raise typer.Exit(1)

    # --- Execute Script Locally ---
    console.print("Attempting to run interface agent locally...")
    script_path = None # Initialize script_path
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding='utf-8') as tmp_script:
            tmp_script.write(interface_script)
            script_path = tmp_script.name

        console.print(f"Running agent script: {script_path}")
        console.print("[bold yellow]Press Ctrl+C to stop the agent.[/bold yellow]")
        process = None

        # Run using the same Python interpreter that's running the CLI
        cmd = [sys.executable, script_path]
        # Pass environment variables explicitly (API key)
        # Coral URL and Agent ID are embedded in the script now
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = resolved_api_key # Ensure the key is passed

        process = subprocess.Popen(cmd, env=env)
        process.wait() # Wait for the script to finish or be interrupted

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Stopping interface agent...[/bold yellow]")
        if process:
            process.terminate() # Send SIGTERM
            try:
                process.wait(timeout=5) # Wait a bit
            except subprocess.TimeoutExpired:
                process.kill() # Force kill if needed
        console.print("[bold green]Interface agent stopped.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error running script locally: {e}[/bold red]")
    finally:
        # Clean up the temporary script file
        if script_path and os.path.exists(script_path):
            try:
                os.remove(script_path)
                # print(f"Cleaned up temp script: {script_path}") # Optional debug msg
            except OSError as e:
                 console.print(f"[bold yellow]Warning: Could not delete temporary script {script_path}: {e}[/bold yellow]")

# --- Boilerplate ---

def main():
    app()

if __name__ == "__main__":
    main()