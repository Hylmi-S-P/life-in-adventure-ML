"""
retriever.py - RAG Retriever for Life in Adventure.
Retrieves and structures event dialogs, choices, stat requirements, items, and monsters
from KnowledgeBase based on OCR screen text or user queries.

Vector search backend: LlamaIndex VectorStoreIndex (when available) or legacy ChromaDB.
Choice re-ranking: LlamaIndex NodePostprocessor (when available) or inline lexical boost.
"""

import json
from typing import Dict, List, Any, Optional
import loguru

from src.rag.knowledge_base import KnowledgeBase
from src.core.response_cache import ResponseCache

logger = loguru.logger

# Optional: LlamaIndex NodePostprocessor for choice-aware re-ranking
try:
    from llama_index.core.postprocessor import SimilarityPostprocessor
    _LLAMA_PP_AVAILABLE = True
except ImportError:
    _LLAMA_PP_AVAILABLE = False


class ChoiceAwarePostprocessor:
    """
    LlamaIndex-compatible NodePostprocessor that boosts event scores based on
    choice text appearing literally in the OCR query. Equivalent to the inline
    re-ranking logic in retrieve_for_ocr() — packaged as a standalone processor
    for cleaner separation and potential LlamaIndex pipeline integration.
    """
    def __init__(self, kb: KnowledgeBase, ocr_text: str):
        self.kb = kb
        self.ocr_lower = ocr_text.lower()

    def postprocess_nodes(self, nodes, query_bundle=None):
        """Boost nodes whose choice text appears in the OCR query."""
        for node in nodes:
            ekey = node.node_id
            full_ev = self.kb.get_event_with_choices(ekey)
            if not full_ev:
                continue
            choice_hits = 0
            for ch in full_ev.get("choices", []):
                ch_txt = ch.get("text", "").strip().lower()
                if ch_txt and len(ch_txt) >= 3:
                    if ch_txt in self.ocr_lower or self.ocr_lower.find(ch_txt[:15]) != -1:
                        choice_hits += 1
            if choice_hits > 0:
                boost = 0.18 + (choice_hits * 0.05)
                node.score = min(1.0, (node.score or 0.0) + boost)
        return sorted(nodes, key=lambda n: n.score or 0.0, reverse=True)


