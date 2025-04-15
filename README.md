# Coral Protocol - Monorepo

This repository contains tools and implementations related to the Coral Protocol for multi-agent systems.

## Projects

* **`coral-cli/`**: A command-line interface (CLI) for initializing Coral agent projects, managing the Coral chatroom server, and "coralizing" (onboarding) existing AI projects onto the Coral network. See [coral_cli/README.md](coral_cli/README.md) for details.
* **`coral-server/`**: A Java-based implementation of a Coral chatroom server using the Model Context Protocol (MCP). It provides tools for agents to register, communicate, and manage conversation threads. See [coral-server/README.md](coral-server/README.md) for details.

## Setup

This repository uses submodules or includes multiple projects. Please refer to the README file within each specific project directory (`coral_cli/`, `coral-server/`) for detailed setup and usage instructions.

Generally, for Python-based projects like `coral_cli`, you will need [Poetry](https://python-poetry.org/docs/#installation) for dependency management.
