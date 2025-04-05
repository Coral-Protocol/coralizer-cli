# Coral Camel Agent

A collaborative agent built with the Camel framework and Coral protocol.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set up your environment variables (create a `.env` file if needed):
   ```
   OPENAI_API_KEY=your_openai_api_key
   ```

3. Run the agent:
   ```
   python agent.py
   ```

## Customization

You can modify the agent by:
- Changing the system prompt in `agent.py`
- Adding custom tools in a tools directory
- Modifying the MCP server URL

## Coral Protocol

This agent is compatible with the Coral protocol, allowing it to communicate with other agents in the Coral ecosystem.