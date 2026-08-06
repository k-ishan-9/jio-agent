"""
api/main.py — FastAPI app exposing the agent as POST /ask, plus the
Jio-themed landing page (with floating chat widget) at GET /.

Run with:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import List, Optional

# Monkey-patch JSONEncoder to make bytes JSON-serializable (fixes ADK telemetry trace byte serialization bug)
_original_default = json.JSONEncoder.default
def _bytes_safe_default(self, o):
    if isinstance(o, bytes):
        try:
            return o.decode("utf-8")
        except UnicodeDecodeError:
            return o.hex()
    return _original_default(self, o)
json.JSONEncoder.default = _bytes_safe_default

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from google.genai.errors import ServerError

from config import MAX_RETRIES, verify_data_files_exist, INTERNAL_RELOAD_TOKEN
from retrieval import tools as retrieval_tools
from agent.adk_agent import root_agent
from agent.semantic_cache import semantic_cache
from agent.guardrails import evaluate_intent, rewrite_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jio_agent_api")

APP_NAME = "jio_agent_api"
USER_ID = "api_user"

app = FastAPI(title="Jio AI Agent API")

session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

STATIC_DIR = Path(__file__).parent.parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup():
    verify_data_files_exist()
    retrieval_tools.setup()
    logger.info("Jio AI Agent API startup complete")


@app.get("/", response_class=HTMLResponse)
async def landing_page():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/prepaid", response_class=HTMLResponse)
async def prepaid_page():
    return HTMLResponse((STATIC_DIR / "prepaid.html").read_text(encoding="utf-8"))


@app.get("/fiber", response_class=HTMLResponse)
async def fiber_page():
    return HTMLResponse((STATIC_DIR / "fiber.html").read_text(encoding="utf-8"))


@app.get("/business", response_class=HTMLResponse)
async def business_page():
    return HTMLResponse((STATIC_DIR / "business.html").read_text(encoding="utf-8"))


@app.get("/apps", response_class=HTMLResponse)
async def apps_page():
    return HTMLResponse((STATIC_DIR / "apps.html").read_text(encoding="utf-8"))


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    session_id: Optional[str] = None


class SourceItem(BaseModel):
    title: str
    url: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    tool_used: str  # "sql" | "vector" | "both" | "none"
    session_id: str


TOOL_NAME_TO_KIND = {"find_jio_plans": "sql", "search_jio_faq_and_info": "vector"}
ACTIVE_SESSIONS = set()
SESSION_CONTEXTS = {}


async def run_agent_query(question: str, session_id: str) -> AskResponse:
    if session_id not in ACTIVE_SESSIONS:
        await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
        ACTIVE_SESSIONS.add(session_id)
        
    content = genai_types.Content(role="user", parts=[genai_types.Part(text=question)])
    tools_called, sources, final_text = set(), [], None

    for attempt in range(MAX_RETRIES):
        try:
            tools_called.clear(); sources.clear(); final_text = None
            events = runner.run_async(user_id=USER_ID, session_id=session_id, new_message=content)

            async for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        fc = getattr(part, "function_call", None)
                        if fc is not None:
                            tools_called.add(fc.name)
                        fr = getattr(part, "function_response", None)
                        if fr is not None and isinstance(fr.response, dict):
                            for item in (fr.response.get("plans") or fr.response.get("results") or []):
                                if isinstance(item, dict) and item.get("url"):
                                    sources.append(SourceItem(title=item.get("title", "source"), url=item["url"]))
                if event.is_final_response():
                    if event.content and event.content.parts:
                        final_text = event.content.parts[0].text

            if final_text is not None:
                break
            raise RuntimeError("Agent returned an empty final response")

        except (ServerError, RuntimeError) as e:
            if attempt == MAX_RETRIES - 1:
                logger.error(f"Agent call failed after {MAX_RETRIES} attempts: {e}")
                raise HTTPException(status_code=503, detail="The AI model is temporarily unavailable.")
            wait = 2 ** attempt * 3
            logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} failed: {e} — retrying in {wait}s")
            await asyncio.sleep(wait)

    if len(tools_called) == 2:
        tool_used = "both"
    elif len(tools_called) == 1:
        tool_used = TOOL_NAME_TO_KIND.get(next(iter(tools_called)), "unknown")
    else:
        tool_used = "none"

    seen, deduped_sources = set(), []
    for s in sources:
        if s.url not in seen:
            seen.add(s.url); deduped_sources.append(s)

    return AskResponse(answer=final_text, sources=deduped_sources, tool_used=tool_used, session_id=session_id)


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    start = time.time()
    session_id = request.session_id or str(uuid.uuid4())
    try:
        # 1. Check Semantic Cache FIRST on raw query (avoids Gemini API calls on cache hits!)
        cached_result = semantic_cache.lookup(request.question)
        if cached_result:
            # Save query and cached answer to context history
            if session_id not in SESSION_CONTEXTS:
                SESSION_CONTEXTS[session_id] = []
            SESSION_CONTEXTS[session_id].append({"role": "user", "content": request.question})
            SESSION_CONTEXTS[session_id].append({"role": "model", "content": cached_result["answer"]})
            if len(SESSION_CONTEXTS[session_id]) > 8:
                SESSION_CONTEXTS[session_id] = SESSION_CONTEXTS[session_id][-8:]

            elapsed = time.time() - start
            logger.info(f"question={request.question!r} CACHE_HIT elapsed={elapsed:.4f}s")
            return AskResponse(
                answer=cached_result["answer"],
                sources=[SourceItem(title=s["title"], url=s["url"]) for s in cached_result["sources"]],
                tool_used=cached_result["tool_used"],
                session_id=session_id
            )

        # 2. Cache Miss - Evaluate intent guardrails with history context
        history = SESSION_CONTEXTS.get(session_id, [])
        is_safe, refusal = evaluate_intent(request.question, history)
        if not is_safe:
            elapsed = time.time() - start
            logger.info(f"question={request.question!r} BLOCKED elapsed={elapsed:.4f}s")
            return AskResponse(answer=refusal, sources=[], tool_used="none", session_id=session_id)

        # 3. Rewrite query for optimal RAG retrieval
        optimized_query = rewrite_query(request.question)

        # 4. Run RAG agent query using the raw question to preserve natural follow-ups in chat history
        # (The ADK agent automatically retrieves database filters from the conversation context)
        response = await run_agent_query(request.question, session_id)

        # Save successful turn to context history
        if response.answer and "Error:" not in response.answer:
            if session_id not in SESSION_CONTEXTS:
                SESSION_CONTEXTS[session_id] = []
            SESSION_CONTEXTS[session_id].append({"role": "user", "content": request.question})
            SESSION_CONTEXTS[session_id].append({"role": "model", "content": response.answer})
            if len(SESSION_CONTEXTS[session_id]) > 8:
                SESSION_CONTEXTS[session_id] = SESSION_CONTEXTS[session_id][-8:]

        # 5. Save successful result to Semantic Cache under the ORIGINAL raw query
        if response.answer and "Error:" not in response.answer:
            semantic_cache.add(
                request.question,
                response.answer,
                response.tool_used,
                [{"title": s.title, "url": s.url} for s in response.sources]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error handling question: {request.question!r}")
        raise HTTPException(status_code=500, detail="Internal server error") from e

    elapsed = time.time() - start
    logger.info(f"question={request.question!r} tool_used={response.tool_used} "
                f"sources={len(response.sources)} elapsed={elapsed:.2f}s")
    return response


class ReloadRequest(BaseModel):
    token: str


@app.post("/internal/reload-index")
async def reload_index(req: ReloadRequest):
    if req.token != INTERNAL_RELOAD_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid reload token")
    success = retrieval_tools.reload_faiss_index()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reload FAISS index")
    return {"status": "success", "message": "FAISS index reloaded into memory"}


@app.get("/health")
async def health():
    return {"status": "ok"}
