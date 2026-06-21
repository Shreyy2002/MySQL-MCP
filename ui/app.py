import streamlit as st
import asyncio
import json
import os
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

# Load .env file from the root directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ==========================================
# 1. SETUP LLM CLIENT
# ==========================================
# We use the standard OpenAI client, which is perfectly compatible 
# with Groq, OpenRouter, and others using the base_url parameter.

# You can pass your Groq/OpenRouter key via environment variable, 
# or hardcode it here for local testing.
API_KEY = os.getenv("LLM_API_KEY", "") 
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
MODEL_NAME = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ==========================================
# 2. STREAMLIT UI SETUP
# ==========================================
st.set_page_config(page_title="SRE Observability Assistant", page_icon="🕵️", layout="centered")
st.title("🕵️ SRE Database Assistant")
st.markdown("Chat with the SRE assistant. It will automatically call the local MySQL MCP Server when needed.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "You are a highly skilled SRE assistant. Use the provided tools to query the MySQL database and diagnose issues. Always summarize the findings neatly."}
    ]

# Display chat history (skipping system prompt)
for msg in st.session_state.messages[1:]:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    elif msg["role"] == "assistant" and msg.get("content"):
        st.chat_message("assistant").write(msg["content"])
    elif msg["role"] == "tool":
        # Optionally show tool outputs in expanders
        with st.expander(f"Tool executed: {msg['name']}"):
            st.code(msg["content"])

# ==========================================
# 3. CORE MCP AND LLM LOOP
# ==========================================
async def process_chat(messages):
    """
    Connects to the local MCP server, provides tools to the LLM, 
    and handles tool execution.
    """
    server_params = StdioServerParameters(
        command="/home/shreytyagi/Documents/mcp-demo/mcp_server/start_server.sh",
        args=[],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # A. Fetch tools from our SRE MCP Server
            tools_response = await session.list_tools()
            
            # B. Format them into the standard OpenAI tool schema
            openai_tools = []
            for tool in tools_response.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })
            
            # C. Send user messages and tools to the LLM
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            # Ensure dictionary format for session state, excluding unset fields (like function_call=None)
            response_message_dict = response_message.model_dump(exclude_unset=True)
            
            # We must append the assistant's tool_calls message to history
            messages.append(response_message_dict)
            
            # D. Check if the LLM wants to execute a tool
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    st.toast(f"Executing MCP Tool: {function_name}...", icon="⚙️")
                    
                    # E. Execute the tool locally on the MCP server
                    result = await session.call_tool(function_name, arguments=function_args)
                    
                    # Extract the string content from the MCP result
                    tool_content = "\\n".join([item.text for item in result.content if hasattr(item, 'text')])
                    
                    # F. Append tool results to the chat history
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_content
                    })
                
                # G. Send the tool results back to the LLM for a final summary
                final_response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                )
                return final_response.choices[0].message.content, messages
            
            # No tools were called, just return the response
            return response_message.content, messages

# ==========================================
# 4. CHAT INPUT HANDLING
# ==========================================
if user_input := st.chat_input("Ask about the database status, slow queries, or table sizes..."):
    # Show user message immediately
    st.chat_message("user").write(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Process with LLM + MCP
    with st.spinner("Analyzing..."):
        try:
            # We run the async workflow inside Streamlit's sync environment
            final_text, updated_messages = asyncio.run(process_chat(st.session_state.messages))
            
            # Update session state with the entire interaction chain (including tool results)
            st.session_state.messages = updated_messages
            
            # Append and display the final textual response
            st.session_state.messages.append({"role": "assistant", "content": final_text})
            st.chat_message("assistant").write(final_text)
            
        except Exception as e:
            st.error(f"Error communicating with LLM or MCP Server: {str(e)}")
            st.info("Did you remember to set LLM_API_KEY in the code or environment?")
