# pyrefly: ignore[missing-import]
from fastapi import FastAPI, Depends, HTTPException, Body
# pyrefly: ignore[missing-import]
from pydantic import BaseModel, field_validator
# pyrefly: ignore[missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore[missing-import]
from sqlalchemy import text
from typing import List, Dict, Any
import logging

from database import get_db
from security import get_api_key

# =========================================================================
# LOGGING — log full internal errors, return generic messages to callers
# =========================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sre-api")

app = FastAPI(title="SRE Observability API", version="1.0.0")

# =========================================================================
# HEALTH
# =========================================================================
@app.get("/health")
def health_check():
    return {"status": "ok"}

# =========================================================================
# DB STATUS — quick snapshot
# =========================================================================
@app.get("/sre/db-status", dependencies=[Depends(get_api_key)])
def get_db_status(db: Session = Depends(get_db)):
    """Get general database status: version, uptime, connected threads."""
    try:
        version = db.execute(text("SELECT VERSION()")).scalar()
        uptime = db.execute(text("SHOW GLOBAL STATUS LIKE 'Uptime'")).fetchone()
        threads = db.execute(text("SHOW GLOBAL STATUS LIKE 'Threads_connected'")).fetchone()
        return {
            "version": version,
            "uptime_seconds": int(uptime[1]) if uptime else None,
            "threads_connected": int(threads[1]) if threads else None,
            "status": "healthy"
        }
    except Exception as e:
        logger.error("get_db_status failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch DB status. Check server logs.")

# =========================================================================
# ACTIVE QUERIES (renamed from slow_queries — shows ALL active non-sleeping)
# =========================================================================
@app.get("/sre/active-queries", dependencies=[Depends(get_api_key)])
def get_active_queries(db: Session = Depends(get_db)):
    """Get all currently active (non-sleeping) queries from PROCESSLIST."""
    try:
        result = db.execute(text("SHOW FULL PROCESSLIST"))
        queries = []
        for row in result:
            row_dict = row._mapping if hasattr(row, '_mapping') else dict(row)
            if row_dict.get('Command') != 'Sleep':
                queries.append(dict(row_dict))
        return {"active_queries": queries}
    except Exception as e:
        logger.error("get_active_queries failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch active queries. Check server logs.")

# =========================================================================
# TABLE SIZES (approximate — InnoDB estimates)
# =========================================================================
@app.get("/sre/table-sizes", dependencies=[Depends(get_api_key)])
def get_table_sizes(db: Session = Depends(get_db)):
    """Get estimated sizes and row counts for all tables."""
    try:
        query = text("""
            SELECT 
                table_schema AS 'database',
                table_name AS 'table',
                ROUND((data_length + index_length) / 1024 / 1024, 2) AS 'size_mb',
                table_rows AS 'rows_approx'
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
            ORDER BY (data_length + index_length) DESC;
        """)
        result = db.execute(query)
        tables = [dict(row._mapping if hasattr(row, '_mapping') else row) for row in result]
        return {"tables": tables, "note": "Row counts are InnoDB estimates and may be inaccurate. Use /sre/exact-row-count for precise counts."}
    except Exception as e:
        logger.error("get_table_sizes failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch table sizes. Check server logs.")

