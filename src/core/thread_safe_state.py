"""
thread_safe_state.py - Central thread-safe state manager for Life in Adventure.
Eliminates race conditions between the UI (main) thread and the auto-play background thread.
All shared mutable state (player stats, language, autoplay flags) flows through here.
"""

import threading
from typing import Dict, List, Any, Optional
import loguru

logger = loguru.logger

# Default player profile — lowercase keys (consistent with OCR parse and HeuristicPolicy).
# hp/sanity/gold defaulted so PPO observation vector has realistic values before OCR scan.
_DEFAULT_STATS = {
    "str": 13, "dex": 13, "int": 13, "cha": 13, "con": 13, "wis": 13,
    "hp": 100, "sanity": 100, "gold": 50,
    "alignment": 0, "exp": 15,
}
_DEFAULT_INVENTORY = ["Shovel", "Lantern"]


class ThreadSafeState:
    """
    Central thread-safe state for all variables shared across the UI thread and
    background worker threads. Uses a single re-entrant lock (RLock) so that a
    holder may re-acquire without deadlocking.

    Properties return *copies* (never live references) so callers cannot mutate
    internal state without going through the setters.
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Player profile (edited via StatsPanel on UI thread, read by auto-play)
        self._player_stats: Dict[str, Any] = dict(_DEFAULT_STATS)
        self._player_inventory: List[str] = list(_DEFAULT_INVENTORY)

        # Language selection (set by Combobox on UI thread, read by auto-play)
        self._active_language: str = "English"

        # Auto-play control (toggled on UI thread, consumed by background loop)
        self._autoplay_active: bool = False
        self._autoplay_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    #  Player stats & inventory
    # ------------------------------------------------------------------ #
    @property
    def player_stats(self) -> Dict[str, Any]:
        """Return a *copy* of the stats dict (thread-safe)."""
        with self._lock:
            return dict(self._player_stats)

    @player_stats.setter
    def player_stats(self, value: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            self._player_stats = dict(value) if value else dict(_DEFAULT_STATS)

    def update_stat(self, key: str, value: Any) -> None:
        """Update a single stat key without replacing the whole dict."""
        with self._lock:
            self._player_stats[key] = value

    @property
    def player_inventory(self) -> List[str]:
        with self._lock:
            return list(self._player_inventory)

    @player_inventory.setter
    def player_inventory(self, value: Optional[List[str]]) -> None:
        with self._lock:
            self._player_inventory = list(value) if value else list(_DEFAULT_INVENTORY)

    # ------------------------------------------------------------------ #
    #  Active language (snapshot — never read Tk StringVar from a thread)
    # ------------------------------------------------------------------ #
    def get_language(self) -> str:
        with self._lock:
            return self._active_language

    def set_language(self, lang: str) -> None:
        with self._lock:
            self._active_language = lang or "English"

    # ------------------------------------------------------------------ #
    #  Auto-play control with thread-singleton guard
    # ------------------------------------------------------------------ #
    @property
    def autoplay_active(self) -> bool:
        with self._lock:
            return self._autoplay_active

    @autoplay_active.setter
    def autoplay_active(self, value: bool) -> None:
        with self._lock:
            self._autoplay_active = bool(value)

    def try_acquire_autoplay(self) -> bool:
        """
        Attempt to start a new auto-play session.
        Returns True only if no previous auto-play thread is still alive.
        Call *before* spawning the thread; pair with register_autoplay_thread().
        """
        with self._lock:
            if self._autoplay_thread is not None and self._autoplay_thread.is_alive():
                return False
            return True

    def register_autoplay_thread(self, thread: threading.Thread) -> None:
        """Record the auto-play worker thread so future toggles can guard against it."""
        with self._lock:
            self._autoplay_thread = thread

    @property
    def autoplay_thread_alive(self) -> bool:
        with self._lock:
            return self._autoplay_thread is not None and self._autoplay_thread.is_alive()
