"""
Template management module for Coral CLI
"""
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List

from rich.console import Console

# Template directory is relative to this file
TEMPLATE_DIR = Path(__file__).parent
console = Console()


def get_template_path(framework: str, language: str) -> Path:
    """
    Get the path to the template directory for the given framework and language
    
    Args:
        framework: The framework to use (e.g., "camel")
        language: The programming language to use (e.g., "python")
        
    Returns:
        Path to the template directory
    """
    return TEMPLATE_DIR / language / framework


def generate_template(framework: str, language: str, output_path: Path) -> None:
    """
    Generate template files for the selected framework and language
    
    Args:
        framework: The framework to use (e.g., "camel")
        language: The programming language to use (e.g., "python")
        output_path: Directory to write the files to
    """
    template_path = get_template_path(framework, language)
    
    if not template_path.exists():
        console.print(f"[bold red]Error: Template not found for {framework}-{language}[/bold red]")
        raise ValueError(f"Template not found for {framework}-{language}")
    
    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Copy all files from the template directory to the output path
    for template_file in template_path.glob("**/*"):
        if template_file.is_file():
            relative_path = template_file.relative_to(template_path)
            target_file = output_path / relative_path
            
            # Create parent directories if they don't exist
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file content
            shutil.copy2(template_file, target_file)
            console.print(f"[green]Created: {target_file}[/green]")