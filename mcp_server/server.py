import os
import httpx
from mcp.server.fastmcp import FastMCP

# Define the FastMCP server
mcp = FastMCP("sre-observability-server")

# Configuration for reaching the API
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "sre-secret-key-12345")

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

@mcp.tool()
async def get_db_status() -> dict:
    """
    Get the general status and metrics of the MySQL database.
    Useful for checking version, uptime, and currently connected threads.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/sre/db-status", headers=HEADERS)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API returned error: {e.response.status_code} - {e.response.text}"}
        except httpx.RequestError as e:
            return {"error": f"Failed to connect to API: {str(e)}"}

@mcp.tool()
async def get_slow_queries() -> dict:
    """
    Get a list of currently active or slow queries running in the MySQL database.
    Useful for troubleshooting performance issues or finding stuck queries.
    Returns the process ID, user, host, command, time, state, and query text.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/sre/slow-queries", headers=HEADERS)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API returned error: {e.response.status_code} - {e.response.text}"}
        except httpx.RequestError as e:
            return {"error": f"Failed to connect to API: {str(e)}"}

@mcp.tool()
async def get_table_sizes() -> dict:
    """
    Get the sizes of all tables in the database in MB along with row counts.
    Useful for capacity planning and finding unexpectedly large tables.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/sre/table-sizes", headers=HEADERS)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API returned error: {e.response.status_code} - {e.response.text}"}
        except httpx.RequestError as e:
            return {"error": f"Failed to connect to API: {str(e)}"}

@mcp.tool()
async def kill_query(process_id: int) -> dict:
    """
    Kill a specific MySQL query process by its ID.
    DANGER: Use with caution as it terminates active connections/transactions.
    To be used only when a query is confirmed to be stuck or causing an outage.
    
    Args:
        process_id: The ID of the process to kill (obtained from get_slow_queries).
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{API_BASE_URL}/sre/kill-query/{process_id}", headers=HEADERS)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API returned error: {e.response.status_code} - {e.response.text}"}
        except httpx.RequestError as e:
            return {"error": f"Failed to connect to API: {str(e)}"}

if __name__ == "__main__":
    # When run directly, start the FastMCP server
    mcp.run()
