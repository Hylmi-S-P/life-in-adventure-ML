"""
response_cache.py - LRU + TTL response cache with disk persistence.
Caches AI evaluation results and RAG retrieval results so that identical
queries (same event + player stats or same OCR text + language) don't
re-execute the full pipeline. Survives app restarts via JSON persistence.
"""

import os
import time
import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any, Optional
import loguru

logger = loguru.logger


class ResponseCache:
    """
    OrderedDict-based LRU cache with TTL, optional JSON persistence, and thread safety.

    Usage:
        cache = ResponseCache(maxsize=500, ttl=3600, persist_path="data/ai_eval_cache.json")
        key = cache.make_key(event_key, player_stats)
        if (val := cache.get(key)) is not None:
            return val          # cache hit
        val = expensive_call()
        cache.set(key, val)
        return val
    """

    def __init__(
        self,
        maxsize: int = 500,
        ttl: float = 3600.0,
        persist_path: Optional[str] = None,
    ):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._persist_path = persist_path
        self._lock = threading.Lock()
        if persist_path and os.path.exists(persist_path):
            self._load()

    @staticmethod
    def make_key(*parts: Any) -> str:
        """Deterministic hash key from arbitrary args."""
        raw = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, key: str) -> Optional[Any]:
        """Return cached value if fresh, else None. Thread-safe."""
        with self._lock:
            if key not in self._cache:
                return None
            val, ts = self._cache[key]
            if time.time() - ts < self._ttl:
                self._cache.move_to_end(key)
                return val
            del self._cache[key]
            return None

    def set(self, key: str, val: Any) -> None:
        """Store a value with current timestamp. Thread-safe."""
        with self._lock:
            self._cache[key] = (val, time.time())
            self._cache.move_to_end(key)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def _load(self) -> None:
        """Load persisted cache from JSON, discarding expired entries."""
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            pruned = 0
            for k, entry in data.items():
                # entry is a JSON array [value, timestamp] — not a tuple.
                # Older versions used tuples serialized via default=str (broken).
                if not isinstance(entry, list) or len(entry) != 2:
                    pruned += 1
                    continue
                v, ts = entry[0], float(entry[1])
                if now - ts < self._ttl:
                    self._cache[k] = (v, ts)
                else:
                    pruned += 1
            logger.info(f"ResponseCache loaded {len(self._cache)} entries from {self._persist_path}")
            if pruned > 0:
                self.save()  # prune expired/broken entries from disk
        except Exception as e:
            logger.debug(f"ResponseCache load failed (safe to ignore): {e}")

    def save(self) -> None:
        """Persist current cache to JSON. Thread-safe.
        Values are stored as [value, timestamp] lists (JSON arrays) to avoid
        the tuple-serialization problem where default=str converts tuples to
        non-deserializable string representations.
        """
        if not self._persist_path:
            return
        try:
            with self._lock:
                os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
                # Serialize as {key: [value, timestamp]} — JSON arrays, not tuples.
                serializable = {k: [v, ts] for k, (v, ts) in self._cache.items()}
                with open(self._persist_path, "w", encoding="utf-8") as f:
                    json.dump(serializable, f, default=str, indent=2)
                logger.debug(f"ResponseCache saved {len(self._cache)} entries.")
        except Exception as e:
            logger.warning(f"ResponseCache save failed: {e}")

    def clear(self) -> None:
        """Clear all cached entries. Thread-safe."""
        with self._lock:
            self._cache.clear()
