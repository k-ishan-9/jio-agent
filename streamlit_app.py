"""
streamlit_app.py — Streamlit Community Cloud entrypoint.

Why this exists: this app needs ~420MB just to import (measured directly —
google-adk pulls in the entire Vertex AI SDK even though this project only
uses a plain Gemini API key, not Vertex AI). Every Docker-capable free,
card-free host tried (Render, Koyeb) caps at 512MB and OOMs. Streamlit
Community Cloud gives 1GB RAM free with no card, which actually fits.

This reuses the *exact* same pipeline as api/main.py's POST /ask — cache
lookup -> guardrail -> query rewrite -> ADK agent -> cache write — by
calling _process_ask() directly in-process instead of over HTTP. Nothing
about the agent/retrieval/guardrail/cache logic is duplicated or
reimplemented here.

Trade-off (documented, not hidden): this uses Streamlit's own chat UI
instead of the custom Jio-branded widget (static/widget.js). Voice
input/output and the SSE streaming typing effect from that widget aren't
wired up in this entrypoint — the FastAPI app (api/main.py) still has
all of that for whichever deployment target can afford the RAM for it.
"""

import asyncio
import logging
import uuid

import streamlit as st
from fastapi import HTTPException

from config import verify_data_files_exist
from retrieval import tools as retrieval_tools
from api.main import _process_ask, AskRequest

logger = logging.getLogger("jio_streamlit")

st.set_page_config(page_title="Jio AI Assistant", page_icon="📶", layout="centered")


@st.cache_resource
def _startup():
    """Runs exactly once per Streamlit process (cache_resource), mirroring
    what api/main.py's FastAPI @app.on_event("startup") handler does —
    that handler never fires here since we never run uvicorn."""
    verify_data_files_exist()
    retrieval_tools.setup()
    return True


_startup()

st.title("📶 Jio AI Assistant")
st.caption(
    "Hybrid RAG chatbot for Jio mobile, fiber, and business plans — "
    "grounded in real plan data (SQL) and FAQ content (vector search), never guessed."
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

TOOL_LABELS = {
    "sql": "🗄️ Source: Database Query",
    "vector": "🔍 Source: Document Search",
    "both": "🗄️🔍 Source: Hybrid DB + FAQ Search",
}


def _render_sources(sources: list):
    if not sources:
        return
    with st.expander(f"📎 {len(sources)} source(s)"):
        for s in sources:
            label = s["title"]
            if s.get("score") is not None:
                label += f" — {s['score'] * 100:.0f}% match"
            if s.get("url"):
                st.markdown(f"- [{label}]({s['url']})")
            else:
                st.markdown(f"- {label}")


# Replay chat history on every rerun (Streamlit reruns the whole script per interaction)
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if msg.get("tool_used") in TOOL_LABELS:
                st.caption(TOOL_LABELS[msg["tool_used"]])
            _render_sources(msg.get("sources", []))

question = st.chat_input("Ask about Jio plans, FAQs, or services...")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                request = AskRequest(question=question, session_id=st.session_state.session_id)
                response = asyncio.run(_process_ask(request))
        except HTTPException as e:
            # _process_ask raises HTTPException for FastAPI's benefit (it
            # normally converts this into a clean JSON error response) —
            # called directly here with no FastAPI request context, nothing
            # else catches it, so Streamlit's default behavior would dump
            # the raw traceback (including internal file paths) straight
            # into the chat UI. Show a clean message instead.
            logger.error(f"_process_ask raised HTTPException {e.status_code}: {e.detail}")
            answer = f"⚠️ {e.detail}" if e.status_code == 503 else "⚠️ Something went wrong processing that question. Please try again."
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer, "tool_used": None, "sources": []})
            st.stop()
        except Exception as e:
            logger.exception("Unexpected error in Streamlit chat handler")
            answer = "⚠️ Something went wrong processing that question. Please try again."
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer, "tool_used": None, "sources": []})
            st.stop()

        st.markdown(response.answer)
        if response.tool_used in TOOL_LABELS:
            st.caption(TOOL_LABELS[response.tool_used])

        sources = [
            {"title": s.title, "url": s.url, "score": s.score}
            for s in response.sources
        ]
        _render_sources(sources)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response.answer,
        "tool_used": response.tool_used,
        "sources": sources,
    })
