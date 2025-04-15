# Coral CLI

A command-line interface (CLI) for initializing Coral agent projects, managing the Coral chatroom server, and "coralizing" (onboarding) existing AI projects onto the Coral network.

## Features

* Initialize new agent projects based on templates (e.g., CAMEL framework).
* Start and manage the Coral Chatroom server (either locally via Java or using Docker).
* Coralize existing projects:
  * Wrap MCP (Model Context Protocol) servers as Coral agents.
  * (Planned) Wrap GitHub repositories containing agent code.
  * (Planned) Wrap Hugging Face models.
* Run coralized agents locally or within Docker containers.

## Setup

1. **Prerequisites:**
    * [Python](https://www.python.org/) (>=3.10, <3.11 - check `pyproject.toml` for exact version).
    * [Poetry](https://python-poetry.org/docs/#installation) for dependency management.
    * [Java](https://adoptium.net/) (JDK 17 or later) - Required for running the chatroom server locally. The server JAR is included.
    * [Docker](https://www.docker.com/products/docker-desktop/) - Required for running the chatroom server or coralized agents in containers. Ensure Docker is installed and running.
    * **(Optional)** Set the `OPENAI_API_KEY` environment variable if using OpenAI models in your agents.

2. **Installation:**
    * Clone the parent repository (if you haven't already).
    * Navigate to the `coral_cli` directory: `cd coral_cli`
    * Install dependencies using Poetry: `poetry install`

3. **Build Coral Server (if needed):**
    * A pre-compiled JAR for the `coral-server` should be included in `coral_cli/binaries/coral-server.jar` or `coral-server/build/libs/`.
    * If you need to rebuild it (e.g., after modifying server code):
        * Navigate to the `coral-server` directory: `cd ../coral-server`
        * Run the Gradle build command: `./gradlew build` (or `gradlew.bat build` on Windows). This requires Java JDK installed.
        * The new JAR will be in `coral-server/build/libs/`. The CLI should automatically find it.

## Usage

The main command is `coral`. Use `coral --help` to see all available commands and options.

### Initialize a Project

Create a basic agent project structure.

```bash
# Initialize interactively
coral init

# Initialize with specific options
coral init --framework camel --language python --output-dir ./my-camel-agent
```

### Manage Chatroom Server

The chatroom server enables agents to communicate.

```bash
# Start the server locally using Java (default port 3001)
coral chatroom start

# Start the server locally on a different port
coral chatroom start --port 8080

# Start the server using Docker (default port 3001)
coral chatroom start --run-mode docker

# Start the server using Docker on a different host port
coral chatroom start --run-mode docker --port 8081
```
*(Note: The first time you run with `--run-mode docker`, it might take a moment to build the server image.)*

### Coralize an MCP Server

Wrap an existing MCP server (e.g., one serving custom tools) so it can join the Coral network.

```bash
# Coralize and run in Docker (interactive prompts for ID/System Message)
coral coralize-mcp http://localhost:5000/sse --run docker

# Coralize and run locally, providing details
coral coralize-mcp http://<target-mcp-url>/sse --agent-id my-tool-agent --sys-msg "Bridge agent for my tools" --run local

# Coralize and save generated files (wrapper script + Dockerfile) instead of running
coral coralize-mcp http://<target-mcp-url>/sse --output-dir ./generated-mcp-agent
```

### Planned Features

* `coral coralize-github <repo-url> ...`
* `coral coralize-hf <model-id> ...`

## Coralizing Explained

"Coralizing" is the process of taking an existing AI component (like an MCP server, a code repository, or a pre-trained model) and wrapping it with a standard Coral entrypoint. This entrypoint allows the component to:

1. Connect to the Coral Chatroom server.
2. Register itself with a unique Agent ID.
3. Communicate with other agents using the Coral protocol tools (send messages, manage threads, wait for mentions).
4. Expose its own capabilities (e.g., tools from an MCP server) to the Coral network alongside the standard communication tools.

The `coralize-*` commands automate the creation of this wrapper and provide options to run it either directly or within a Docker container.