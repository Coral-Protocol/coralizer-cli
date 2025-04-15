import asyncio
import os
import tempfile
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple
import json # Added for cleaner dict formatting

class MCPCoralizer:
    def __init__(self, 
                 coral_server_url: str,
                 target_mcp_url: str,
                 agent_id: str,
                 system_message: str,
                 model_config: Optional[Dict] = None):
        self.coral_server_url = coral_server_url
        self.target_mcp_url = target_mcp_url
        self.agent_id = agent_id
        self.system_message = system_message
        # Ensure model_config is a valid dict even if None is passed
        self.model_config = model_config if isinstance(model_config, dict) else {
            "temperature": 0.3,
            "max_tokens": 4096
        }
        
    def generate_wrapper(self) -> str:
        """Generate the Coral wrapper for the MCP server"""
        # Use json.dumps for reliable dictionary formatting, then decode for the string literal
        # Or simply represent it directly as a string dictionary literal
        model_config_str = repr(self.model_config)

        wrapper = f"""import asyncio
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
        return wrapper
        
    def generate_dockerfile(self) -> str:
        """Generate Dockerfile for the MCP server bridge"""
        # Ensure camel-ai[all] is installed for full functionality if needed,
        # or just camel-ai if specific extras aren't required.
        # requests might not be strictly necessary if camel-ai handles HTTP internally.
        dockerfile = """FROM python:3.10-slim

WORKDIR /app

# Copy the Coral wrapper
COPY coral_wrapper.py /app/

# Install dependencies - consider camel-ai[all] if extra features are needed
# Pinning versions might be good practice for stability
RUN pip install --no-cache-dir camel-ai>=0.2.0 pydantic>=2.0

# Set environment variables - API key is passed during 'docker run'
# ENV OPENAI_API_KEY=${OPENAI_API_KEY} # This is set via 'docker run -e'

# Run the Coral wrapper
CMD ["python", "-u", "/app/coral_wrapper.py"]
# Adding -u ensures print statements appear without delay
"""
        return dockerfile
    
    def coralize(self) -> Tuple[str, str]:
        """Generate all necessary files for coralization"""
        wrapper = self.generate_wrapper()
        dockerfile = self.generate_dockerfile()
        return wrapper, dockerfile
    
    def build_and_run(self, wrapper: str, dockerfile: str) -> None:
        """Build and run the Docker container"""
        # Check for OPENAI_API_KEY before attempting build/run
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[bold red]Error: OPENAI_API_KEY environment variable is not set.[/bold red]")
            print("[bold yellow]Please set the OPENAI_API_KEY before running with Docker.[/bold yellow]")
            return # Exit the function early

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Write wrapper and Dockerfile to temp directory
            wrapper_path = tmp_path / "coral_wrapper.py"
            dockerfile_path = tmp_path / "Dockerfile"
            
            print(f"Writing wrapper to {wrapper_path}")
            with open(wrapper_path, "w") as f:
                f.write(wrapper)
            
            print(f"Writing Dockerfile to {dockerfile_path}")
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile)
            
            # Build Docker image
            image_name = f"mcp-coralizer-{self.agent_id.lower().replace(' ', '-')}" # Sanitize agent_id for image name
            print(f"Building Docker image: {image_name}...")
            try:
                # Run build command, capture output, don't check=True immediately
                build_process = subprocess.run(
                    ["docker", "build", "-t", image_name, tmpdir],
                    capture_output=True, text=True, check=False # Don't raise on error yet
                )

                # Check for permission error specifically
                if build_process.returncode != 0:
                    if "permission denied" in build_process.stderr.lower() and "docker.sock" in build_process.stderr.lower():
                         print("[bold red]Docker Permission Error Detected![/bold red]")
                         print("[bold yellow]The current user does not have permission to access the Docker daemon socket.[/bold yellow]")
                         print("[bold yellow]On Linux, try adding your user to the 'docker' group:[/bold yellow]")
                         print("  1. Run: [cyan]sudo usermod -aG docker $USER[/cyan]")
                         print("  2. Log out and log back in, or run: [cyan]newgrp docker[/cyan] in your terminal.")
                         print("[bold yellow]Then, try running the coral command again.[/bold yellow]")
                    else:
                        # Print generic build error
                        print(f"[bold red]Error building Docker image (Return Code: {build_process.returncode}):[/bold red]")
                        print(build_process.stderr)
                    return # Stop if build fails

                print("Docker image built successfully.")

                # Run Docker container
                print(f"Running Docker container {image_name}...")
                print("[bold yellow]Using --network=host to allow connection to local Coral server.[/bold yellow]")
                print("[bold yellow]Press Ctrl+C in this terminal to stop the container.[/bold yellow]")
                # Note: --network=host might not work on all platforms (e.g., Docker Desktop on Mac/Windows uses VMs)
                # A shared Docker network might be a more robust solution for container-to-container communication.
                subprocess.run([
                    "docker", "run", "--rm",
                    "-e", f"OPENAI_API_KEY={api_key}",
                    "--network=host", # Allows connection to localhost:3001 (Coral server)
                    "--name", f"coral-agent-{self.agent_id.lower().replace(' ', '-')}", # Give container a name
                    image_name
                ], check=True) # Use check=True here, as permission errors usually happen during build/info commands

            except FileNotFoundError:
                 print("[bold red]Error: 'docker' command not found. Is Docker installed and in your PATH?[/bold red]")
            except subprocess.CalledProcessError as e:
                # Catch errors during 'docker run' if any occur besides permission denied
                print(f"[bold red]Error running Docker container: {e}[/bold red]")
                if e.stderr:
                    print(f"[bold red]Stderr:[/bold red]\n{e.stderr.decode()}")
            except KeyboardInterrupt:
                print("\n[bold yellow]Stopping Docker container...[/bold yellow]")
                # Attempt to stop the container by name if it was started
                stop_cmd = ["docker", "stop", f"coral-agent-{self.agent_id.lower().replace(' ', '-')}"]
                subprocess.run(stop_cmd, capture_output=True)
                print("[bold green]Container stopped.[/bold green]")