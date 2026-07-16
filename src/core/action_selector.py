"""
action_selector.py - Priority-based action selection for autoplay.

UI navigation buttons beat RAG quest matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.button_scanner import ButtonScanner, UIButton
from src.core.session_memory import SessionMemory
from src.core.screen_state import ScreenState


@dataclass
class BotAction:
    type: str  # continue|choice|battle|dismiss|scroll|wait|advance
    target_text: Optional[str] = None
    target_center: Optional[tuple] = None
    choice_idx: Optional[int] = None
    event_key: Optional[str] = None
    reason: str = ""
    needs_rag: bool = False


class ActionSelector:
    """Pick next bot action from screen state + buttons + memory (+ optional RAG)."""

    def __init__(self, scanner: Optional[ButtonScanner] = None):
        self.scanner = scanner or ButtonScanner()

    def needs_rag(
        self,
        screen_state: ScreenState,
        buttons: List[UIButton],
        memory: SessionMemory,
        ad_playing: bool = False,
    ) -> bool:
        if ad_playing:
            return False
        if memory.pending_continue:
            return False
        # Nav buttons take priority — no RAG needed
        if self.scanner.first_of(
            buttons, "continue", "ok", "close", "back",
            "battle_begin", "battle_abandon", "battle_simulate",
        ):
            # Exception: pure choice screen may also show "continue" rarely
            if screen_state == ScreenState.CHOICE and self.scanner.first_of(buttons, "choice"):
                return True
            if screen_state in (ScreenState.DIALOGUE, ScreenState.COMBAT):
                return False
            # continue-only → no RAG
            if self.scanner.first_of(buttons, "continue", "ok") and not self.scanner.first_of(
                buttons, "choice"
            ):
                return False
        if screen_state in (ScreenState.DIALOGUE, ScreenState.COMBAT, ScreenState.AD, ScreenState.STATS):
            return False
        return screen_state == ScreenState.CHOICE or screen_state == ScreenState.UNKNOWN

    def select(
        self,
        screen_state: ScreenState,
        buttons: List[UIButton],
        memory: SessionMemory,
        rag_result: Optional[Dict[str, Any]] = None,
        recommendation: Optional[Dict[str, Any]] = None,
        ad_playing: bool = False,
        stuck_iterations: int = 0,
    ) -> BotAction:
        # 1. Ad
        if ad_playing or screen_state == ScreenState.AD:
            return BotAction(type="wait", reason="ad_playing")

        # 2. Pending continue after a choice click
        if memory.pending_continue:
            btn = self.scanner.first_of(buttons, "continue", "ok")
            if btn:
                return BotAction(
                    type="continue",
                    target_text=btn.text,
                    target_center=btn.center,
                    reason="pending_continue_button",
                )
            # Force advance even without classified button
            return BotAction(type="advance", reason="pending_continue_force")

        # 3. Explicit nav buttons (no RAG)
        btn = self.scanner.first_of(buttons, "continue")
        if btn and screen_state != ScreenState.CHOICE:
            return BotAction(
                type="continue",
                target_text=btn.text,
                target_center=btn.center,
                reason="continue_button",
            )
        if btn and screen_state == ScreenState.DIALOGUE:
            return BotAction(
                type="continue",
                target_text=btn.text,
                target_center=btn.center,
                reason="dialogue_continue",
            )

        btn = self.scanner.first_of(buttons, "ok", "close")
        if btn:
            return BotAction(
                type="dismiss",
                target_text=btn.text,
                target_center=btn.center,
                reason=f"dismiss_{btn.kind}",
            )

        # 4. Battle
        if screen_state == ScreenState.COMBAT or self.scanner.first_of(
            buttons, "battle_begin", "battle_simulate", "battle_abandon"
        ):
            btn = self.scanner.first_of(buttons, "battle_begin", "battle_simulate")
            if not btn:
                btn = self.scanner.first_of(buttons, "battle_abandon")
            if btn:
                return BotAction(
                    type="battle",
                    target_text=btn.text,
                    target_center=btn.center,
                    reason=f"battle_{btn.kind}",
                )
            return BotAction(type="advance", reason="combat_advance_fallback")

        # 5. Dialogue without choice
        if screen_state == ScreenState.DIALOGUE:
            btn = self.scanner.first_of(buttons, "continue", "ok")
            if btn:
                return BotAction(
                    type="continue",
                    target_text=btn.text,
                    target_center=btn.center,
                    reason="dialogue_nav",
                )
            return BotAction(type="advance", reason="dialogue_advance")

        # 6. Same-event rematch → force continue
        ekey = None
        if rag_result and rag_result.get("event"):
            ekey = rag_result["event"].get("event_key")
        if ekey and memory.should_force_continue(ekey):
            btn = self.scanner.first_of(buttons, "continue", "ok")
            return BotAction(
                type="continue" if btn else "advance",
                target_text=btn.text if btn else None,
                target_center=btn.center if btn else None,
                event_key=ekey,
                reason="same_event_force_continue",
            )

        # 7. CHOICE + RAG recommendation
        if rag_result and rag_result.get("matched") and recommendation:
            idx = recommendation.get("recommended_choice_idx", -1)
            if idx is not None and idx >= 0:
                # Prefer button with matching choice_idx or text
                choice_txt = recommendation.get("recommended_choice_text") or ""
                btn = None
                for b in buttons:
                    if b.kind == "choice" and b.choice_idx == idx:
                        btn = b
                        break
                if not btn and choice_txt:
                    cl = choice_txt.lower()
                    for b in buttons:
                        if b.kind == "choice" and (
                            cl in b.text.lower() or b.text.lower() in cl
                        ):
                            btn = b
                            break
                return BotAction(
                    type="choice",
                    choice_idx=idx,
                    target_text=choice_txt or (btn.text if btn else None),
                    target_center=btn.center if btn else None,
                    event_key=ekey,
                    reason="rag_choice",
                )

        # Continue visible on ambiguous choice screen without strong RAG
        btn = self.scanner.first_of(buttons, "continue")
        if btn:
            return BotAction(
                type="continue",
                target_text=btn.text,
                target_center=btn.center,
                reason="fallback_continue",
            )

        # 8. Stuck recovery
        if stuck_iterations >= 2:
            return BotAction(type="scroll", reason="stuck_scroll")
        if stuck_iterations >= 3:
            return BotAction(type="advance", reason="stuck_advance")

        return BotAction(type="wait", reason="no_action")
