"""
safety.py - Dead loop detector, loading screen handler, multi-step plan, DLC detector.
"""

from __future__ import annotations

import time
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─── #5: Loading Screen Detector ──────────────────────────────────────

_LOADING_INDICATORS = frozenset({
    "loading", "load", "please wait", "now loading", "connecting",
    "saving", "save", "syncing", "fetching",
    # symbol patterns that appear during transitions
    "...", "····", "···",
})

_SPINNER_RE = re.compile(r"[|/\\\-]")  # ASCII spinner chars

@dataclass
class LoadingState:
    consecutive_no_text: int = 0
    consecutive_same_short: int = 0
    last_short_text: str = ""
    detected: bool = False

    def check(self, ocr_text: str) -> bool:
        """Return True if loading screen detected."""
        t = (ocr_text or "").strip()
        if not t:
            self.consecutive_no_text += 1
            self.consecutive_same_short = 0
            self.detected = self.consecutive_no_text >= 2
            return self.detected

        text_l = t.lower()

        # Loading keywords
        for kw in _LOADING_INDICATORS:
            if kw in text_l:
                self.detected = True
                return True

        # Spinner char only (|/-\ spinning)
        if len(t) <= 2 and _SPINNER_RE.match(t):
            self.detected = True
            return True

        # Very short repeated text (e.g. "..." "1%" "10%")
        if len(t) <= 5:
            if t == self.last_short_text:
                self.consecutive_same_short += 1
            else:
                self.consecutive_same_short = 0
            self.last_short_text = t
            if self.consecutive_same_short >= 2:
                self.detected = True
                self.consecutive_same_short -= 1
                return True
            # Not yet repeated, but don't reset counters yet
            return False

        # Normal text → definitely not loading
        if len(t) > 5:
            self.reset()
            self.detected = False
            return False

        # Short non-repeated text fallthrough
        self.reset()
        self.detected = False
        return False

    def reset(self) -> None:
        """Reset all counters."""
        self.consecutive_no_text = 0
        self.consecutive_same_short = 0
        self.last_short_text = ""
        self.detected = False


# ─── #4: Dead Loop Detector ──────────────────────────────────────────

@dataclass
class DeadLoopState:
    """Track if bot is repeating same action on same screen without progress."""

    max_repeat: int = 10  # max identical action:event before declaring dead loop
    action_history: deque = field(default_factory=lambda: deque(maxlen=20))
    dead_loop_triggered: bool = False
    break_count: int = 0

    def record_and_check(
        self,
        action_type: str,
        event_key: Optional[str] = None,
        screen_text_snapshot: str = "",
    ) -> bool:
        """Record action; return True if dead loop detected."""
        self.action_history.append({
            "action": action_type,
            "event_key": event_key,
            "text": screen_text_snapshot[:50],
        })

        if len(self.action_history) < self.max_repeat:
            self.dead_loop_triggered = False
            return False

        # Check: last N all same action on same event
        recent = list(self.action_history)[-self.max_repeat:]
        if not recent:
            return False

        first_action = recent[0].get("action", "")
        first_event = recent[0].get("event_key", "")
        if all(
            r.get("action") == first_action
            and r.get("event_key") == first_event
            for r in recent[-self.max_repeat:]
        ):
            if self.dead_loop_triggered:
                self.break_count += 1
                return self.break_count >= 3  # 3rd break = force kill
            self.dead_loop_triggered = True
            self.break_count += 1
            return True

        self.dead_loop_triggered = False
        self.break_count = 0
        return False


# ─── #3: Multi-Step Action Plan ──────────────────────────────────────

