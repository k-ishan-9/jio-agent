"""
config.py — Central configuration for the Jio AI Agent.

Reads secrets/paths from environment variables (loaded automatically from a
local .env file via python-dotenv) instead of Colab-specific mechanisms.

Required environment variables (set via .env — see .env.example):
    GOOGLE_API_KEY      — Gemini API key (embeddings + agent model)

Optional environment variables (sensible defaults provided):
    JIO_DATA_ROOT       — root folder containing jio_plans.db, jio_faiss_index/,
                           etc. Default: ./data (relative to project root)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from a .env file in the project root, if one exists.
load_dotenv()

# --- Required ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError(
        "GOOGLE_API_KEY environment variable is not set. "
        "Copy .env.example to .env and fill in your key, or set it directly "
        "in your shell before running."
    )

# --- Data paths ---
DATA_ROOT = Path(os.environ.get("JIO_DATA_ROOT", Path(__file__).parent / "data"))

CLEANED_DATA_PATH = DATA_ROOT / "all_jio_data_cleaned.json"
CHUNKED_DATA_PATH = DATA_ROOT / "all_jio_data_chunked.json"
SQLITE_DB_PATH = DATA_ROOT / "jio_plans.db"
FAISS_INDEX_DIR = DATA_ROOT / "jio_faiss_index"
FAISS_INDEX_PATH = FAISS_INDEX_DIR / "index.faiss"
FAISS_METADATA_PATH = FAISS_INDEX_DIR / "metadata.json"

RAW_DATA_DIR = DATA_ROOT / "raw_data"
FAQ_RAW_PATH = RAW_DATA_DIR / "faq_all.json"
BUSINESS_RAW_PATH = RAW_DATA_DIR / "business_pages.json"
APPS_RAW_PATH = RAW_DATA_DIR / "apps_cleaned.json"
ALL_URLS_PATH = DATA_ROOT / "all_jio_urls.txt"

# State hash files for change detection
PLAN_HASH_PATH = DATA_ROOT / "plan_hash.json"
FAQ_HASH_PATH = DATA_ROOT / "faq_hash.json"

# --- Celery & Background Jobs Config ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
INTERNAL_RELOAD_TOKEN = os.environ.get("INTERNAL_RELOAD_TOKEN", "secret-reload-token-jio")
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# --- API auth ---
# If unset, /ask is open (matches current default deployment); set it to
# require an X-API-Key header on every request.
API_KEY = os.environ.get("API_KEY", "")

# --- Session persistence ---
# ADK's InMemorySessionService loses all conversation history on process
# restart or when running multiple API instances. DatabaseSessionService
# persists sessions to SQLite (or any SQLAlchemy URL) so conversations
# survive restarts.
SESSIONS_DB_URL = os.environ.get("SESSIONS_DB_URL", f"sqlite:///{DATA_ROOT / 'sessions.db'}")

# --- Scraper target URLs ---
JIO_PLANS_URL = os.environ.get("JIO_PLANS_URL", "https://www.jio.com/mobile/prepaid-plans")
JIO_FAQ_URL = os.environ.get("JIO_FAQ_URL", "https://www.jio.com/help/faq")

# --- Model config ---
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768
AGENT_MODEL = "gemini-flash-latest"

# --- Retry / rate-limit tuning ---
MAX_RETRIES = 6
EMBEDDING_BATCH_SIZE = 20
EMBEDDING_SLEEP_BETWEEN_BATCHES = 6.0


def verify_data_files_exist():
    """Call at startup to fail fast with a clear message if data is missing."""
    required = {
        "SQLite plans db": SQLITE_DB_PATH,
        "FAISS index": FAISS_INDEX_PATH,
        "FAISS metadata": FAISS_METADATA_PATH,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required data files: {missing}. "
            f"Expected under JIO_DATA_ROOT={DATA_ROOT}. "
            f"Copy these over from your Colab/Drive build before running the API."
        )
