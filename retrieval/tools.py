"""
retrieval/tools.py — the two retrieval tools (SQL + vector search).
"""

import asyncio
import json
import sqlite3
import threading

import faiss
import numpy as np
from google import genai
from google.genai import types

from config import (
    SQLITE_DB_PATH, FAISS_INDEX_PATH, FAISS_METADATA_PATH,
    GOOGLE_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM,
)

_client = None
_faiss_index = None
_faiss_metadata = None
_index_lock = threading.Lock()


def setup():
    """Load FAISS index + metadata into memory. Call once at process startup."""
    reload_faiss_index()


def reload_faiss_index():
    """Thread-safe reload of FAISS index + metadata from disk into memory."""
    global _faiss_index, _faiss_metadata
    if not FAISS_INDEX_PATH.exists() or not FAISS_METADATA_PATH.exists():
        print(f"Warning: FAISS index/metadata files do not exist yet at {FAISS_INDEX_PATH}")
        return False
    
    new_index = faiss.read_index(str(FAISS_INDEX_PATH))
    with open(FAISS_METADATA_PATH, "r", encoding="utf-8") as f:
        new_metadata = json.load(f)

    with _index_lock:
        _faiss_index = new_index
        _faiss_metadata = new_metadata

    print(f"Reloaded FAISS index into memory: {_faiss_index.ntotal} vectors, "
          f"{len(_faiss_metadata)} metadata entries")
    return True


def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


async def query_jio_plans(
    max_price=None, min_price=None, min_data=None, max_data=None,
    min_speed=None, section=None, category=None, validity=None,
    subscription=None, limit=20,
):
    """Query jio_plans.db with optional filters. Runs in a thread pool to avoid blocking."""
    def _run_query():
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        conditions, params = [], []
        if max_price is not None:
            conditions.append("price <= ?"); params.append(max_price)
        if min_price is not None:
            conditions.append("price >= ?"); params.append(min_price)
        if min_data is not None:
            conditions.append("data_gb >= ?"); params.append(min_data)
        if max_data is not None:
            conditions.append("data_gb <= ?"); params.append(max_data)
        if min_speed is not None:
            conditions.append("speed_mbps >= ?"); params.append(min_speed)
        if section is not None:
            conditions.append("section = ?"); params.append(section)
        if category is not None:
            conditions.append("category LIKE ?"); params.append(f"%{category}%")
        if validity is not None:
            conditions.append("validity LIKE ?"); params.append(f"%{validity}%")
        if subscription is not None:
            conditions.append("subscriptions LIKE ?"); params.append(f"%{subscription}%")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT title, section, category, price, validity, data_gb, speed_mbps,
                   subscriptions, description, url
            FROM plans {where_clause}
            ORDER BY price ASC LIMIT ?
        """
        params.append(limit)
        rows = cur.execute(sql, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    return await asyncio.to_thread(_run_query)


async def search_jio_knowledge(query, top_k=5, section_filter=None):
    """Embed query and search FAISS index. Runs blocking operations in thread pool."""
    client = get_client()

    def _get_embedding():
        result = client.models.embed_content(
            model=EMBEDDING_MODEL, contents=[query],
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
        )
        return np.array([result.embeddings[0].values], dtype="float32")

    query_vec = await asyncio.to_thread(_get_embedding)
    faiss.normalize_L2(query_vec)

    fetch_k = top_k * 5 if section_filter else top_k
    
    def _search_index():
        with _index_lock:
            if _faiss_index is None or _faiss_metadata is None:
                return np.array([]), np.array([])
            distances, indices = _faiss_index.search(query_vec, fetch_k)
            # Make a local copy of referenced metadata to release lock quickly
            metas = [dict(_faiss_metadata.get(str(idx), {})) if idx != -1 else {} for idx in indices[0]]
            return distances, indices, metas

    res = await asyncio.to_thread(_search_index)
    if len(res) < 3 or len(res[0]) == 0:
        return []
    distances, indices, metas = res

    results = []
    for score, idx, meta in zip(distances[0], indices[0], metas):
        if idx == -1 or not meta:
            continue
        if section_filter and meta.get("section") != section_filter:
            continue
        results.append({
            "score": float(score), "section": meta.get("section", ""),
            "category": meta.get("category", ""), "title": meta.get("title", ""),
            "content": meta.get("content", ""), "url": meta.get("url"),
        })
        if len(results) >= top_k:
            break
    return results
