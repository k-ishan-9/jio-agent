"""
tasks/pipeline.py — Celery tasks for plan and FAQ change checking, re-ingestion, FAISS index rebuilding, and API hot-reloading.
"""

import json
import logging
import sqlite3
import numpy as np
import faiss
import requests
from google import genai
from google.genai import types

from tasks.celery_app import app
from tasks.scrapers import (
    fetch_plans_signature,
    fetch_faq_signature,
    scrape_jio_plans,
    scrape_jio_faqs,
)
from config import (
    PLAN_HASH_PATH,
    FAQ_HASH_PATH,
    SQLITE_DB_PATH,
    FAISS_INDEX_PATH,
    FAISS_METADATA_PATH,
    GOOGLE_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    API_BASE_URL,
    INTERNAL_RELOAD_TOKEN,
)

logger = logging.getLogger("jio_pipeline")


def _read_stored_hash(hash_file) -> str:
    if hash_file.exists():
        try:
            with open(hash_file, "r", encoding="utf-8") as f:
                return json.load(f).get("hash", "")
        except Exception:
            return ""
    return ""


def _save_stored_hash(hash_file, hash_val: str):
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    with open(hash_file, "w", encoding="utf-8") as f:
        json.dump({"hash": hash_val}, f)


def _notify_api_reload():
    """Notify the FastAPI instance to reload FAISS index into memory."""
    try:
        url = f"{API_BASE_URL}/internal/reload-index"
        resp = requests.post(url, json={"token": INTERNAL_RELOAD_TOKEN}, timeout=5)
        logger.info(f"API hot-reload response: status={resp.status_code}, text={resp.text}")
    except Exception as e:
        logger.warning(f"Could not trigger API hot-reload at {API_BASE_URL}: {e}")


def _notify_cache_clear():
    """Notify the FastAPI instance to wipe its semantic cache, so a cached
    answer can never outlive the plan/FAQ data it was generated from — the
    24h TTL alone only bounds staleness, this eliminates it on every
    successful re-ingestion."""
    try:
        url = f"{API_BASE_URL}/internal/clear-cache"
        resp = requests.post(url, json={"token": INTERNAL_RELOAD_TOKEN}, timeout=5)
        logger.info(f"API cache-clear response: status={resp.status_code}, text={resp.text}")
    except Exception as e:
        logger.warning(f"Could not trigger API cache-clear at {API_BASE_URL}: {e}")


RETRY_POLICY = dict(
    autoretry_for=(Exception,),
    retry_backoff=True,       # exponential backoff between retries
    retry_backoff_max=600,    # cap at 10 minutes
    retry_jitter=True,
    max_retries=3,
)


@app.task(name="tasks.pipeline.check_plan_changes", **RETRY_POLICY)
def check_plan_changes():
    """Hourly task: checks if Jio plans page has changed."""
    logger.info("Executing hourly check_plan_changes task...")
    current_hash = fetch_plans_signature()
    stored_hash = _read_stored_hash(PLAN_HASH_PATH)

    if not current_hash:
        logger.warning("Could not fetch plan signature. Skipping re-ingestion.")
        return {"status": "skipped", "reason": "fetch_failed"}

    if current_hash != stored_hash:
        logger.info(f"Plan change detected! (stored={stored_hash[:8]}, current={current_hash[:8]}). Triggering reingest_plans...")
        reingest_plans.delay(current_hash)
        return {"status": "triggered", "new_hash": current_hash}
    
    logger.info("No plan changes detected.")
    return {"status": "no_change", "hash": current_hash}


@app.task(name="tasks.pipeline.reingest_plans", **RETRY_POLICY)
def reingest_plans(new_hash: str = ""):
    """Scrapes latest Jio plans and updates SQLite database."""
    logger.info("Executing reingest_plans task...")
    plans = scrape_jio_plans()
    if not plans:
        logger.warning("No plans scraped or scraping failed. Aborting database update.")
        return {"status": "failed", "reason": "empty_scraped_data"}

    # Update SQLite database
    conn = sqlite3.connect(str(SQLITE_DB_PATH))
    cur = conn.cursor()
    
    # Ensure table structure exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            section TEXT,
            category TEXT,
            price REAL,
            validity TEXT,
            data_gb REAL,
            speed_mbps REAL,
            subscriptions TEXT,
            description TEXT,
            url TEXT
        )
    """)

    # Upsert / insert scraped plans
    for p in plans:
        cur.execute("""
            INSERT OR REPLACE INTO plans 
            (title, section, category, price, validity, data_gb, speed_mbps, subscriptions, description, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p.get("title"), p.get("section"), p.get("category"),
            p.get("price"), p.get("validity"), p.get("data_gb"),
            p.get("speed_mbps"), p.get("subscriptions"),
            p.get("description"), p.get("url")
        ))
    
    conn.commit()
    conn.close()
    logger.info(f"Successfully updated SQLite jio_plans.db with {len(plans)} plans.")

    if new_hash:
        _save_stored_hash(PLAN_HASH_PATH, new_hash)

    _notify_api_reload()
    _notify_cache_clear()
    return {"status": "success", "count": len(plans)}


@app.task(name="tasks.pipeline.check_faq_changes", **RETRY_POLICY)
def check_faq_changes():
    """Weekly task: checks if Jio FAQ pages have changed."""
    logger.info("Executing weekly check_faq_changes task...")
    current_hash = fetch_faq_signature()
    stored_hash = _read_stored_hash(FAQ_HASH_PATH)

    if not current_hash:
        logger.warning("Could not fetch FAQ signature. Skipping re-ingestion.")
        return {"status": "skipped", "reason": "fetch_failed"}

    if current_hash != stored_hash:
        logger.info(f"FAQ change detected! (stored={stored_hash[:8]}, current={current_hash[:8]}). Triggering reingest_faq_content...")
        reingest_faq_content.delay(current_hash)
        return {"status": "triggered", "new_hash": current_hash}

    logger.info("No FAQ changes detected.")
    return {"status": "no_change", "hash": current_hash}


@app.task(name="tasks.pipeline.reingest_faq_content", **RETRY_POLICY)
def reingest_faq_content(new_hash: str = ""):
    """Scrapes FAQs, embeds with Gemini API, and rebuilds FAISS index."""
    logger.info("Executing reingest_faq_content task...")
    faqs = scrape_jio_faqs()
    if not faqs:
        logger.warning("No FAQ content scraped. Aborting vector index update.")
        return {"status": "failed", "reason": "empty_scraped_data"}

    # Generate embeddings via Google Gemini API
    client = genai.Client(api_key=GOOGLE_API_KEY)
    embeddings = []
    metadata = {}

    for idx, faq in enumerate(faqs):
        text_to_embed = f"{faq['title']}\n{faq['content']}"
        res = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[text_to_embed],
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
        )
        vec = np.array(res.embeddings[0].values, dtype="float32")
        embeddings.append(vec)
        metadata[str(idx)] = faq

    if not embeddings:
        return {"status": "failed", "reason": "no_embeddings_generated"}

    vectors = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(vectors)

    # Build FAISS Index
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(vectors)

    # Save to disk
    FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    with open(FAISS_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Rebuilt FAISS index with {index.ntotal} vectors at {FAISS_INDEX_PATH}")

    if new_hash:
        _save_stored_hash(FAQ_HASH_PATH, new_hash)

    _notify_api_reload()
    _notify_cache_clear()
    return {"status": "success", "vector_count": index.ntotal}
