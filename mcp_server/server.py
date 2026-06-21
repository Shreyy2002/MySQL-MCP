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

# =========================================================================
# HELPER
# =========================================================================
async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}{path}", headers=HEADERS, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API error {e.response.status_code}: {e.response.text}"}
        except httpx.RequestError as e:
            return {"error": f"Cannot connect to SRE API at {API_BASE_URL}: {str(e)}"}

async def _post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{API_BASE_URL}{path}", headers=HEADERS, json=body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API error {e.response.status_code}: {e.response.text}"}
        except httpx.RequestError as e:
            return {"error": f"Cannot connect to SRE API at {API_BASE_URL}: {str(e)}"}

# =========================================================================
# TOOL: DB STATUS
# =========================================================================
@mcp.tool()
async def get_db_status() -> dict:
    """
    Get a quick snapshot of the MySQL database: version, uptime in seconds,
    and number of currently connected threads.

    Use this for a fast health check. For deeper metrics (buffer pool, connection
    limits, slow query counters), use get_database_vitals() instead.
    """
    return await _get("/sre/db-status")

# =========================================================================
# TOOL: ACTIVE QUERIES (formerly get_slow_queries)
# =========================================================================
@mcp.tool()
async def get_active_queries() -> dict:
    """
    Get ALL currently running (non-sleeping) queries from MySQL PROCESSLIST.

    Returns columns: Id, User, Host, db, Command, Time (seconds), State, Info (query text).

    Use this for real-time visibility into what is running RIGHT NOW.
    To find which queries are HISTORICALLY slow over time, use get_top_slow_queries() instead.

    After identifying a stuck query here, note its 'Id' and pass it to kill_query() to terminate it.
    """
    return await _get("/sre/active-queries")

# =========================================================================
# TOOL: TABLE SIZES
# =========================================================================
@mcp.tool()
async def get_table_sizes() -> dict:
    """
    Get estimated disk sizes (in MB) for all tables in the database.

    WARNING: The 'rows_approx' column contains InnoDB statistics estimates —
    they can be wildly inaccurate (e.g., showing 22 instead of 1,000,000).
    For exact row counts, ALWAYS use get_exact_row_count(table_name) instead.

    The 'size_mb' column IS accurate and useful for capacity planning.
    """
    return await _get("/sre/table-sizes")

# =========================================================================
# TOOL: EXACT ROW COUNT
# =========================================================================
@mcp.tool()
async def get_exact_row_count(table_name: str) -> dict:
    """
    Get the EXACT, real-time row count for a specific table via SELECT COUNT(*).

    ALWAYS use this tool when the user asks 'how many rows', 'count the rows',
    or 'how many records' — because get_table_sizes() only provides inaccurate
    InnoDB estimates that can be orders of magnitude off.

    Args:
        table_name: The exact name of the table to count (e.g. 'request_logs').
    """
    return await _get(f"/sre/exact-row-count/{table_name}")

# =========================================================================
# TOOL: KILL QUERY
# =========================================================================
@mcp.tool()
async def kill_query(process_id: int) -> dict:
    """
    Kill a specific MySQL query process by its process ID.

    DANGER: This immediately terminates an active connection or transaction.
    Use ONLY when a query is confirmed to be stuck, causing an outage, or holding locks.

    WORKFLOW: First call get_active_queries() to see running processes and note the 'Id'
    of the stuck query. Then call this tool with that 'Id'.

    Safety: This tool will REFUSE to kill root or system-level processes.

    Args:
        process_id: The process ID to kill (the 'Id' field from get_active_queries).
    """
    return await _post(f"/sre/kill-query/{process_id}", {})

# =========================================================================
# TOOL: DATABASE VITALS
# =========================================================================
@mcp.tool()
async def get_database_vitals() -> dict:
    """
    Get comprehensive database health vitals including:
    - Uptime, Threads_connected, Threads_running
    - Total Connections, Questions (total queries executed), Slow_queries count
    - InnoDB buffer pool hit ratio indicators (Innodb_buffer_pool_reads vs read_requests)
    - Configuration: max_connections, innodb_buffer_pool_size, slow_query_log status

    Use this for a deep health assessment. For a quick version/uptime snapshot,
    use get_db_status() instead.

    Key things to look for:
    - Threads_running close to max_connections = connection pressure
    - Innodb_buffer_pool_reads high relative to read_requests = buffer pool too small
    - Slow_queries count growing = query performance degradation
    """
    return await _get("/sre/vitals")

