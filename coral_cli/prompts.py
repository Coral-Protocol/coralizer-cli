def get_tools_description():
    return """
    - Use the chat tool to communicate with other agents. The message should be clear and concise.
    - Use the ask_user tool to get input from the user when needed.
    - Use the send_final_response tool to send the final response to the user.
    - Use the list_agents tool to see what other agents are available.
    - Use the list_messages tool to see recent messages from other agents.
    """

def get_user_message():
    return "What's the next step?"