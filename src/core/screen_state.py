"""
screen_state.py - Screen state classifier for the auto-play loop.

Classifies the current emulator screen into one of:
  DIALOGUE — text scrolling, tap to advance
  CHOICE   — choices visible → RAG + decide + click
  COMBAT   — combat UI → combat stat calculator / advance battle
  AD       — video ad → pause
  STATS    — stats panel → auto-parse + update player_stats
  UNKNOWN  — could not determine
"""

from enum import Enum
from typing import List, Dict, Any, Tuple

# Language-specific advance/confirm keywords detected by OCR in choice buttons.
_ADVANCE_KEYWORDS = [
    # English
    "continue", "confirm", "ok", "start", "next", "leave", "confirmar",
    # Indonesian
    "kembali", "mulai", "coba lagi",
    # Korean
    "다음", "확인", "계속",
    # Japanese
    "承諾", "accept",
]
_ADVANCE_SET = frozenset(k.lower() for k in _ADVANCE_KEYWORDS)

# Combat keywords (multiple languages).
_COMBAT_KEYWORDS = [
    "battle", "combat", "attack", "fight", "전투", "pertempuran",
    "atk", "hp", "defense", "damaged", "damage", "dodge", "block", "roll",
    "begin battle", "abandon battle", "victory", "defeat",
    "power points", "simulate",
]
_COMBAT_SET = frozenset(k.lower() for k in _COMBAT_KEYWORDS)

# Stats panel keywords (for auto-parsing player stats).
_STATS_KEYWORDS = [
    "str", "dex", "con", "int", "wis", "cha",
    "strength", "dexterity", "constitution", "wisdom", "charisma",
    "level", "exp", "hp", "sanity", "gold",
]


class ScreenState(Enum):
    DIALOGUE = "dialogue"
    CHOICE = "choice"
    COMBAT = "combat"
    AD = "ad"
    STATS = "stats"
    UNKNOWN = "unknown"


class ScreenStateMachine:
    """
    Classify the current screen state from OCR output.

    Usage in the auto-play loop::

        state, confidence = classifier.classify(ocr_text, ocr_boxes, ad_playing)
        if state == ScreenState.AD:
            time.sleep(4); continue
        if state == ScreenState.DIALOGUE:
            clicker.click_advance_dialog(...); continue
        if state == ScreenState.CHOICE:
            rag_and_decide()   # only expensive step for choice screens
        ...
    """

    def classify(
        self,
        ocr_text: str,
        ocr_boxes: List[Dict[str, Any]],
        ad_playing: bool,
    ) -> Tuple[ScreenState, float]:
        """
        Returns (state, confidence) where confidence is 0.0–1.0.
        """
        if ad_playing:
            return ScreenState.AD, 1.0

        text_lower = ocr_text.lower()

        # Combat detection — phrase first, then multi-keyword.
        if "begin battle" in text_lower or "abandon battle" in text_lower:
            return ScreenState.COMBAT, 0.95
        combat_hits = sum(1 for kw in _COMBAT_SET if kw in text_lower)
        if combat_hits >= 2:
            return ScreenState.COMBAT, min(1.0, 0.5 + combat_hits * 0.15)

        # Stats panel detection.
        stats_hits = sum(1 for kw in _STATS_KEYWORDS if kw in text_lower)
        if stats_hits >= 3:
            return ScreenState.STATS, min(1.0, 0.5 + stats_hits * 0.1)

        # Advance-button detection — presence of "Continue" / "Kembali" etc.
        advance_found = False
        for box in ocr_boxes:
            box_text = box.get("text", "").lower().strip()
            if not box_text or len(box_text) > 30:
                continue
            words = frozenset(box_text.split())
            if words & _ADVANCE_SET:
                advance_found = True
                break

        if advance_found:
            return ScreenState.DIALOGUE, 0.85

        # Default: choices likely visible.
        return ScreenState.CHOICE, 0.7

    def should_run_rag(self, state: ScreenState) -> bool:
        """Return True if RAG + AI pipeline should run for this state."""
        return state == ScreenState.CHOICE

    def should_click_advance(self, state: ScreenState) -> bool:
        """Return True if we should tap the advance button for this state."""
        return state in (ScreenState.DIALOGUE, ScreenState.UNKNOWN)
