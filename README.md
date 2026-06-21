# SRE Observability MCP Server

This repository contains an implementation of a Site Reliability Engineering (SRE) observability tool using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io). It features a 3-tier architecture:

1. **MySQL Database**: Stores service statuses, query data, and schema information.
2. **FastAPI Layer**: An intermediate backend that securely connects to the database and exposes specific SRE endpoints (e.g., getting DB health, slow queries, and killing queries).
3. **MCP Server**: A Python FastMCP server that connects to the FastAPI backend via an API Key. This server provides tools for LLMs/AI assistants to query SRE data.

## Architecture

```text
+--------------+       +---------------+       +-----------------+
| Streamlit UI |       |               |       |                 |
| (MCP Client) |<----->|  MCP Server   |<----->|  FastAPI Layer  |<-----> MySQL DB
|  (Python)    |       |  (Python)     | API   |  (Python)       |
|              |       |               | Key   |                 |
+--------------+       +---------------+       +-----------------+
```

## Setup & Local Development

### 1. Database

We use a local MySQL instance configured via `docker-compose.yml`.

```bash
docker compose up -d
```
This will start MySQL on port `3306` and initialize the schema with dummy data from `init.sql`.

### 2. FastAPI Backend

Install dependencies:
```bash
cd api
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

Run the server:
```bash
# Uses the default API_KEY: sre-secret-key-12345
fastapi dev main.py --port 8000
```

### 3. MCP Server

Install dependencies:
```bash
cd mcp_server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

To run the MCP server in development mode (using the MCP Inspector):
```bash
mcp dev server.py
```
Or to run it directly:
```bash
python server.py
```

### 4. Streamlit UI (Chatbot)

Install dependencies:
```bash
cd ui
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run the web application:
```bash
streamlit run app.py
```

## Security Best Practices Implemented

- **API Key Authentication**: The FastAPI endpoints are protected by an `X-API-Key` header dependency. The MCP server stores this key as an environment variable and injects it into every request.
- **Principle of Least Privilege**: The intermediate API layer prevents the LLM/MCP client from sending raw, arbitrary SQL queries to the database. Only pre-defined, safe queries (like checking table sizes or viewing the processlist) are exposed.
- **Environment Variables**: Sensitive data like DB passwords and API keys are read from environment variables.

## Tools Exposed

The MCP Server exposes the following SRE tools:
- `get_db_status`: Get version, uptime, and thread counts.
- `get_slow_queries`: View active connections and long-running queries via `SHOW FULL PROCESSLIST`.
- `get_table_sizes`: Inspect table sizes for capacity planning.
- `kill_query(process_id)`: A remediation tool to terminate a stuck connection or long-running query.
