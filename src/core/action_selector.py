"""
action_selector.py - Priority-based action selection for autoplay.

Priority: ad > pending_continue > combat > nav/ok/back > merchant/recovery > choice+RAG > action > stuck
With expanded button kinds from button_scanner.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.button_scanner import ButtonScanner, UIButton
from src.core.session_memory import SessionMemory
from src.core.screen_state import ScreenState


@dataclass
class BotAction:
    type: str  # continue|choice|combat|merchant|recovery|explore|social|quest|popup|dismiss|action|scroll|wait|advance
    target_text: Optional[str] = None
    target_center: Optional[tuple] = None
    choice_idx: Optional[int] = None
    event_key: Optional[str] = None
    reason: str = ""
    needs_rag: bool = False


_NAV_KINDS = frozenset(
    {
        "continue",
        "ok",
        "back",
        "close",
        "navigation",
        "popup",
        "binary",
        "dismiss",
    }
)
_NON_RAG_KINDS = frozenset(
    {
        "combat",
        "merchant",
        "recovery",
        "explore",
        "social",
        "quest",
        "navigation",
        "popup",
        "action",
    }
)


class ActionSelector:
    """Choose next bot action from screen + buttons + memory + optional RAG."""

    def __init__(self, scanner: Optional[ButtonScanner] = None):
        self.scanner = scanner or ButtonScanner()

    def needs_rag(
        self,
        screen_state: ScreenState,
        buttons: List[UIButton],
        memory: SessionMemory,
        ad_playing: bool = False,
    ) -> bool:
        if ad_playing or memory.pending_continue:
            return False
        # Binary Yes/No choices also need RAG (E.65) — rare endings matter
        has_binary = self.scanner.first_of(buttons, "binary")
        has_choice = self.scanner.first_of(buttons, "choice_numbered")
        # Nav-only screen without binary/choice → no RAG
        non_rag = self.scanner.first_of(
            buttons, "combat", "merchant", "recovery", "explore",
            "social", "quest", "navigation", "popup", "action",
        )
        if non_rag and not has_choice and not has_binary:
            return False
        if screen_state == ScreenState.CHOICE:
            return True
        # Binary yes/no on any screen: use RAG for alignment-aware pick
        if has_binary and not self.scanner.first_of(buttons, "continue"):
            return True
        return False

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
            btn = self.scanner.first_of(buttons, "continue", "ok", "back")
            if btn:
                return BotAction(
                    type="continue",
                    target_text=btn.text,
                    target_center=btn.center,
                    reason="pending_continue_button",
                )
            return BotAction(type="advance", reason="pending_continue_force")

        # 3. Nav buttons (no RAG)
        btn = self.scanner.first_of(buttons, "continue")
        if btn:
            return BotAction(
                type="continue",
                target_text=btn.text,
                target_center=btn.center,
                reason="continue_button",
            )
        btn = self.scanner.first_of(buttons, "ok", "back", "close", "binary")
        if btn:
            return BotAction(
                type="continue" if btn.kind != "close" else "dismiss",
                target_text=btn.text,
                target_center=btn.center,
                reason=f"nav_{btn.kind}",
            )

        # 4. Combat
        btn = self.scanner.first_of(
            buttons, "combat", "choice_numbered"
        )  # choice_numbered in combat = combat actions
        if screen_state == ScreenState.COMBAT and btn:
            return BotAction(
                type="combat",
                target_text=btn.text,
                target_center=btn.center,
                choice_idx=btn.choice_idx,
                reason=f"combat_{btn.kind}",
            )
        if screen_state == ScreenState.COMBAT:
            return BotAction(type="advance", reason="combat_advance_fallback")

        # 5. Merchant / Recovery / Explore / Social / Quest (non-RAG interactive)
        for kind in ("merchant", "recovery", "explore", "social", "quest", "navigation", "action"):
            btn = self.scanner.first_of(buttons, kind)
            if btn:
                return BotAction(
                    type=btn.kind,
                    target_text=btn.text,
                    target_center=btn.center,
                    reason=f"interactive_{kind}",
                )

        # 6. Dialogue advance (no explicit continue button, but likely dialogue)
        if screen_state == ScreenState.DIALOGUE:
            return BotAction(type="advance", reason="dialogue_advance")

        # 7. Same-event rematch → force continue
        ekey = None
        if rag_result and rag_result.get("event"):
            ekey = rag_result["event"].get("event_key")
        if ekey and memory.should_force_continue(ekey):
            btn = self.scanner.first_of(buttons, "continue", "ok", "action")
            return BotAction(
                type="continue" if btn else "advance",
                target_text=btn.text if btn else None,
                target_center=btn.center if btn else None,
                event_key=ekey,
                reason="same_event_force_continue",
            )

        # 8. Choice + RAG recommendation
        if rag_result and rag_result.get("matched") and recommendation:
            idx = recommendation.get("recommended_choice_idx", -1)
            if idx is not None and idx >= 0:
                choice_txt = recommendation.get("recommended_choice_text") or ""
                btn = None
                for b in buttons:
                    if b.kind == "choice_numbered" and b.choice_idx == idx:
                        btn = b
                        break
                if not btn and choice_txt:
                    cl = choice_txt.lower()
                    for b in buttons:
                        if b.kind == "choice_numbered" and (
                            cl in b.text.lower() or b.text.lower() in cl
                        ):
                            btn = b
                            break
                if not btn:
                    # Any bottom-zone action button as fallback
                    btn = self.scanner.first_of(buttons, "action")
                return BotAction(
                    type="choice",
                    choice_idx=idx,
                    target_text=choice_txt or (btn.text if btn else None),
                    target_center=btn.center if btn else None,
                    event_key=ekey,
                    reason="rag_choice",
                )

        # 9. Continue visible on ambiguous screen
        btn = self.scanner.first_of(buttons, "continue")
        if btn:
            return BotAction(
                type="continue",
                target_text=btn.text,
                target_center=btn.center,
                reason="fallback_continue",
            )

        # 10. Stuck recovery
        if stuck_iterations >= 2:
            return BotAction(type="scroll", reason="stuck_scroll")
        if stuck_iterations >= 3:
            return BotAction(type="advance", reason="stuck_advance")

        return BotAction(type="wait", reason="no_action")
