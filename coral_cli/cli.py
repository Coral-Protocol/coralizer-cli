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

from coral_cli.templates import generate_template

app = typer.Typer(
    name="coral",
    help="CLI tool for creating and managing multiagent systems with the Coral protocol",
    add_completion=True,
)

console = Console()

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
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # If framework not provided via command line, prompt for it
    if not framework:
        framework = questionary.select(
            "Select a framework:",
            choices=["camel", "langgraph", "crewai", "custom"],
        ).ask()
    
    # For now, we only support Python
    if not language:
        language = questionary.select(
            "Select a language:",
            choices=["python"],
        ).ask()
    
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
    except ValueError as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        console.print("[bold yellow]Available templates: camel-python[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")

@app.command()
def version():
    """
    Show the current version of the Coral CLI
    """
    from coral_cli import __version__
    console.print(f"Coral CLI version: [bold]{__version__}[/bold]")

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
        return
    
    # Get the path to the JAR file
    jar_path = get_server_jar()
    if not jar_path:
        console.print("[bold red]Error: Server JAR not found[/bold red]")
        return
    
    # Build the command based on the mode
    if mode == "sse":
        args = ["--sse-server-ktor", str(port)]
    elif mode == "stdio":
        args = ["--stdio"]
    else:
        console.print(f"[bold red]Unknown mode: {mode}[/bold red]")
        return
    
    try:
        # Run the JAR
        cmd = ["java", "-jar", jar_path] + args
        
        console.print(f"[bold green]Starting Coral chatroom server on port {port} in {mode} mode[/bold green]")
        if mode == "sse":
            console.print(f"[bold green]Server URL: http://localhost:{port}/sse[/bold green]")
        
        # Run the server in the foreground
        console.print("[bold yellow]Press Ctrl+C to stop the server[/bold yellow]")
        subprocess.run(cmd)
    
    except KeyboardInterrupt:
        console.print("\n[bold green]Coral chatroom server stopped[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error starting server: {str(e)}[/bold red]")


def get_server_jar():
    """Get the path to the server JAR file"""
    # First check if it's in the package
    package_jar = Path(__file__).parent / "binaries" / "coral-server.jar"
    if package_jar.exists():
        return str(package_jar)
    
    # If not in package, check in user's config directory
    config_jar = Path.home() / ".coral" / "bin" / "coral-server.jar"
    if config_jar.exists():
        return str(config_jar)
    
    # Not found
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

def main():
    app()

if __name__ == "__main__":
    main()