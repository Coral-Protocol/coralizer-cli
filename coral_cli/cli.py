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

# Make sure the coralizer module is importable
# This assumes coralizer is a sub-package of coral_cli
try:
    from coral_cli.coralizer.mcp_coralizer import MCPCoralizer
except ImportError:
    # Handle cases where the script might be run directly or package structure differs
    sys.path.append(str(Path(__file__).parent.parent))
    from coral_cli.coralizer.mcp_coralizer import MCPCoralizer

from coral_cli.templates import generate_template

app = typer.Typer(
    name="coral",
    help="CLI tool for creating and managing multiagent systems with the Coral protocol",
    add_completion=True,
    no_args_is_help=True, # Show help if no command is given
)

console = Console()

# --- Helper Functions ---

def is_docker_installed():
    """Check if Docker CLI is installed and accessible."""
    return shutil.which("docker") is not None

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
    action: str = typer.Argument(..., help="Action to perform: start"),
    port: int = typer.Option(3001, "--port", "-p", help="Port to run the server on"),
    mode: str = typer.Option("sse", "--mode", "-m", help="Server mode: sse, stdio")
):
    """
    Manage the Coral chatroom server
    """
    if action == "start":
        start_chatroom_server(port, mode)
    else:
        console.print(f"[bold red]Unknown action: {action}[/bold red]")
        console.print("[bold yellow]Available actions: start, stop, status[/bold yellow]")


def start_chatroom_server(port: int, mode: str):
    """Start the Coral chatroom server"""
    console.print("[bold blue]Starting Coral chatroom server...[/bold blue]")
    
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
    else:
        console.print(f"[bold red]Unknown mode: {mode}[/bold red]")
        console.print("[bold yellow]Available modes: sse, stdio[/bold yellow]")
        raise typer.Exit(1)
    
    try:
        # Run the JAR
        cmd = ["java", "-jar", str(jar_path)] + args # Ensure jar_path is string
        
        console.print(f"[bold green]Starting Coral chatroom server on port {port} in {mode} mode[/bold green]")
        if mode == "sse":
            console.print(f"[bold green]Server URL: http://localhost:{port}/sse[/bold green]")
        
        # Run the server in the foreground
        console.print("[bold yellow]Press Ctrl+C to stop the server[/bold yellow]")
        # Use Popen to allow graceful shutdown? For now, run is simpler.
        process = subprocess.Popen(cmd)
        process.wait() # Wait for the process to complete (e.g., via Ctrl+C)
    
    except KeyboardInterrupt:
        console.print("\n[bold green]Coral chatroom server stopped by user.[/bold green]")
    except FileNotFoundError:
        console.print("[bold red]Error: 'java' command not found. Is Java installed and in your PATH?[/bold red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error starting server: {str(e)}[/bold red]")
        raise typer.Exit(1)


def get_server_jar() -> Optional[str]: # Return Optional[str]
    """Get the path to the server JAR file"""
    # Define potential locations
    locations = [
        Path(__file__).parent / "binaries" / "coral-server.jar",
        Path.home() / ".coral" / "bin" / "coral-server.jar",
        # Add other potential locations if needed, e.g., relative to project root
    ]

    for loc in locations:
        if loc.exists() and loc.is_file():
            return str(loc) # Return the first one found

    # If not found, try searching relative to the script's parent dir (useful for dev)
    script_dir = Path(__file__).parent
    dev_jar_path = script_dir.parent / "coral-server" / "build" / "libs" / "agent-fuzzy-p2p-tools-1.0-SNAPSHOT.jar" # Adjust name if needed
    if dev_jar_path.exists() and dev_jar_path.is_file():
        # Optionally copy it to a standard location or just use it directly
        # Let's copy it to the .coral dir for consistency if it doesn't exist there
        config_dir = Path.home() / ".coral" / "bin"
        config_jar = config_dir / "coral-server.jar"
        if not config_jar.exists():
            try:
                console.print(f"Found development JAR, copying to {config_jar}...")
                config_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(dev_jar_path, config_jar)
                return str(config_jar)
            except Exception as e:
                console.print(f"[bold yellow]Warning: Could not copy dev JAR: {e}[/bold yellow]")
                # Fallback to using the dev path directly if copy fails
                return str(dev_jar_path)
        else:
             # If config_jar already exists, prefer it
             return str(config_jar)


    # Not found anywhere
    console.print("[bold red]Server JAR 'coral-server.jar' not found in standard locations:[/bold red]")
    for loc in locations:
        console.print(f"- {loc}")
    console.print(f"- {dev_jar_path} (development build)")
    console.print("[bold yellow]Consider running './gradlew build' in the 'coral-server' directory or placing the JAR manually.[/bold yellow]")
    return None

def get_pid_file_path() -> Path:
    """Get the path to the PID file"""
    config_dir = Path.home() / ".coral"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "server.pid"


def get_server_dir() -> Path:
    """Get the path to the server directory"""
    # The server directory is relative to this file
    return Path(__file__).parent.parent / "coral-server"

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


# --- Boilerplate ---

def main():
    app()

if __name__ == "__main__":
    main()