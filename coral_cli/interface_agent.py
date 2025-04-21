def get_interface_agent_script(coral_url: str, agent_id: str) -> str:
    """Generates the Python script content for the interface agent."""

    # Define helper functions as self-contained strings
    get_tools_description_code = '''
def get_tools_description():
    # Basic description, enhance if needed
    return \'\'\'
        - `register`: Register yourself with your specified agent ID.
        - `list`: List all currently registered agents.
        - `send`: Send a message to another agent or a thread.
        - `wait_for_mentions`: Check for messages specifically mentioning you.
        - `ask_user`: Prompt the human user for input.
        - `send_message_to_user`: Send a final consolidated response to the user.
    \'\'\'
'''

    get_user_message_code = '''
def get_user_message():
    # This simulates the periodic prompt in the original example loop
    return "[automated] Check for user input via 'ask_user' or incoming messages via 'wait_for_mentions'. Collaborate with other agents to fulfill requests. Send final response using 'send_message_to_user'."
'''

    # Using triple single quotes for the main f-string to avoid conflicts with internal double quotes
    # Doubled braces {{}} are used for literal braces in the final script
    script_content = f'''
import asyncio
import os
import sys
from time import sleep

# Check for API key early
if not os.getenv("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set.")
    sys.exit(1)

try:
    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.toolkits import HumanToolkit, MCPToolkit
    from camel.toolkits.mcp_toolkit import MCPClient
    from camel.types import ModelPlatformType, ModelType
except ImportError:
    print("Error: camel-ai library not found or incomplete in the execution environment.")
    sys.exit(1)

# --- Embedded Helper Functions ---
{get_tools_description_code}

{get_user_message_code}
# --- End Embedded Helper Functions ---

async def main():
    coral_server_url = "{coral_url}"
    my_agent_id = "{agent_id}"
    print(f"Starting Interface Agent '{{my_agent_id}}'...")
    print(f"Connecting to Coral Server at {{coral_server_url}}")

    server = MCPClient(coral_server_url)
    mcp_toolkit = MCPToolkit([server])

    async with mcp_toolkit.connection() as connected_mcp_toolkit:
        print("Creating interface agent...")
        camel_agent = await create_interface_agent(connected_mcp_toolkit, my_agent_id)

        print(f"Registering agent as '{{my_agent_id}}'...")
        try:
            # Use a simple registration prompt
            reg_resp = await camel_agent.astep(f"Register yourself with the agent ID '{{my_agent_id}}'.")
            # Check response content if needed
            print(f"Registration attempted for '{{my_agent_id}}'.")
        except Exception as reg_err:
            print(f"Warning: Error during registration: {{reg_err}}")
            # Decide whether to continue if registration fails

        print("Checking in with other agents...")
        try:
            # Allow agent to introduce itself if desired by its system prompt
            await camel_agent.astep("Introduce yourself to other agents using the 'list' and 'send' tools.")
        except Exception as intro_err:
             print(f"Warning: Error during initial check-in: {{intro_err}}")


        print("Starting main loop. Press Ctrl+C to stop.")
        # Continuous loop
        while True:
            try:
                # Get the standard prompt for the agent's tick
                prompt = get_user_message()
                resp = await camel_agent.astep(prompt)
                if resp and resp.msgs:
                    print(f"Agent step response: {{resp.msgs[0].content[:150]}}...")
                # Add a sleep to prevent high CPU usage and excessive API calls
                await asyncio.sleep(10) # Sleep for 10 seconds
            except asyncio.CancelledError:
                 print("Main loop cancelled.")
                 break
            except Exception as e:
                print(f"Error in agent loop: {{e}}")
                print("Attempting to recover...")
                await asyncio.sleep(30) # Longer sleep on error


async def create_interface_agent(connected_mcp_toolkit, my_agent_id: str):
    print("Initializing toolkits...")
    # Ensure HumanToolkit is imported and initialized correctly
    try:
        human_tools = HumanToolkit().get_tools()
    except Exception as ht_err:
        print(f"Warning: Failed to initialize HumanToolkit: {{ht_err}}. User interaction tools might be unavailable.")
        human_tools = []
    tools = connected_mcp_toolkit.get_tools() + human_tools
    print(f"Total tools available: {{len(tools)}}")

    # Define system message using a raw f-string
    sys_msg_content = f\'\'\'
You are a helpful assistant agent responsible for interacting with the human user and coordinating with other AI agents on the Coral network to fulfill the user's requests.
Your designated agent ID is "{{my_agent_id}}". You MUST use this ID when registering.

**Core Responsibilities:**
1.  **User Interaction:** You are the *only* agent allowed to directly interact with the human user. Use the `ask_user` tool to get input/requests and the `send_message_to_user` tool to deliver final, consolidated answers.
2.  **Coordination:** Use the Coral communication tools (`list`, `send`, `wait_for_mentions`) to discover and collaborate with other agents. Delegate tasks to specialized agents based on their capabilities (which you can infer from their IDs or by asking them).
3.  **Information Gathering:** Ensure information comes from reliable sources (other agents using their tools) or the user. Do not guess. Verify calculations or complex information with appropriate agents.
4.  **Registration:** Register yourself using the `register` tool with your exact ID: "{{my_agent_id}}".
5.  **Workflow:**
    *   If you don't have a user request, use `ask_user`.
    *   When you receive a request, use `list` to see available agents.
    *   Use `send` to delegate sub-tasks or ask questions to other agents.
    *   Use `wait_for_mentions` periodically within your loop to check for responses.
    *   Synthesize information received from other agents.
    *   Only when the task is fully complete and you have a final answer, use `send_message_to_user`. Do not send partial updates with this tool.

**Tool Guidelines:**
{{get_tools_description()}}
\'\'\'
    # Ensure SystemChatMessage is imported and used correctly
    system_message = sys_msg_content

    print("Creating OpenAI model...")
    try:
        model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O, # Or GPT_4_TURBO, make configurable if needed
            api_key=os.getenv("OPENAI_API_KEY"),
            model_config_dict={{ "temperature": 0.3 }},
        )
    except Exception as model_err:
        print(f"Fatal Error: Failed to create OpenAI model: {{model_err}}")
        sys.exit(1)

    print("Creating ChatAgent instance...")
    camel_agent = ChatAgent(
        system_message=system_message,
        model=model,
        tools=tools,
        # message_window_size=4096 * 50, # Consider making configurable
        # token_limit=20000
    )
    print("Interface agent created.")
    return camel_agent


if __name__ == "__main__":
    print("Starting Interface Agent script...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interface Agent stopped by user.")
    finally:
        print("Interface Agent script finished.")

''' # End of the main f-string
    return script_content