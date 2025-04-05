# Coral LangGraph Agent

A collaborative agent built with the LangGraph framework and Coral protocol.

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
- Adding additional MCP servers in the server_config dictionary
- Changing the model parameters
- Implementing a more sophisticated interaction loop
- Adding custom tools or chains

## Coral Protocol

This agent is compatible with the Coral protocol, allowing it to communicate with other agents in the Coral ecosystem.

## Advanced Usage

For more advanced usage, you can:
1. Create a custom agent with specific tools
2. Implement a state graph for more complex behavior
3. Add memory to the agent for persistent conversations
4. Integrate with other LangChain components