# =========================================================================
# EXACT ROW COUNT
# =========================================================================
@app.get("/sre/exact-row-count/{table_name}", dependencies=[Depends(get_api_key)])
def get_exact_row_count(table_name: str, db: Session = Depends(get_db)):
    """Get precise real-time row count for a specific table via SELECT COUNT(*)."""
    if not table_name.isidentifier():
        raise HTTPException(status_code=400, detail="Invalid table name. Must be a valid SQL identifier.")
    try:
        count = db.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()
        return {"table": table_name, "exact_row_count": count}
    except Exception as e:
        logger.error("get_exact_row_count failed for table '%s': %s", table_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to count rows. Check server logs.")

# =========================================================================
# KILL QUERY — with process ownership validation
# =========================================================================
@app.post("/sre/kill-query/{process_id}", dependencies=[Depends(get_api_key)])
def kill_query(process_id: int, db: Session = Depends(get_db)):
    """Kill a MySQL process by ID. Refuses to kill root or system processes."""
    try:
        # Safety check: inspect the process before killing it
        process_row = db.execute(
            text("SELECT User, Command FROM information_schema.PROCESSLIST WHERE ID = :pid"),
            {"pid": process_id}
        ).fetchone()

        if process_row is None:
            raise HTTPException(status_code=404, detail=f"Process {process_id} not found.")

        process_user = process_row[0] if process_row else None
        protected_users = {"root", "system user", "event_scheduler", "replica"}
        if process_user and process_user.lower() in protected_users:
            raise HTTPException(
                status_code=403,
                detail=f"Refusing to kill process owned by protected user '{process_user}'. This is a system-level process."
            )

        db.execute(text(f"KILL {process_id}"))
        logger.warning("SRE action: KILLED process_id=%s (user=%s)", process_id, process_user)
        return {"status": "success", "message": f"Process {process_id} (user: {process_user}) killed successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("kill_query failed for pid %s: %s", process_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to kill query. Check server logs.")

# =========================================================================
# DATABASE VITALS (parameterized — no string interpolation)
# =========================================================================
@app.get("/sre/vitals", dependencies=[Depends(get_api_key)])
def get_database_vitals(db: Session = Depends(get_db)):
    """Get core database health metrics: uptime, threads, connections, buffer pool."""
    try:
        metrics = {}
        # Use hardcoded safe variable names — no user input interpolated here
        status_vars = ["Uptime", "Threads_connected", "Threads_running",
                       "Connections", "Questions", "Slow_queries",
                       "Innodb_buffer_pool_reads", "Innodb_buffer_pool_read_requests"]
        for var in status_vars:
            res = db.execute(text("SHOW GLOBAL STATUS LIKE :var"), {"var": var}).fetchone()
            if res:
                metrics[res[0]] = res[1]

        config_vars = ["max_connections", "innodb_buffer_pool_size",
                       "innodb_log_file_size", "query_cache_size", "slow_query_log"]
        for var in config_vars:
            res = db.execute(text("SHOW GLOBAL VARIABLES LIKE :var"), {"var": var}).fetchone()
            if res:
                metrics[res[0]] = res[1]

        return {"vitals": metrics}
    except Exception as e:
        logger.error("get_database_vitals failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch vitals. Check server logs.")

# =========================================================================
# ACTIVE LOCKS & BLOCKS
# =========================================================================
@app.get("/sre/locks", dependencies=[Depends(get_api_key)])
def get_active_locks_and_blocks(db: Session = Depends(get_db)):
    """Investigate active deadlocks and lock waits between InnoDB transactions."""
    try:
        query = text("""
            SELECT
                r.trx_id                         AS waiting_trx_id,
                r.trx_mysql_thread_id            AS waiting_thread,
                r.trx_query                      AS waiting_query,
                b.trx_id                         AS blocking_trx_id,
                b.trx_mysql_thread_id            AS blocking_thread,
                b.trx_query                      AS blocking_query,
                b.trx_started                    AS blocking_trx_started,
                b.trx_rows_locked                AS blocking_rows_locked
            FROM performance_schema.data_lock_waits w
            INNER JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_engine_transaction_id
            INNER JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_engine_transaction_id;
        """)
        result = db.execute(query)
        locks = [dict(row._mapping if hasattr(row, '_mapping') else row) for row in result]
        return {"lock_count": len(locks), "locks": locks}
    except Exception as e:
        logger.error("get_active_locks_and_blocks failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch lock data. Check server logs.")

# =========================================================================
# TOP SLOW QUERIES (historical, from performance_schema) — capped at 100
# =========================================================================
@app.get("/sre/top-slow-queries", dependencies=[Depends(get_api_key)])
def get_top_slow_queries(limit: int = 10, db: Session = Depends(get_db)):
    """Get historically slowest queries from performance_schema digest table."""
    # Hard cap to prevent expensive queries against performance_schema
    limit = min(max(limit, 1), 100)
    try:
        query = text("""
            SELECT 
                SCHEMA_NAME,
                DIGEST_TEXT AS query_pattern,
                COUNT_STAR AS exec_count,
                ROUND(SUM_TIMER_WAIT / 1000000000000, 4) AS total_latency_s,
                ROUND(AVG_TIMER_WAIT / 1000000000000, 4) AS avg_latency_s,
                ROUND(MAX_TIMER_WAIT / 1000000000000, 4) AS max_latency_s
            FROM performance_schema.events_statements_summary_by_digest
            WHERE SCHEMA_NAME NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
              AND SCHEMA_NAME IS NOT NULL
            ORDER BY AVG_TIMER_WAIT DESC
            LIMIT :limit;
        """)
        result = db.execute(query, {"limit": limit})
        queries = [dict(row._mapping if hasattr(row, '_mapping') else row) for row in result]
        return {"slow_queries": queries}
    except Exception as e:
        logger.error("get_top_slow_queries failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch slow queries. Check server logs.")

# =========================================================================
# EXPLAIN QUERY PLAN — hardened against multi-statement injection
# =========================================================================
class ExplainRequest(BaseModel):
    sql_query: str

    @field_validator("sql_query")
    @classmethod
    def validate_sql(cls, v: str) -> str:
        stripped = v.strip()

        # Block any semicolons to completely prevent multi-statement injection
        if ";" in stripped:
            raise ValueError("Semicolons are not allowed in queries. Submit a single statement only.")

        # Only allow safe read-intent prefixes
        safe_prefixes = ("SELECT ", "UPDATE ", "DELETE ", "INSERT ")
        if not any(stripped.upper().startswith(p) for p in safe_prefixes):
            raise ValueError("Only SELECT, UPDATE, DELETE, or INSERT queries may be explained.")

        return stripped

@app.post("/sre/explain", dependencies=[Depends(get_api_key)])
def explain_query_plan(req: ExplainRequest, db: Session = Depends(get_db)):
    """Run EXPLAIN FORMAT=JSON on a validated SQL query to analyze its execution plan."""
    try:
        result = db.execute(text(f"EXPLAIN FORMAT=JSON {req.sql_query}")).scalar()
        return {"plan": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("explain_query_plan failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to explain query. Check server logs.")

# =========================================================================
# TABLE ARCHITECTURE
# =========================================================================
@app.get("/sre/table-architecture/{table_name}", dependencies=[Depends(get_api_key)])
def get_table_architecture(table_name: str, db: Session = Depends(get_db)):
    """Get the CREATE TABLE schema and all index definitions for a table."""
    if not table_name.isidentifier():
        raise HTTPException(status_code=400, detail="Invalid table name.")
    try:
        create_res = db.execute(text(f"SHOW CREATE TABLE `{table_name}`")).fetchone()
        schema = create_res[1] if create_res else ""
        idx_res = db.execute(text(f"SHOW INDEX FROM `{table_name}`"))
        indexes = [dict(row._mapping if hasattr(row, '_mapping') else row) for row in idx_res]
        return {"table": table_name, "schema": schema, "indexes": indexes}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_table_architecture failed for '%s': %s", table_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch table architecture. Check server logs.")

# =========================================================================
# LIST DATABASE TABLES
# =========================================================================
@app.get("/sre/tables", dependencies=[Depends(get_api_key)])
def list_database_tables(db: Session = Depends(get_db)):
    """Discover all tables in the sre_db database."""
    try:
        query = text("""
            SELECT table_name, table_type, engine, 
                   ROUND((data_length + index_length) / 1024 / 1024, 2) AS size_mb
            FROM information_schema.tables 
            WHERE table_schema = 'sre_db';
        """)
        result = db.execute(query)
        tables = [dict(row._mapping if hasattr(row, '_mapping') else row) for row in result]
        return {"tables": tables}
    except Exception as e:
        logger.error("list_database_tables failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list tables. Check server logs.")

# =========================================================================
# SERVER CONFIGURATION — parameterized LIKE query (no string interpolation)
# =========================================================================
@app.get("/sre/config/{variable_name}", dependencies=[Depends(get_api_key)])
def get_server_configuration(variable_name: str, db: Session = Depends(get_db)):
    """Audit MySQL GLOBAL variables. Supports LIKE wildcards e.g. 'innodb_%'."""
    # Validate: only allow alphanumeric, underscores, and the LIKE wildcard '%'
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_%")
    if not all(c in allowed_chars for c in variable_name):
        raise HTTPException(status_code=400, detail="Invalid variable name. Only alphanumeric, underscores, and '%' wildcards are allowed.")
    try:
        # Use bound parameter to prevent injection — SQLAlchemy escapes the value
        result = db.execute(text("SHOW GLOBAL VARIABLES LIKE :var"), {"var": variable_name})
        configs = [dict(row._mapping if hasattr(row, '_mapping') else row) for row in result]
        return {"configs": configs}
    except Exception as e:
        logger.error("get_server_configuration failed for '%s': %s", variable_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch configuration. Check server logs.")
