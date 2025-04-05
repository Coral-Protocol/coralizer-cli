"""
Coral CLI - Main CLI implementation
"""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
import questionary

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


def main():
    app()

if __name__ == "__main__":
    main()