# =========================================================================
# TOOL: ACTIVE LOCKS & BLOCKS
# =========================================================================
@mcp.tool()
async def get_active_locks_and_blocks() -> dict:
    """
    Investigate active InnoDB deadlocks and lock wait chains.

    Returns pairs of (waiting_query, blocking_query) with their transaction IDs,
    thread IDs, query text, and how long the blocking transaction has been running.

    An empty 'locks' list means there are no active lock conflicts.

    Use this when:
    - Queries are hanging or timing out unexpectedly
    - You suspect a long-running transaction is blocking others
    - Applications report deadlock errors

    If you find a blocking transaction, note its blocking_thread and use
    kill_query() with that thread ID to release the lock.
    """
    return await _get("/sre/locks")

# =========================================================================
# TOOL: TOP SLOW QUERIES (historical)
# =========================================================================
@mcp.tool()
async def get_top_slow_queries(limit: int) -> dict:
    """
    Get the historically slowest query patterns from performance_schema.
    This is HISTORICAL data aggregated since the server last restarted — not live queries.

    Returns columns: query_pattern (normalized SQL), exec_count, avg_latency_s,
    max_latency_s, total_latency_s.

    Use this for query optimization and identifying which queries need indexes.

    Key insight: high avg_latency_s + high exec_count = highest priority to optimize.

    For real-time running queries, use get_active_queries() instead.

    Args:
        limit: Number of slow query patterns to return (1-100, default 10).
    """
    return await _get("/sre/top-slow-queries", params={"limit": limit})

# =========================================================================
# TOOL: EXPLAIN QUERY PLAN
# =========================================================================
@mcp.tool()
async def explain_query_plan(sql_query: str) -> dict:
    """
    Run EXPLAIN FORMAT=JSON on a SQL query to analyze its execution plan.

    Returns a JSON plan showing how MySQL will execute the query, including:
    - access_type: 'ALL' means a full table scan (missing index — bad for large tables)
    - key: which index MySQL chose to use
    - rows: estimated number of rows examined
    - filtered: percentage of rows passing WHERE conditions

    Use this AFTER finding a slow query from get_top_slow_queries() or get_active_queries()
    to understand WHY it is slow and whether it needs a new index.

    RULES for sql_query argument:
    - Must be a single SELECT, INSERT, UPDATE, or DELETE statement
    - No semicolons allowed
    - No DDL (CREATE, DROP, ALTER) or admin commands

    Args:
        sql_query: A single SQL SELECT/INSERT/UPDATE/DELETE statement to analyze.
    """
    return await _post("/sre/explain", {"sql_query": sql_query})

# =========================================================================
# TOOL: TABLE ARCHITECTURE
# =========================================================================
@mcp.tool()
async def get_table_architecture(table_name: str) -> dict:
    """
    Get the complete schema definition and index structure for a specific table.

    Returns:
    - schema: The full CREATE TABLE statement including column types, constraints, charset
    - indexes: All defined indexes including PRIMARY KEY, UNIQUE, and secondary indexes

    Use this when:
    - Investigating whether a slow query is missing an index
    - Understanding column data types for query optimization
    - Auditing foreign key relationships and constraints

    After reviewing indexes, use explain_query_plan() on the specific slow query to
    confirm whether the correct index is being used.

    Args:
        table_name: The exact name of the table (e.g. 'request_logs').
    """
    return await _get(f"/sre/table-architecture/{table_name}")

# =========================================================================
# TOOL: LIST TABLES
# =========================================================================
@mcp.tool()
async def list_database_tables() -> dict:
    """
    Discover all tables in the sre_db database along with their engine and size in MB.

    Use this as your starting point when you don't know which tables exist.
    Then use get_table_architecture(table_name) on specific tables of interest.
    """
    return await _get("/sre/tables")

# =========================================================================
# TOOL: SERVER CONFIGURATION
# =========================================================================
@mcp.tool()
async def get_server_configuration(variable_name: str) -> dict:
    """
    Audit MySQL GLOBAL configuration variables in real-time.

    Supports LIKE wildcards to fetch groups of related settings:
    - 'max_connections' — maximum allowed connections
    - 'innodb_buffer_pool_size' — how much RAM InnoDB uses for caching
    - 'innodb_%' — all InnoDB-related settings (use % wildcard)
    - 'slow_query%' — slow query log configuration
    - 'query_cache%' — query cache settings
    - '%timeout%' — all timeout configurations

    Use this when diagnosing configuration-related performance issues,
    e.g., connection exhaustion (check max_connections vs Threads_connected in vitals).

    Args:
        variable_name: Exact variable name or LIKE pattern with '%' wildcards.
    """
    return await _get(f"/sre/config/{variable_name}")

if __name__ == "__main__":
    mcp.run()
