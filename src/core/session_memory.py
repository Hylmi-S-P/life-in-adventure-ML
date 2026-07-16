"""
session_memory.py - Short-term memory for autoplay decisions.

Remembers last event/action so we don't re-click the same choice after
a result screen still OCR-matches the same quest narrative.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


@dataclass
class SessionMemory:
    last_screen_state: Optional[str] = None
    last_event_key: Optional[str] = None
    last_action: Optional[str] = None  # e.g. "choice:0", "continue", "battle_begin"
    last_choice_text: Optional[str] = None
    action_history: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=20))
    consecutive_same_event: int = 0
    consecutive_same_screen: int = 0
    pending_continue: bool = False  # True after choice click until Continue handled

    def record(
        self,
        action_type: str,
        *,
        event_key: Optional[str] = None,
        screen_state: Optional[str] = None,
        choice_text: Optional[str] = None,
        choice_idx: Optional[int] = None,
        reason: str = "",
    ) -> None:
        action_label = action_type
        if action_type == "choice" and choice_idx is not None:
            action_label = f"choice:{choice_idx}"

        if screen_state and screen_state == self.last_screen_state:
            self.consecutive_same_screen += 1
        else:
            self.consecutive_same_screen = 0

        if event_key and event_key == self.last_event_key:
            self.consecutive_same_event += 1
        elif event_key:
            self.consecutive_same_event = 0

        self.last_action = action_label
        if event_key is not None:
            self.last_event_key = event_key
        if screen_state is not None:
            self.last_screen_state = screen_state
        if choice_text is not None:
            self.last_choice_text = choice_text

        if action_type == "choice":
            self.pending_continue = True
        elif action_type in ("continue", "ok", "dismiss", "battle_begin", "battle_simulate"):
            self.pending_continue = False

        self.action_history.append(
            {
                "action": action_label,
                "event_key": event_key,
                "screen_state": screen_state,
                "choice_text": choice_text,
                "reason": reason,
            }
        )

    def should_force_continue(self, current_event_key: Optional[str]) -> bool:
        """Same quest rematched after we already clicked a choice on it."""
        if not self.pending_continue:
            return False
        if not current_event_key or not self.last_event_key:
            return False
        return current_event_key == self.last_event_key

    def clear_pending(self) -> None:
        self.pending_continue = False

    def recent_actions(self, n: int = 5) -> List[Dict[str, Any]]:
        return list(self.action_history)[-n:]
