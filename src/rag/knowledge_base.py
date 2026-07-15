"""
knowledge_base.py - RAG Knowledge Base and Indexer for Life in Adventure.
Manages SQLite structured storage and hybrid (Vector + RapidFuzz + TF-IDF) indexing
over 19,341 Events, 377 Items, and 195 Monsters extracted from game assets.
"""

import os
import json
import sqlite3
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import loguru

logger = loguru.logger

try:
    from rapidfuzz import fuzz, process
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    _TFIDF_AVAILABLE = True
except ImportError:
    _TFIDF_AVAILABLE = False

try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    _CHROMADB_AVAILABLE = True
except ImportError:
    _CHROMADB_AVAILABLE = False

try:
    from llama_index.core import Document, VectorStoreIndex, StorageContext
    from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, FilterOperator
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.vector_stores.chroma import ChromaVectorStore
    _LLAMAINDEX_AVAILABLE = True
except ImportError:
    _LLAMAINDEX_AVAILABLE = False


class KnowledgeBase:
    """
    RAG Knowledge Base that parses, stores, and indexes the complete offline dataset
    of Life in Adventure (Events, Choices, Items, Monsters).
    """

    def __init__(self, db_path: str = "data/knowledge_base", source_dir: str = "data/apk/assets_dump"):
        self.db_dir = Path(db_path)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db_file = self.db_dir / "lia_kb.sqlite"
        self.source_dir = Path(source_dir)
        
        self.conn: Optional[sqlite3.Connection] = None
        self.version = "1.0.0-offline-dump"
        
        # In-memory indexes for fast hybrid search
        self.event_texts: List[str] = []
        self.event_ids: List[str] = []
        self.event_records: Dict[str, Dict[Any, Any]] = {}
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
        self.chroma_client = None
        self.chroma_collection = None
        self._embedder = None
        self._lang_cache: dict = {}  # suffix -> (filtered_texts, filtered_ids)
        
        # ── LlamaIndex fields (Phase 1 migration) ─────────────────────────
        self._llama_documents: list = []
        self._bm25_retriever = None
        self._vector_index = None
        self._vector_retriever = None
        
        self._init_sqlite()
        self.build_or_load()

    def get_version(self) -> str:
        """Return KB schema and dataset version."""
        return self.version

    def _init_sqlite(self) -> None:
        """Create SQLite schema if not exists."""
        self.conn = sqlite3.connect(str(self.db_file), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_key TEXT PRIMARY KEY,
                    id INTEGER,
                    source_file TEXT,
                    grade INTEGER,
                    normal_goal TEXT,
                    required TEXT,
                    raw_text TEXT,
                    clean_text TEXT
                );
                CREATE TABLE IF NOT EXISTS choices (
                    choice_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT,
                    choice_idx INTEGER,
                    required TEXT,
                    text TEXT,
                    results_json TEXT,
                    FOREIGN KEY(event_key) REFERENCES events(event_key)
                );
                CREATE TABLE IF NOT EXISTS items (
                    index_id INTEGER PRIMARY KEY,
                    name_en TEXT,
                    name_id TEXT,
                    name_ko TEXT,
                    image TEXT,
                    price INTEGER,
                    rarity INTEGER,
                    desc_en TEXT,
                    raw_json TEXT
                );
                CREATE TABLE IF NOT EXISTS monsters (
                    index_id INTEGER PRIMARY KEY,
                    name_en TEXT,
                    name_id TEXT,
                    name_ko TEXT,
                    hp INTEGER,
                    raw_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_clean_text ON events(clean_text);
                CREATE INDEX IF NOT EXISTS idx_items_name_en ON items(name_en);
                CREATE INDEX IF NOT EXISTS idx_monsters_name_en ON monsters(name_en);
            """)

    def _clean_text(self, text: str) -> str:
        """Strip Unity formatting codes, icons (`|...|`), and extra whitespace."""
        if not text:
            return ""
        # Remove Unity tags like |drawing_board| or <color=#ffffff>
        text = re.sub(r'\|[^|]+\|', ' ', text)
        text = re.sub(r'</?(?:color|size|i|b|u|sprite|material|align|voffset|c|sub|sup|mark)[^>]*>', ' ', text, flags=re.IGNORECASE)
        # Normalize line endings and multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def build_or_load(self, force_rebuild: bool = False) -> None:
        """Check if dataset is loaded; if empty or force_rebuild, ingest extracted JSON files."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        event_count = cursor.fetchone()[0]

        if event_count == 0 or force_rebuild:
            logger.info("Building Knowledge Base from extracted JSON dumps...")
            self._ingest_all_assets()
        else:
            logger.info(f"Loaded existing SQLite KB with {event_count} events.")

        self._build_in_memory_indexes()

    def _ingest_all_assets(self) -> None:
        """Parse all JSON files in source_dir and insert into SQLite."""
        if not self.source_dir.exists():
            logger.error(f"Source directory '{self.source_dir}' does not exist! Run extract_assets.py first.")
            return

        with self.conn:
            # Clear existing data on rebuild
            self.conn.executescript("DELETE FROM choices; DELETE FROM events; DELETE FROM items; DELETE FROM monsters;")

            # Ingest Items
            item_file = self.source_dir / "itemJson.json"
            if item_file.exists():
                try:
                    with open(item_file, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                        items_list = data.get("list", []) if isinstance(data, dict) else data
                        for it in items_list:
                            names = it.get("name", [])
                            descs = it.get("desc", [])
                            name_ko = names[0] if len(names) > 0 else ""
                            name_en = names[1] if len(names) > 1 else name_ko
                            name_id = names[8] if len(names) > 8 else name_en
                            desc_en = descs[1] if len(descs) > 1 else (descs[0] if len(descs) > 0 else "")
                            
                            self.conn.execute("""
                                INSERT OR REPLACE INTO items (index_id, name_en, name_id, name_ko, image, price, rarity, desc_en, raw_json)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                it.get("index", 0),
                                name_en, name_id, name_ko,
                                it.get("image", ""),
                                it.get("price", 0),
                                it.get("rarity", 0),
                                self._clean_text(desc_en),
                                json.dumps(it, ensure_ascii=False)
                            ))
                        logger.info(f"Ingested {len(items_list)} items.")
                except Exception as e:
                    logger.error(f"Failed ingesting items: {e}")

            # Ingest Monsters
            monster_file = self.source_dir / "monsterJson.json"
            if monster_file.exists():
                try:
                    with open(monster_file, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                        m_list = data.get("list", []) if isinstance(data, dict) else data
                        for m in m_list:
                            names = m.get("name", [])
                            name_ko = names[0] if len(names) > 0 else ""
                            name_en = names[1] if len(names) > 1 else name_ko
                            name_id = names[8] if len(names) > 8 else name_en
                            
                            self.conn.execute("""
                                INSERT OR REPLACE INTO monsters (index_id, name_en, name_id, name_ko, hp, raw_json)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (
                                m.get("index", 0),
                                name_en, name_id, name_ko,
                                m.get("hp", 0),
                                json.dumps(m, ensure_ascii=False)
                            ))
                        logger.info(f"Ingested {len(m_list)} monsters.")
                except Exception as e:
                    logger.error(f"Failed ingesting monsters: {e}")

            # Ingest Events (Main & Sub)
            total_events = 0
            for json_file in sorted(self.source_dir.glob("Event*.json")):
                try:
                    with open(json_file, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                        ev_list = data.get("list", []) if isinstance(data, dict) else data
                        for idx, ev in enumerate(ev_list):
                            ev_id = ev.get("id", idx)
                            ev_key = f"{json_file.stem}_{ev_id}_{idx}"
                            raw_text = ev.get("text", "")
                            clean_t = self._clean_text(raw_text)
                            
                            self.conn.execute("""
                                INSERT OR REPLACE INTO events (event_key, id, source_file, grade, normal_goal, required, raw_text, clean_text)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ev_key, ev_id, json_file.stem,
                                ev.get("grade", 1),
                                str(ev.get("normalGoal", "")),
                                str(ev.get("required", "")),
                                raw_text, clean_t
                            ))
                            
                            # Ingest choices
                            for c_idx, ch in enumerate(ev.get("choice", [])):
                                self.conn.execute("""
                                    INSERT INTO choices (event_key, choice_idx, required, text, results_json)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (
                                    ev_key, c_idx,
                                    str(ch.get("required", "")),
                                    self._clean_text(ch.get("text", "")),
                                    json.dumps(ch.get("result", []), ensure_ascii=False)
                                ))
                            total_events += 1
                except Exception as e:
                    logger.error(f"Failed parsing {json_file.name}: {e}")

            logger.info(f"Successfully ingested {total_events} events into SQLite database.")

    def _build_in_memory_indexes(self) -> None:
        """Load events into memory for RapidFuzz and build LlamaIndex + ChromaDB vector index."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT event_key, clean_text, source_file, grade, required FROM events WHERE clean_text != ''")
        rows = cursor.fetchall()
        
        self.event_texts = []
        self.event_ids = []
        self.event_records = {}
        
        for r in rows:
            ekey = r["event_key"]
            txt = r["clean_text"]
            self.event_ids.append(ekey)
            self.event_texts.append(txt)
            self.event_records[ekey] = {
                "event_key": ekey,
                "clean_text": txt,
                "source_file": r["source_file"],
                "grade": r["grade"],
                "required": r["required"],
            }
            
        logger.info(f"Loaded {len(self.event_texts)} non-empty event strings for fast search.")
        
        # Build TF-IDF matrix (kept as fast sklearn fallback)
        if _TFIDF_AVAILABLE and len(self.event_texts) > 0:
            logger.info("Building TF-IDF vectorizer over events...")
            self.tfidf_vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=50000)
            self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.event_texts)
            logger.info("TF-IDF matrix built successfully.")

        # ── LlamaIndex-based vector indexing ─────────────────────────────
        # Replaces manual SentenceTransformer loading + ChromaDB batch upsert.
        # Falls back gracefully to manual ChromaDB if LlamaIndex not available.
        if _LLAMAINDEX_AVAILABLE and _CHROMADB_AVAILABLE and len(self.event_texts) > 0:
            try:
                self._build_llama_index()
            except Exception as e:
                logger.warning(f"LlamaIndex build failed, falling back to manual ChromaDB: {e}")
                self._build_legacy_chroma()
        elif _CHROMADB_AVAILABLE and len(self.event_texts) > 0:
            self._build_legacy_chroma()

    def _build_llama_index(self) -> None:
        """
        Build ChromaDB vector store via LlamaIndex HuggingFaceEmbedding + ChromaVectorStore.
        Creates a VectorStoreIndex for semantic retrieval with metadata filtering.
        """
        t0 = time.time()
        
        # 1. Load embedder via LlamaIndex (handles caching, offline-first, warmup)
        try:
            embed_model = HuggingFaceEmbedding(
                model_name="all-MiniLM-L6-v2",
                trust_remote_code=False,
            )
            # Warmup
            _ = embed_model.get_text_embedding("warmup")
            elapsed = time.time() - t0
            logger.info(f"LlamaIndex HuggingFaceEmbedding ready ({elapsed:.1f}s).")
        except Exception as e:
            # Fallback: try SentenceTransformer directly as embed_model is not required
            # for LlamaIndex to function — it can use local_files_only
            logger.info(f"HuggingFaceEmbedding warmup issue: {e}. Trying local-only...")
            embed_model = HuggingFaceEmbedding(
                model_name="all-MiniLM-L6-v2",
                trust_remote_code=False,
            )
        
        self._embedder = embed_model
        
        # 2. Build LlamaIndex Documents from event records
        self._llama_documents = []
        for eid in self.event_ids:
            rec = self.event_records[eid]
            doc = Document(
                text=rec["clean_text"],
                doc_id=eid,
                metadata={
                    "event_key": rec["event_key"],
                    "source_file": rec["source_file"],
                    "grade": rec["grade"],
                    "required": rec["required"],
                    "lang_suffix": self._get_suffix(rec["source_file"]),
                },
            )
            self._llama_documents.append(doc)
        
        # 3. Create ChromaDB collection (reuse existing if populated)
        chroma_path = str(self.db_dir / "chroma")
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.chroma_collection = self.chroma_client.get_or_create_collection(name="lia_events")
        
        vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # 4. Build or load vector index
        if self.chroma_collection.count() == 0:
            logger.info("Building LlamaIndex VectorStoreIndex into ChromaDB (first run, ~10-15 min)...")
            self._vector_index = VectorStoreIndex.from_documents(
                self._llama_documents,
                storage_context=storage_context,
                embed_model=embed_model,
                show_progress=True,
            )
            logger.info(f"LlamaIndex vector index built ({self.chroma_collection.count()} vectors).")
        else:
            logger.info(f"Loading existing ChromaDB collection ({self.chroma_collection.count()} vectors)...")
            self._vector_index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=embed_model,
            )
        
        # 5. Create LlamaIndex retrievers
        self._vector_retriever = self._vector_index.as_retriever(
            similarity_top_k=20,  # fetch more than needed; cascade will filter
        )
        
        elapsed_total = time.time() - t0
        logger.info(f"LlamaIndex pipeline ready ({elapsed_total:.1f}s total).")

    def _build_legacy_chroma(self) -> None:
        """
        Fallback: manual ChromaDB indexing (pre-LlamaIndex, kept for environments
        where llama-index-core cannot be installed).
        """
        # Eager-load SentenceTransformer embedder (offline-first)
        if self._embedder is None:
            try:
                t0 = time.time()
                try:
                    logger.info("Loading SentenceTransformer from local cache...")
                    self._embedder = SentenceTransformer(
                        "all-MiniLM-L6-v2",
                        local_files_only=True,
                    )
                    source = "local cache"
                except Exception:
                    logger.info("Model not cached locally. Downloading from HuggingFace (one-time, ~90MB)...")
                    self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                    source = "download"
                self._embedder.encode(["warmup"], show_progress_bar=False)
                elapsed = time.time() - t0
                logger.info(f"SentenceTransformer ready ({source}, {elapsed:.1f}s).")
            except Exception as e:
                logger.warning(f"Failed to load SentenceTransformer: {e}. ChromaDB search will be skipped.")
                return

        try:
            chroma_path = str(self.db_dir / "chroma")
            self.chroma_client = chromadb.PersistentClient(path=chroma_path)
            self.chroma_collection = self.chroma_client.get_or_create_collection(name="lia_events")

            if self.chroma_collection.count() == 0:
                logger.info("Indexing events into ChromaDB vector store (legacy)...")
                batch_size = 500
                for i in range(0, len(self.event_texts), batch_size):
                    batch_txt = self.event_texts[i:i+batch_size]
                    batch_ids = self.event_ids[i:i+batch_size]
                    batch_embs = self._embedder.encode(batch_txt, show_progress_bar=False, normalize_embeddings=True).tolist()
                    batch_meta = [
                        {
                            "source": self.event_records[eid]["source_file"],
                            "lang_suffix": self._get_suffix(self.event_records[eid]["source_file"]),
                        }
                        for eid in batch_ids
                    ]
                    self.chroma_collection.upsert(
                        ids=batch_ids,
                        embeddings=batch_embs,
                        documents=batch_txt,
                        metadatas=batch_meta
                    )
                logger.info("ChromaDB vector store indexed successfully.")
            else:
                logger.info(f"ChromaDB collection ready ({self.chroma_collection.count()} vectors).")
        except Exception as e:
            logger.warning(f"ChromaDB initialization failed, falling back to TF-IDF + RapidFuzz: {e}")
            self.chroma_collection = None

    def get_event_with_choices(self, event_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve full event metadata, choices, and chance results by event_key."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM events WHERE event_key = ?", (event_key,))
        ev_row = cursor.fetchone()
        if not ev_row:
            return None
            
        ev_data = dict(ev_row)
        cursor.execute("SELECT * FROM choices WHERE event_key = ? ORDER BY choice_idx ASC", (event_key,))
        choices_rows = cursor.fetchall()
        
        choices_list = []
        for ch in choices_rows:
            ch_dict = dict(ch)
            ch_dict["results"] = json.loads(ch["results_json"]) if ch["results_json"] else []
            choices_list.append(ch_dict)
            
        ev_data["choices"] = choices_list
        return ev_data

    def get_event_by_key(self, event_key: str) -> Optional[Dict[str, Any]]:
        """Alias for get_event_with_choices."""
        return self.get_event_with_choices(event_key)


    def _get_suffix(self, source_file: str) -> str:
        """
        Extract the language digit suffix from a source file name.

        Examples:
            "EventBattle0"  → "0"  (Korean)
            "EventMain1"    → "1"  (English)
            "EventSub2"     → "2"  (Spanish)
            "EventMain_0"   → "0"  (underscore format)

        Uses regex to find trailing digits after stripping alphabetic prefix.
        """
        import re
        # Strip alphabetic prefix, extract trailing digits
        m = re.search(r'(\d+)$', source_file)
        return m.group(1) if m else ""

    def _lang_to_suffix(self, language: Optional[str]) -> Optional[str]:
        """Map language string/code to event file suffix digit (0-8)."""
        if not language:
            return None
        lang_clean = str(language).lower().strip()
        if lang_clean in ("english", "en", "1"):
            return "1"
        elif lang_clean in ("indonesian", "id", "indonesia", "8"):
            return "8"
        elif lang_clean in ("korean", "ko", "korea", "0"):
            return "0"
        elif lang_clean in ("spanish", "es", "2"):
            return "2"
        elif lang_clean in ("italian", "it", "3"):
            return "3"
        elif lang_clean in ("portuguese", "pt", "4"):
            return "4"
        elif lang_clean in ("chinese_simplified", "zh_cn", "zh-cn", "5"):
            return "5"
        elif lang_clean in ("chinese_traditional", "zh_tw", "zh-tw", "6"):
            return "6"
        elif lang_clean in ("japanese", "ja", "jp", "7"):
            return "7"
        return None

    def _get_lang_filtered(self, suffix: Optional[str]) -> Tuple[List[str], List[str]]:
        """
        Return (texts, ids) filtered by language suffix.
        Results are cached in self._lang_cache so the filtering is done once per suffix.
        """
        if suffix is None:
            return self.event_texts, self.event_ids
        if suffix in self._lang_cache:
            return self._lang_cache[suffix]
        texts, ids = [], []
        for idx, ekey in enumerate(self.event_ids):
            if str(self.event_records[ekey].get("source_file", "")).endswith(suffix):
                texts.append(self.event_texts[idx])
                ids.append(ekey)
        self._lang_cache[suffix] = (texts, ids)
        logger.debug(f"Built lang filter cache for suffix='{suffix}': {len(texts)} events")
        return texts, ids

    def _is_correct_lang(self, ekey: str, suffix: str) -> bool:
        """Return True if event key belongs to the given language suffix."""
        rec = self.event_records.get(ekey)
        if not rec:
            return False
        return str(rec.get("source_file", "")).endswith(suffix)

    def search_events(
        self,
        query: str,
        top_k: int = 5,
        use_vector: bool = True,
        language: Optional[str] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Cascade hybrid search: RapidFuzz → TF-IDF → Chroma (early termination).

        Returns list of (event_record_with_choices, confidence_score).
        """
        query_clean = self._clean_text(query)
        if not query_clean or len(self.event_texts) == 0:
            return []

        suffix = self._lang_to_suffix(language)
        results: dict[str, float] = {}  # event_key -> best combined score

        # Stage 1: RapidFuzz (fastest, lang-filtered, cached).
        filtered_texts, filtered_ids = self._get_lang_filtered(suffix)
        if filtered_texts and _RAPIDFUZZ_AVAILABLE:
            try:
                fuzz_matches = process.extract(
                    query_clean,
                    filtered_texts,
                    scorer=fuzz.token_sort_ratio,
                    limit=top_k * 3,
                )
                for txt_match, score_int, idx in fuzz_matches:
                    score = score_int / 100.0
                    if score > 0.65:
                        results[filtered_ids[idx]] = max(results.get(filtered_ids[idx], 0.0), score)
                # token_set_ratio bonus
                fuzz_set = process.extract(
                    query_clean,
                    filtered_texts,
                    scorer=fuzz.token_set_ratio,
                    limit=top_k * 3,
                )
                for txt_match, score_int, idx in fuzz_set:
                    score = (score_int / 100.0) * 0.85
                    if score > 0.72:
                        results[filtered_ids[idx]] = max(results.get(filtered_ids[idx], 0.0), score)
            except Exception as e:
                logger.debug(f"RapidFuzz search skipped: {e}")

        # Early termination: strong RapidFuzz match → skip expensive engines.
        if results and max(results.values()) >= 0.88:
            logger.debug(f"RapidFuzz early termination at score {max(results.values()):.2f}")
            return self._finalize_results(results, top_k)

        # Stage 2: TF-IDF cosine similarity (if RapidFuzz wasn't decisive).
        if _TFIDF_AVAILABLE and self.tfidf_matrix is not None and self.tfidf_vectorizer is not None:
            try:
                q_vec = self.tfidf_vectorizer.transform([query_clean])
                sims = cosine_similarity(q_vec, self.tfidf_matrix).flatten()
                fetch_k = top_k * 5 if suffix else top_k * 3
                top_indices = np.argsort(sims)[::-1][:fetch_k]
                for idx in top_indices:
                    score = float(sims[idx])
                    if score > 0.1:
                        ekey = self.event_ids[idx]
                        if not suffix or self._is_correct_lang(ekey, suffix):
                            results[ekey] = max(results.get(ekey, 0.0), score)
            except Exception as e:
                logger.debug(f"TF-IDF search skipped: {e}")

        best_so_far = max(results.values()) if results else 0.0

        # Stage 3: Vector search (cold path, only if TF-IDF was weak).
        # LlamaIndex handles embedding/indexing; retrieval uses ChromaDB directly.
        # Note: older Chroma indices may only have metadata "source" (no lang_suffix).
        # Prefer where=lang_suffix when present; always post-filter by language.
        if best_so_far < 0.6 and use_vector and self.chroma_collection is not None and self._embedder is not None:
            try:
                if hasattr(self._embedder, "encode"):
                    q_emb = self._embedder.encode(
                        [query_clean], normalize_embeddings=True
                    ).tolist()
                else:
                    q_emb = [self._embedder.get_text_embedding(query_clean)]
                # Over-fetch when language filter applied (post-filter may drop hits)
                n_results = top_k * 8 if suffix else top_k * 2
                query_filter = {"lang_suffix": suffix} if suffix else None
                try:
                    c_res = self.chroma_collection.query(
                        query_embeddings=q_emb,
                        n_results=n_results,
                        where=query_filter,
                    )
                except Exception:
                    # Metadata may lack lang_suffix (legacy index) — query unfiltered
                    c_res = self.chroma_collection.query(
                        query_embeddings=q_emb,
                        n_results=n_results,
                    )
                if c_res["ids"] and len(c_res["ids"][0]) > 0:
                    for idx, ekey in enumerate(c_res["ids"][0]):
                        if suffix and not self._is_correct_lang(ekey, suffix):
                            continue
                        dist = c_res["distances"][0][idx] if c_res.get("distances") else 0.0
                        # L2 on unit vectors ≈ [0, 2]; map to [0, 1]
                        score = max(0.0, min(1.0, 1.0 - (float(dist) / 2.0)))
                        results[ekey] = max(results.get(ekey, 0.0), score)
            except Exception as e:
                logger.warning(f"Vector search failed: {e}. Using RapidFuzz + TF-IDF only.")

        return self._finalize_results(results, top_k)

    def _finalize_results(
        self, results: dict[str, float], top_k: int
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Sort results by score and fetch full event data."""
        sorted_keys = sorted(results.items(), key=lambda x: x[1], reverse=True)[:top_k]
        output = []
        for ekey, score in sorted_keys:
            full_ev = self.get_event_with_choices(ekey)
            if full_ev:
                output.append((full_ev, round(score, 4)))
        return output

    def get_item_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Find item by ID."""
        if not self.conn:
            return None
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM items WHERE index_id = ?", (item_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_item_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find item by English, Indonesian, or Korean name."""
        if not self.conn:
            return None
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM items 
            WHERE name_en LIKE ? OR name_id LIKE ? OR name_ko LIKE ?
            LIMIT 1
        """, (f"%{name}%", f"%{name}%", f"%{name}%"))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_monster_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find monster by name."""
        if not self.conn:
            return None
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM monsters 
            WHERE name_en LIKE ? OR name_id LIKE ? OR name_ko LIKE ?
            LIMIT 1
        """, (f"%{name}%", f"%{name}%", f"%{name}%"))
        row = cursor.fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
