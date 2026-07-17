"""
button_scanner.py - Classify interactive UI buttons from OCR boxes.

Button kinds (expanded taxonomy for Life in Adventure):
  continue | choice | combat | merchant | recovery | explore | social |
  quest | popup | binary | navigation | action (generic bottom-zone tap) | unknown

Any bottom-zone non-garbage text that does not match specific keywords
is still classified as 'action' so the bot never misses a tap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import re

# ── Choice / separator patterns ────────────────────────────────────────
_CHOICE_NUM_RE = re.compile(r"^\s*([1-9])\s*[.)]\s*(.*)$")
_SEPARATOR_RE = re.compile(r"[═=]+\s*(\d+)\s*[═=]+")
_TWO_DIGIT_OPTION_RE = re.compile(r"^\s*([1-9][0-9]?)\s*[.)]\s*")

# ── Keyword clusters — single source of truth ──────────────────────────
_CONTINUE = frozenset(
    "continue|kembali|mulai|confirm|confirmar|siguiente|continuar|avanti|prosseguire|coba lagi|next|start|leave".split(
        "|"
    )
)
_OK = frozenset("ok|okay|yes|ya|sure|fine|확인|接受".split("|"))
_CLOSE = frozenset("close|x|tutup|dismiss|cancel|batal|exit|quit".split("|"))
_BACK = frozenset("back|kembali ke|return|previous|나가기".split("|"))

_COMBAT = frozenset(
    "begin battle|start battle|전투 시작|abandon battle|flee|retreat|도망"
    "|simulate|simulate battle|simulation|roll the die|roll dice"
    "|swing weapon|dodge|block|defend|charge|prepare|cast|spell|use item"
    "|attack|fight|battle|strike|shoot|pierce|slash|bash|smash".split("|")
)

_MERCHANT = frozenset(
    "buy|sell|trade|barter|appraise|purchase|shop|store|market|price|deal"
    "|interested|need anything|wares|inventory|item|equip|upgrade|craft|combine"
    "|pay|spend|gold|price".split("|")
)

_RECOVERY = frozenset(
    "rest|camp|sleep|eat|drink|heal|recover|repair|medicate|bandage|first aid"
    "|sit|wait|pass time|digest".split("|")
)

_EXPLORE = frozenset(
    "search|investigate|examine|inspect|look|observe|listen|sniff|touch"
    "|open|unlock|push|pull|climb|jump|descend|ascend|enter|exit|approach"
    "|check|read|study".split("|")
)

_SOCIAL = frozenset(
    "talk|speak|ask|question|request|gift|give|offer|bribe|threaten"
    "|persuade|convince|deceive|lie|flirt|charm|intimidate|praise|insult"
    "|tell|share|listen".split("|")
)

_QUEST = frozenset(
    "accept|decline|start|begin|begin quest|take quest|abandon quest"
    "|report|complete|turn in|tales|background|dlc|special".split("|")
)

_BINARY = frozenset("yes|no|yeah|nope|sure|never|always".split("|"))

_NAV = frozenset(
    "skip|auto|speed up|retry|revive|collect|loot|gather|grab|claim reward"
    "|settings|options|inventory|stats|character|map|quest log|journal|menu"
    "|save|load|continue game|new game|main menu".split("|")
)

_INTERACTIVE_ZONE_BOTTOM = 0.45  # bottom 55% of window


@dataclass
class UIButton:
    kind: str  # continue|choice|combat|merchant|recovery|explore|social|quest|popup|binary|navigation|action|unknown
    text: str
    center: Tuple[int, int]
    conf: float = 1.0
    source: str = "ocr"
    choice_idx: Optional[int] = None


class ButtonScanner:
    """Scan OCR boxes → classified interactive buttons. Generic fallback for unknowns."""

    # Classification priority order
    _CLASSIFIERS: List[Tuple[str, float, Any]] = []

    def __init__(self):
        # Build classification pipeline (kind, confidence, keyword-set-or-callable)
        self._pipeline = [
            ("choice_numbered", 0.95, _CHOICE_NUM_RE),
            ("combat", 0.90, _COMBAT),
            ("continue", 0.90, _CONTINUE),
            ("binary", 0.85, _BINARY),
            ("merchant", 0.80, _MERCHANT),
            ("recovery", 0.80, _RECOVERY),
            ("explore", 0.80, _EXPLORE),
            ("social", 0.80, _SOCIAL),
            ("quest", 0.85, _QUEST),
            ("navigation", 0.80, _NAV),
            ("ok", 0.85, _OK),
            ("close", 0.85, _CLOSE),
            ("back", 0.80, _BACK),
        ]

    def scan(
        self,
        ocr_boxes: Optional[List[Dict[str, Any]]],
        ocr_text: str = "",
        window_rect: Optional[Dict[str, int]] = None,
    ) -> List[UIButton]:
        boxes = ocr_boxes or []
        buttons: List[UIButton] = []
        top = (window_rect or {}).get("top", 0)
        height = (window_rect or {}).get("height", 0)
        zone_y = top + int(height * (1 - _INTERACTIVE_ZONE_BOTTOM)) if height > 0 else 0

        for box in boxes:
            text = (box.get("text") or "").strip()
            if not text:
                continue
            center = box.get("center")
            if not center or len(center) < 2:
                continue
            cx, cy = int(center[0]), int(center[1])

            kind, conf, cidx = self._classify(text, ocr_text)
            if kind == "unknown" and len(text) > 25:
                continue  # long narrative, not interactive

            if kind == "unknown":
                # Generic fallback: any text in bottom interactive zone → clickable
                if height > 0 and cy >= zone_y and len(text) <= 30:
                    kind = "action"
                    conf = 0.5
                else:
                    continue

            buttons.append(
                UIButton(
                    kind=kind,
                    text=text,
                    center=(cx, cy),
                    conf=conf,
                    source="ocr",
                    choice_idx=cidx,
                )
            )

        # Full-text fallback: "continue" / "kembali" in OCR but no box classified
        text_l = (ocr_text or "").lower()
        if not any(b.kind in ("continue", "ok", "action") for b in buttons):
            for kw in ("continue", "kembali"):
                if kw in text_l and window_rect:
                    left = window_rect.get("left", 0)
                    w = window_rect.get("width", 400)
                    t = window_rect.get("top", 0)
                    h = window_rect.get("height", 800)
                    buttons.append(
                        UIButton(
                            kind="continue",
                            text="Continue",
                            center=(left + w // 2, t + int(h * 0.86)),
                            conf=0.6,
                            source="ocr_fulltext",
                        )
                    )
                    break

        # Sort: combat/battle first, then continue/ok, then rest; by Y top-first
        order_priority = {
            "combat": 0,
            "continue": 1,
            "ok": 2,
            "back": 3,
            "binary": 4,
            "quest": 5,
            "merchant": 6,
            "recovery": 7,
            "explore": 8,
            "social": 9,
            "navigation": 10,
            "close": 11,
            "popup": 12,
            "choice_numbered": 13,
            "action": 14,
        }
        buttons.sort(key=lambda b: (order_priority.get(b.kind, 15), b.center[1]))
        return buttons

    def has_kind(self, buttons: List[UIButton], *kinds: str) -> bool:
        return any(b.kind in kinds for b in buttons)

    def first_of(self, buttons: List[UIButton], *kinds: str) -> Optional[UIButton]:
        for b in buttons:
            if b.kind in kinds:
                return b
        return None

    def choices_visible(self, ocr_boxes: Optional[List[Dict[str, Any]]], ocr_text: str = "") -> bool:
        """True if numbered choices or separator bar visible."""
        boxes = ocr_boxes or []
        n = 0
        for box in boxes:
            t = (box.get("text") or "").strip()
            if _CHOICE_NUM_RE.match(t):
                n += 1
            if _SEPARATOR_RE.search(t):
                return True
        if n >= 2:
            return True
        if _SEPARATOR_RE.search(ocr_text or ""):
            return True
        return False

    def _classify(self, text: str, full_text: str = "") -> Tuple[str, float, Optional[int]]:
        """Return (kind, confidence, choice_idx)."""
        t = text.strip()
        t_lower = t.lower()
        t_clean = t_lower.rstrip(".…!?").strip()

        # 1. Numbered choice: "1. Attack"
        m = _CHOICE_NUM_RE.match(t)
        if m:
            idx = int(m.group(1)) - 1
            return "choice_numbered", 0.95, max(0, idx)

        # 2. Two-digit option: "10." "12)" (combat quick-select)
        m2 = _TWO_DIGIT_OPTION_RE.match(t)
        if m2:
            idx = int(m2.group(1)) - 1
            return "choice_numbered", 0.90, max(0, idx)

        # 3. Specific keyword kinds (pipeline)
        for kind, conf, matcher in self._pipeline:
            if isinstance(matcher, re.Pattern):
                if matcher.match(t):
                    return kind, conf, None
            elif isinstance(matcher, frozenset):
                # Exact and contains matching
                if t_lower in matcher:
                    return kind, conf, None
                if len(t) <= 30:
                    for kw in matcher:
                        if len(kw) >= 4 and kw in t_lower:
                            return kind, conf, None
            else:
                # fallback: backward compat
                if t_lower in matcher:
                    return kind, conf, None

        # 4. Combat action patterns (no single keyword)
        if any(kw in t_lower for kw in ("dodge", "block", "roll the die", "swing weapon")):
            return "combat", 0.85, None

        # 5. Generic - any short text with leading number section separator
        if re.match(r"^\d+[\s.]", t) and len(t) <= 35:
            return "choice_numbered", 0.60, None

        # 6. Single word, ≤ 3 chars, all alphabetic → likely binary/popup
        if len(t) <= 3 and t.isalpha() and len(full_text.split()) <= 10:
            return "action", 0.60, None

        return "unknown", 0.0, None
