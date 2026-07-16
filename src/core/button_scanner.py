"""
button_scanner.py - Classify interactive UI buttons from OCR boxes.

UI-first: navigation buttons (Continue, Begin Battle, OK) are detected
before any RAG quest matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Keyword maps — single source of truth for UI button kinds.
_CONTINUE_KWS = (
    "continue", "kembali", "mulai", "confirm", "confirmar",
    "siguiente", "continuar", "avanti", "prosseguire", "coba lagi",
    "next", "start", "leave",
)
_OK_KWS = ("ok", "okay", "yes", "ya", "확인", "接受")
_CLOSE_KWS = ("close", "x", "tutup", "dismiss", "cancel", "batal")
_BACK_KWS = ("back", "kembali ke", "return", "나가기")
_BATTLE_BEGIN = ("begin battle", "start battle", "전투 시작")
_BATTLE_ABANDON = ("abandon battle", "flee", "retreat", "도망")
_BATTLE_SIM = ("simulate", "simulate battle", "simulation")
_BATTLE_OTHER = ("roll the die", "roll dice", "dodge", "block", "swing weapon")

_CHOICE_NUM_RE = re.compile(r"^\s*([1-9])\s*[.)]\s*(.*)$")
_SEPARATOR_RE = re.compile(r"[═=]+\s*(\d+)\s*[═=]+")


@dataclass
class UIButton:
    kind: str  # continue|choice|battle_begin|battle_abandon|battle_simulate|ok|close|back|unknown
    text: str
    center: Tuple[int, int]
    conf: float = 1.0
    source: str = "ocr"
    choice_idx: Optional[int] = None  # 0-based when kind=choice


class ButtonScanner:
    """Scan OCR boxes → classified interactive buttons."""

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
        # Interactive zone: bottom 55% of window (absolute Y)
        zone_y = top + int(height * 0.45) if height > 0 else 0

        for box in boxes:
            text = (box.get("text") or "").strip()
            if not text:
                continue
            center = box.get("center")
            if not center or len(center) < 2:
                continue
            cx, cy = int(center[0]), int(center[1])
            # Prefer bottom-zone buttons; still allow short labels anywhere
            if height > 0 and cy < zone_y and len(text) > 20:
                continue

            kind, conf, cidx = self._classify_text(text)
            if kind == "unknown" and len(text) > 25:
                continue  # long narrative, not a button
            if kind == "unknown":
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

        # Full-text fallback: "continue" in OCR but no box classified
        text_l = (ocr_text or "").lower()
        if not any(b.kind == "continue" for b in buttons):
            if any(k in text_l for k in ("continue", "kembali")):
                # Synthetic center: bottom-center of window
                if window_rect:
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

        # Sort: battle > continue/ok > choice > rest; then by Y (top first)
        order = {
            "battle_begin": 0,
            "battle_simulate": 1,
            "battle_abandon": 2,
            "continue": 3,
            "ok": 4,
            "close": 5,
            "back": 6,
            "choice": 7,
            "unknown": 9,
        }
        buttons.sort(key=lambda b: (order.get(b.kind, 8), b.center[1]))
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

    def _classify_text(self, text: str) -> Tuple[str, float, Optional[int]]:
        t = text.strip().lower()
        t_clean = t.rstrip(".…").strip()

        # Numbered choice: "1. Attack"
        m = _CHOICE_NUM_RE.match(text.strip())
        if m:
            idx = int(m.group(1)) - 1
            return "choice", 0.95, max(0, idx)

        # Battle phrases (multi-word first)
        if any(k in t for k in _BATTLE_BEGIN):
            return "battle_begin", 0.95, None
        if any(k in t for k in _BATTLE_ABANDON):
            return "battle_abandon", 0.9, None
        if any(k in t for k in _BATTLE_SIM):
            return "battle_simulate", 0.9, None

        # Exact / short labels
        if t_clean in _CONTINUE_KWS or t in _CONTINUE_KWS:
            return "continue", 0.95, None
        if any(k == t_clean or (len(k) >= 4 and k in t) for k in _CONTINUE_KWS):
            if len(t) <= 25:
                return "continue", 0.85, None

        if t_clean in _OK_KWS or t in _OK_KWS:
            return "ok", 0.9, None
        if t_clean in _CLOSE_KWS:
            return "close", 0.85, None
        if any(k in t for k in _BACK_KWS) and len(t) <= 20:
            return "back", 0.8, None

        # Combat action labels sometimes appear as choices without numbers
        if any(k in t for k in _BATTLE_OTHER) and len(t) <= 30:
            return "choice", 0.7, None

        return "unknown", 0.0, None
