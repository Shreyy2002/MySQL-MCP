#!/bin/bash
# Wrapper script to easily launch the MCP server from Cursor or other clients

# Navigate to the mcp_server directory
cd /home/shreytyagi/Documents/mcp-demo/mcp_server

# Ensure the virtual environment exists, create it if it doesn't
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..." >&2
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt >&2
else
    source venv/bin/activate
fi

# Run the MCP server
python server.py
