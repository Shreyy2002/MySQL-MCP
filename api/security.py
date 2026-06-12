import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

# Read API key from environment, default for local dev
API_KEY = os.getenv("API_KEY", "sre-secret-key-12345")
API_KEY_NAME = "X-API-Key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate API key"
        )
