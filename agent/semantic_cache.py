# agent/semantic_cache.py - Semantic Cache for Jio AI Agent

import json
import os
from pathlib import Path
import time
import faiss
import numpy as np
from google.genai import types

from config import DATA_ROOT, EMBEDDING_MODEL, EMBEDDING_DIM
from retrieval import tools as retrieval_tools

CACHE_INDEX_PATH = DATA_ROOT / "cache_faiss.index"
CACHE_META_PATH = DATA_ROOT / "cache_metadata.json"
CACHE_TTL_SECONDS = 86400  # Cache entries expire after 24 hours

class SemanticCache:
    def __init__(self, threshold=0.88):
        self.threshold = threshold
        self.index = None
        self.metadata = {}
        self._load_cache()

    def _load_cache(self):
        """Load cache FAISS index and metadata from disk, or initialize new ones."""
        if os.path.exists(CACHE_INDEX_PATH) and os.path.exists(CACHE_META_PATH):
            try:
                self.index = faiss.read_index(str(CACHE_INDEX_PATH))
                with open(CACHE_META_PATH, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                print(f"Loaded Semantic Cache: {self.index.ntotal} queries cached.")
            except Exception as e:
                print(f"Error loading cache files, reinitializing: {e}")
                self._initialize_empty_cache()
        else:
            self._initialize_empty_cache()

    def _initialize_empty_cache(self):
        """Create a new empty FAISS IP index of specified embedding dimensions."""
        self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self.metadata = {}
        print("Initialized new empty Semantic Cache.")

    def _save_cache(self):
        """Save FAISS index and metadata to disk."""
        try:
            faiss.write_index(self.index, str(CACHE_INDEX_PATH))
            with open(CACHE_META_PATH, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving semantic cache to disk: {e}")

    def _get_embedding(self, text: str) -> np.ndarray:
        """Helper to generate L2-normalized embedding for query text."""
        client = retrieval_tools.get_client()
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[text],
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
        )
        query_vec = np.array([result.embeddings[0].values], dtype="float32")
        faiss.normalize_L2(query_vec)
        return query_vec

    def lookup(self, query_text: str):
        """
        Check if a semantically similar query exists in cache.
        Returns (answer, tool_used, sources) if hit and not expired, else None.
        """
        if self.index.ntotal == 0:
            return None

        try:
            query_vec = self._get_embedding(query_text)
            # Search top 1
            scores, indices = self.index.search(query_vec, 1)
            
            best_score = float(scores[0][0])
            best_idx = int(indices[0][0])

            if best_idx != -1 and best_score >= self.threshold:
                match_meta = self.metadata.get(str(best_idx))
                if match_meta:
                    # Check TTL (Time-To-Live) expiration
                    cache_time = match_meta.get("timestamp", 0)
                    if time.time() - cache_time > CACHE_TTL_SECONDS:
                        print(f"Semantic Cache HIT but EXPIRED: age={time.time() - cache_time:.1f}s for matched_query='{match_meta['query']}'")
                        return None

                    print(f"Semantic Cache HIT: score={best_score:.4f} matched_query='{match_meta['query']}'")
                    return {
                        "answer": match_meta["answer"],
                        "tool_used": match_meta["tool_used"],
                        "sources": match_meta["sources"]
                    }
        except Exception as e:
            print(f"Error in semantic cache lookup: {e}")
        
        return None

    def add(self, query_text: str, answer_text: str, tool_used: str, sources: list):
        """Add a query and its final RAG answer/sources to the cache."""
        try:
            query_vec = self._get_embedding(query_text)
            new_idx = self.index.ntotal
            
            # Add embedding to index
            self.index.add(query_vec)
            
            # Save metadata
            self.metadata[str(new_idx)] = {
                "query": query_text,
                "answer": answer_text,
                "tool_used": tool_used,
                "sources": sources,
                "timestamp": time.time()
            }
            
            self._save_cache()
            print(f"Added query to Semantic Cache: '{query_text}' at index {new_idx}")
        except Exception as e:
            print(f"Error adding query to semantic cache: {e}")

    def clear(self):
        """Wipe all cached entries. Called after plan/FAQ re-ingestion so stale
        cached answers can never outlive the data they were generated from,
        instead of only being bounded by the 24h TTL."""
        self._initialize_empty_cache()
        self._save_cache()
        print("Semantic Cache cleared (data re-ingested).")

# Global singleton
semantic_cache = SemanticCache()
