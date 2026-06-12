from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any

from .database import get_db
from .security import get_api_key

app = FastAPI(title="SRE Observability API", version="1.0.0")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/sre/db-status", dependencies=[Depends(get_api_key)])
def get_db_status(db: Session = Depends(get_db)):
    """Get general database status and global variables."""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sre/slow-queries", dependencies=[Depends(get_api_key)])
def get_slow_queries(db: Session = Depends(get_db)):
    """Get currently running queries that might be slow or stuck."""
    try:
        # Avoid showing sleeping connections if possible, but PROCESSLIST is good for SRE
        result = db.execute(text("SHOW FULL PROCESSLIST"))
        queries = []
        for row in result:
            # SQLAlchemy 2.0 Row proxy handles as tuple/dict
            row_dict = row._mapping if hasattr(row, '_mapping') else dict(row)
            if row_dict.get('Command') != 'Sleep':
                queries.append(dict(row_dict))
        return {"active_queries": queries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sre/table-sizes", dependencies=[Depends(get_api_key)])
def get_table_sizes(db: Session = Depends(get_db)):
    """Get the size of all tables in the database for capacity planning."""
    try:
        query = text(\"\"\"
            SELECT 
                table_schema AS 'database',
                table_name AS 'table',
                ROUND((data_length + index_length) / 1024 / 1024, 2) AS 'size_mb',
                table_rows AS 'rows'
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
            ORDER BY (data_length + index_length) DESC;
        \"\"\")
        result = db.execute(query)
        tables = [dict(row._mapping if hasattr(row, '_mapping') else row) for row in result]
        return {"tables": tables}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sre/kill-query/{process_id}", dependencies=[Depends(get_api_key)])
def kill_query(process_id: int, db: Session = Depends(get_db)):
    """Kill a specific query by its process ID. Use with caution!"""
    try:
        # Only users with PROCESS or SUPER privilege can kill other users' processes
        db.execute(text(f"KILL {process_id}"))
        return {"status": "success", "message": f"Process {process_id} killed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