class RAGRetriever:
    """
    High-level retrieval engine that interfaces between raw OCR screen captures / user queries
    and the underlying offline KnowledgeBase (SQLite + ChromaDB + TF-IDF).
    """

    def __init__(
        self,
        knowledge_base: Optional[KnowledgeBase] = None,
        top_k_events: int = 3,
        top_k_choices: int = 5,
        similarity_threshold: float = 0.48,
    ):
        self.kb = knowledge_base
        self.top_k_events = top_k_events
        self.top_k_choices = top_k_choices
        self.similarity_threshold = similarity_threshold
        # Persistent TTL cache for RAG results — identical OCR text + language hits cache.
        self._cache = ResponseCache(
            maxsize=500,
            ttl=3600.0,
            persist_path="data/rag_cache.json",
        )

    def _is_requirement_met(self, req: str, player_stats: Dict[str, int], player_inventory: List[str]) -> bool:
        """Check if player meets choice requirement criteria (stats/items/spells)."""
        if not req or req == "0" or req == "-1":
            return True

        for option in req.split('|'):
            option = option.strip()
            if not option:
                continue

            tokens = option.split('_')
            if not tokens:
                continue

            prefix = tokens[0]

            # 8: Item requirement
            if prefix == "8" and len(tokens) >= 3:
                try:
                    item_id = int(tokens[1])
                    item_data = self.kb.get_item_by_id(item_id) if (self.kb and hasattr(self.kb, "get_item_by_id")) else None
                    if item_data:
                        names = [
                            str(item_data.get("name_en", "")).lower(),
                            str(item_data.get("name_id", "")).lower(),
                            str(item_data.get("name_ko", "")).lower()
                        ]
                        matched = False
                        for p_item in player_inventory:
                            p_item_clean = str(p_item).lower().strip()
                            if any(p_item_clean == name or p_item_clean in name or name in p_item_clean for name in names if name):
                                matched = True
                                break
                        if matched:
                            return True
                    else:
                        common_items = {
                            38: ["shovel", "sekop"],
                            39: ["rope", "tali"],
                            42: ["lantern", "lentera"],
                        }
                        if item_id in common_items:
                            names = common_items[item_id]
                            matched = False
                            for p_item in player_inventory:
                                p_item_clean = str(p_item).lower().strip()
                                if any(p_item_clean == name or p_item_clean in name for name in names):
                                    matched = True
                                    break
                            if matched:
                                return True
                except ValueError:
                    pass
                continue

            # 20: Spell requirement
            elif prefix == "20" and len(tokens) >= 3:
                spell_keywords = ["magic", "spell", "light", "barrier", "gravity", "growth", "wind", "fire", "undead", "mana"]
                matched = False
                for p_item in player_inventory:
                    p_item_clean = str(p_item).lower().strip()
                    if any(kw in p_item_clean for kw in spell_keywords):
                        matched = True
                        break
                if matched:
                    return True
                continue

            # 17: Gem requirement
            elif prefix == "17" and len(tokens) >= 3:
                return True

            # Other flags / stat requirements (prefixes 0-5: STR through WIS)
            # These are always "met" in the filtering sense — we don't hide choices
            # based on stat values because the player might pass a low-DC check
            # with a bad stat. The AI decision engine handles stat evaluation via
            # HeuristicPolicy.evaluate_choice which computes actual pass probability.
            else:
                return True

        return False

    def retrieve_for_ocr(
        self,
        ocr_text: str,
        use_vector: bool = True,
        language: Optional[str] = None,
        player_stats: Optional[Dict[str, int]] = None,
        player_inventory: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Query KB for events matching the OCR screen text.
        Returns a structured dictionary with best match, confidence, choices, and stat thresholds.
        Cache key: hash(ocr_text, language) — player-specific state not cached.
        """
        if not self.kb or not ocr_text or not ocr_text.strip():
            return {
                "matched": False,
                "confidence": 0.0,
                "event": None,
                "event_full": None,  # full event with choices — no double-fetch needed
                "choices": [],
                "candidates": []
            }

        # Check persistent cache (key = OCR text + language + use_vector flag).
        # NOTE: use_vector must be in the key because it changes the search strategy
        # (Chroma vs TF-IDF-only) and therefore the confidence scores.
        cache_key = ResponseCache.make_key(
            ocr_text, language, use_vector,
            ",".join(sorted(str(i).lower() for i in (player_inventory or [])))
        )
        if (cached := self._cache.get(cache_key)) is not None:
            logger.debug(f"RAG cache hit for: {ocr_text[:40]}...")
            return cached

        logger.debug(f"Querying RAG KB with OCR text ({len(ocr_text)} chars): {ocr_text[:60]}...")
        raw_matches = self.kb.search_events(ocr_text, top_k=self.top_k_events, use_vector=use_vector, language=language)

        if not raw_matches:
            return {
                "matched": False,
                "confidence": 0.0,
                "event": None,
                "event_full": None,
                "choices": [],
                "candidates": []
            }

        # Choice-Aware Lexical Re-Ranker: Boost score if candidate's choice options literally appear inside OCR text
        reranked_matches = []
        clean_ocr_lower = ocr_text.lower()
        for ev, score in raw_matches:
            boosted_score = score
            choice_hits = 0
            for ch in ev.get("choices", []):
                ch_txt = ch.get("text", "").strip().lower()
                if ch_txt and len(ch_txt) >= 3 and (ch_txt in clean_ocr_lower or clean_ocr_lower.find(ch_txt[:15]) != -1):
                    choice_hits += 1
            if choice_hits > 0:
                boosted_score = min(1.0, score + 0.18 + (choice_hits * 0.05))
            reranked_matches.append((ev, boosted_score))

        reranked_matches.sort(key=lambda x: x[1], reverse=True)

        # Format candidates
        candidates = []
        best_event, best_score = reranked_matches[0]
        
        for ev, score in reranked_matches:
            candidates.append({
                "event_key": ev.get("event_key"),
                "id": ev.get("id"),
                "grade": ev.get("grade"),
                "required": ev.get("required"),
                "clean_text": ev.get("clean_text", "")[:150],
                "confidence": round(score, 3),
                "choices_count": len(ev.get("choices", []))
            })

        # Require stronger match for short OCR (noise / partial dialogue).
        # Weak scores (<0.55) often pick wrong quests with similar vocabulary.
        match_threshold = self.similarity_threshold
        if len(ocr_text.strip()) < 40:
            match_threshold = max(match_threshold, 0.62)
        is_matched = best_score >= match_threshold

        # Parse choices and result branches for top match, applying active player inventory/stats requirements filter
        formatted_choices = []
        if is_matched and "choices" in best_event:
            stats = player_stats or {}
            inv = player_inventory or []
            stats_lower = {k.lower(): v for k, v in stats.items()}

            visible_idx = 0
            for ch in best_event["choices"][:self.top_k_choices]:
                req = ch.get("required", "")
                if not self._is_requirement_met(req, stats_lower, inv):
                    logger.info(f"🚫 Filtering out choice index {ch.get('choice_idx')} ('{ch.get('text', '')}') because requirements ('{req}') are not met.")
                    continue

                formatted_choices.append({
                    "choice_idx": visible_idx,
                    "original_idx": ch.get("choice_idx"),
                    "text": ch.get("text", ""),
                    "required": req,
                    "results": ch.get("results", [])
                })
                visible_idx += 1

        result = {
            "matched": is_matched,
            "confidence": round(best_score, 3),
            "event": {
                "event_key": best_event.get("event_key"),
                "id": best_event.get("id"),
                "grade": best_event.get("grade"),
                "normal_goal": best_event.get("normal_goal"),
                "required": best_event.get("required"),
                "raw_text": best_event.get("raw_text"),
                "clean_text": best_event.get("clean_text"),
                "source_file": best_event.get("source_file"),
            } if is_matched else None,
            "event_full": best_event if is_matched else None,
            "choices": formatted_choices if is_matched else [],
            "candidates": candidates
        }
        # Cache the result (keyed by OCR text + language + use_vector).
        self._cache.set(cache_key, result)
        return result

    def get_item_info(self, item_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve detailed item stats and descriptions by exact or partial name."""
        if not self.kb or not item_name:
            return None
        return self.kb.get_item_by_name(item_name)

    def get_monster_info(self, monster_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve detailed monster combat stats by name."""
        if not self.kb or not monster_name:
            return None
        return self.kb.get_monster_by_name(monster_name)

    def explain_stat_requirement(self, req_code: str) -> List[str]:
        """
        Parse D20 stat threshold string (e.g. '1_2_10|13_0_0') into readable text.
        In LiA: Stat codes generally map to: 0: STR, 1: DEX, 2: INT, 3: CHA, 4: CON, 5: WIS, etc.
        """
        if not req_code or req_code == "0" or req_code == "":
            return ["No stat requirement (Free choice)"]
            
        explanations = []
        # Rules split by '|' or '&'
        parts = req_code.split("|")
        stat_names = {0: "STR", 1: "DEX", 2: "INT", 3: "CHA", 4: "CON", 5: "WIS", 13: "Item/Gold Check"}
        
        for p in parts:
            tokens = p.split("_")
            if len(tokens) >= 3:
                try:
                    stat_id = int(tokens[0])
                    chk_type = int(tokens[1])
                    threshold = int(tokens[2])
                    s_name = stat_names.get(stat_id, f"Stat#{stat_id}")
                    explanations.append(f"Requires {s_name} DC {threshold}")
                except ValueError:
                    explanations.append(f"Raw check: {p}")
            else:
                explanations.append(f"Raw check: {p}")
                
        return explanations
