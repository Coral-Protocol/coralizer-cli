# The Coralizer

A tool to create onboard existing agents written in other tools or frameworks and MCP servers onto the coral protocol.

## How It Works

The coralizer is able to take in multiple types of inputs

- GitHub Repo url(s)
- MCP Server configs (both commands and SSE)

It then creates a docker file containing a coral entrypoint file that wraps around the agent or MCP server, and deploys it into a container

## Core Architecture

┌─────────────────┐      ┌───────────────────┐
│ GitHub Repo     │──┐   │ Generated Docker  │
│ MCP Server      │  │   │ ┌───────────────┐ │
│ Config          │  ├──>│ │Coral Wrapper  │ │
└─────────────────┘  │   │ │  ┌─────────┐  │ │
                     │   │ │  │Original │  │ │
┌─────────────────┐  │   │ │  │Agent    │  │ │
│ Framework       │──┘   │ │  └─────────┘  │ │
│ Detection       │      │ └───────────────┘ │
└─────────────────┘      └───────────────────┘

## Implementation

Here is the anatomy of a coral entrypoint file

```
async def main():
    # Simply add the Coral server address as a tool
    server = MCPClient("http://localhost:3001/sse")
    mcp_toolkit = MCPToolkit([server])

    async with mcp_toolkit.connection() as connected_mcp_toolkit:
        <!-- If its a github repo, we need to find the main file and replace it with the agent -->
        agent = await create_agent(connected_mcp_toolkit)

        await agent.astep("Register as search_agent")

        # Step the agent continuously
        for i in range(20):  #This should be infinite, but for testing we limit it to 20 to avoid accidental API fees
            resp = await agent.astep(get_user_message())
            sleep(7)

async def create_agent(connected_mcp_toolkit):
    search_tools = [
        ### define your tools here
    ]
    <!-- If its a mcp server, then we just need to replace search tools with a config -->
    tools = connected_mcp_toolkit.get_tools() + search_tools
    sys_msg = ###
    model = ###
    agent = ChatAgent(
        system_message=sys_msg,
        model=model,
        tools=tools,
    )
    agent.reset()
    agent.memory.clear()
    return agent


if __name__ == "__main__":
    asyncio.run(main())
```
