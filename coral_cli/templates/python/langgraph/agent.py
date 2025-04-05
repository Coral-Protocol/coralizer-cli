import os
import asyncio
from typing import Dict, List, Any

from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from prompts import get_tools_description, get_user_message

# Initialize the LLM
model = ChatOpenAI(
    model="gpt-4o",
    temperature=0.3,
    api_key=os.getenv("OPENAI_API_KEY")
)

async def main():
    # Configure the MCP client with Coral server
    server_config = {
        "coral": {
            "url": "http://localhost:3001/sse",
            "transport": "sse",
        }
    }
    
    # You can add additional servers as needed:
    # "math": {
    #     "command": "python",
    #     "args": ["./math_server.py"],
    #     "transport": "stdio",
    # },
    # "weather": {
    #     "url": "http://localhost:8000/sse",
    #     "transport": "sse",
    # }
    
    print("Connecting to Coral server...")
    async with MultiServerMCPClient(server_config) as client:
        # Create the agent with tools from the MCP client
        tools = client.get_tools()
        agent = create_react_agent(model, tools)
        
        # Register the agent with Coral
        register_message = "Register as user_interaction_agent"
        register_response = await agent.ainvoke({"messages": [HumanMessage(content=register_message)]})
        print(f"Registration response: {register_response}")
        
        # Introduce the agent to other agents
        intro_message = "Check in with the other agents to introduce yourself, before we start answering user queries."
        intro_response = await agent.ainvoke({"messages": [HumanMessage(content=intro_message)]})
        print(f"Introduction response: {intro_response}")
        
        # Ask the user for input
        ask_message = "Ask the user for a request to work with the other agents to fulfill by calling the ask human tool."
        ask_response = await agent.ainvoke({"messages": [HumanMessage(content=ask_message)]})
        print(f"Ask user response: {ask_response}")
        
        # Main interaction loop
        for i in range(20):  # Limit to 20 iterations for testing
            # In a real implementation, you would get user input here
            user_message = "What's the next step?"
            
            # Step the agent
            response = await agent.ainvoke({"messages": [HumanMessage(content=user_message)]})
            print(f"Agent response: {response}")
            
            # Add a small delay to avoid overwhelming the server
            await asyncio.sleep(4)

if __name__ == "__main__":
    asyncio.run(main())