@dataclass
class MultiStepPlan:
    """
    For flows like: Buy → Confirm → Pay.
    The bot detects a merchant screen, clicks "Buy", then anticipates
    the next screen is a confirm dialog and clicks the confirmed action.

    plan = ["Buy", "Yes"] or ["Buy", "Confirm", "Pay"]
    """

    active: bool = False
    steps: List[str] = field(default_factory=list)
    current_step: int = 0
    event_key: str = ""
    screen_suffix: str = ""

    _PLANS: Dict[str, List[str]] = field(default_factory=lambda: {
        "merchant_buy": ["buy", "confirm", "pay"],
        "quest_accept": ["accept", "confirm"],
        "quest_decline": ["decline", "confirm"],
        "shop_buy": ["buy", "confirm", "pay", "done"],
        "craft": ["craft", "select", "confirm"],
        "travel": ["travel to", "confirm", "pay"],
    })

    @staticmethod
    def detect_plan_fingerprint(
        text: str, buttons: List[Any]
    ) -> Optional[str]:
        pass

    @classmethod
    def match_plan(cls, action_text: str) -> Optional[str]:
        """Return plan name if action_text matches the first step of a known plan."""
        a = action_text.lower().strip()
        # Use a local ref so we don't hit dataclass field issues
        plans = {
            "merchant_buy": ["buy", "confirm", "pay"],
            "quest_accept": ["accept", "confirm"],
            "quest_decline": ["decline", "confirm"],
            "shop_buy": ["buy", "confirm", "pay", "done"],
            "craft": ["craft", "select", "confirm"],
            "travel": ["travel to", "confirm", "pay"],
        }
        for plan_name, steps in plans.items():
            if steps and a == steps[0].lower():
                return plan_name
        return None

    def start_plan(
        self, plan_name: str, event_key: str, screen_suffix: str = ""
    ) -> bool:
        steps = self._PLANS.get(plan_name)
        if not steps:
            return False
        self.active = True
        self.steps = list(steps)
        self.current_step = 1
        self.event_key = event_key
        self.screen_suffix = screen_suffix
        return True

    def get_next_action(self) -> Optional[str]:
        if not self.active or self.current_step >= len(self.steps):
            self.active = False
            return None
        return self.steps[self.current_step]

    def advance_step(self) -> None:
        self.current_step += 1
        if self.current_step >= len(self.steps):
            self.active = False

    def cancel(self) -> None:
        self.active = False
        self.current_step = 0

    @classmethod
    def plan_action_types(cls) -> List[str]:
        ret: List[str] = []
        plans = cls._PLANS if hasattr(cls, '_PLANS') and isinstance(cls._PLANS, dict) else {}
        for steps in plans.values():
            ret.extend(steps)
        return list(set(ret))


# ─── #2: DLC / Tales detector ────────────────────────────────────────

_DLC_KEYWORDS = frozenset({
    "tales", "tale", "dlc", "forest invitation", "demon of the mine",
    "dance with the demon", "echoes", "forgotten", "special",
    "background", "premium", "exclusive",
})

def detect_dlc(text: str, event_key: str = "") -> Tuple[bool, str]:
    """
    Check if current text/event matches DLC/Tales content.
    Returns (is_dlc, collection_name).
    """
    t = (text or "").lower()
    for kw in _DLC_KEYWORDS:
        if kw in t:
            return True, kw.title()
    # Event key patterns: Tales often have different prefixes
    if event_key.startswith("Tales") or "Tale" in event_key:
        return True, "Tales"
    return False, ""


# ─── #2b: KB tag existing events as DLC ──────────────────────────────

def tag_dlc_events(kb) -> int:
    """
    Tag all existing KB events that contain DLC/Tales keywords.
    Sets event metadata 'collection' = 'tales' | 'main' | 'side' | 'battle'.
    Returns count of tagged DLC events.
    """
    if not kb or not hasattr(kb, "event_records"):
        return 0
    count = 0
    for ekey, rec in kb.event_records.items():
        text = rec.get("clean_text", "") or ""
        # Check by keywords or source file naming
        is_dlc, _ = detect_dlc(text, ekey)
        if is_dlc:
            # Tag in rec dict (in-memory; SQLite not altered)
            rec["collection"] = "tales"
            count += 1
        else:
            # Determine by source_file prefix
            sf = rec.get("source_file", "")
            if sf.startswith("EventMain"):
                rec["collection"] = "main"
            elif sf.startswith("EventSub"):
                rec["collection"] = "side"
            elif sf.startswith("EventBattle"):
                rec["collection"] = "battle"
            elif sf.startswith("EventNormal"):
                rec["collection"] = "random"
            else:
                rec["collection"] = "unknown"
    return count
