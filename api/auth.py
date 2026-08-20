"""
api/auth.py — optional API-key auth for POST /ask.

Kept opt-in (via the API_KEY env var) rather than mandatory: the project
ships with no key configured by default so local/demo usage is unaffected,
but a real deployment can set API_KEY and every request must then present
it via the X-API-Key header.
"""

from fastapi import Header, HTTPException

from config import API_KEY


async def require_api_key(x_api_key: str = Header(default="")):
    if not API_KEY:
        return  # auth disabled — no key configured
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
