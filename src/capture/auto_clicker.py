"""
auto_clicker.py - Ad-Shield Auto-Clicker for Life in Adventure.
Safely executes simulated mouse clicks on recommended choice buttons inside MuMuPlayer,
and pauses execution during video advertisements to protect against misclicks.

Coordinate contract:
  All internal targets are kept in ABSOLUTE SCREEN coordinates.
  Two output adapters at the boundary:
    - Win32: SetCursorPos / mouse_event → directly in screen coords (OK)
    - ADB:  rel = tap - emulator_client_origin (computed from HWND ClientToScreen)
  The capture crop/ROI offsets are handled in ScreenCapture so OCR boxes
  are converted to screen-space BEFORE reaching this module.
"""

import time
import re
from typing import Dict, Any, Optional, List, Tuple
import loguru

try:
    import win32api
    import win32con
    import win32gui
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

logger = loguru.logger


class AutoClicker:
    """
    Automates clicking choice options in MuMuPlayer window based on AI recommendations.
    Enforces strict Ad-Shield lockouts when video ads are detected.
    Detects choice visibility (choice numbers + separator bar) to prevent
    infinite scroll loops when the dialog has already reached the bottom.

    Coordinate contract:
      All (x, y) targets passed to click_choice / click_advance_dialog / _execute_click
      are in ABSOLUTE SCREEN coordinates (the same space as win32gui.GetWindowRect).
      The emulator's window chrome offset is NOT subtracted internally.
      Conversion from game-client-space OCR boxes to screen-space happens in ScreenCapture
      (via capture_origin), so this module receives screen-space coordinates only.
    """

    # Separator pattern: ════════ 20 ════════ (digits between separator lines)
    _SEPARATOR_RE = re.compile(r'[═=]+\s*(\d+)\s*[═=]+')
    # Choice number pattern: "1." "2." etc. at start of OCR text box
    _CHOICE_NUM_RE = re.compile(r'^\s*(\d+)\s*[.)]\s*')

    # ── Choice visibility detection ────────────────────────────────────────
    @classmethod
    def _choices_visible(cls, ocr_boxes: list, ocr_text: str = "") -> bool:
        """
        Return True if numbered choices (1. 2. 3...) or a separator bar
        are visible on screen, indicating the dialog has reached the bottom.
        """
        if not ocr_boxes:
            return False
        num_choices = 0
        for box in ocr_boxes:
            txt = box.get("text", "").strip()
            # Choice number: "1." "2)" "3 ." etc.
            if cls._CHOICE_NUM_RE.match(txt):
                num_choices += 1
            # Separator bar: "20" or "════ 20 ════"
            if cls._SEPARATOR_RE.search(txt):
                return True
        # 2+ numbered items → choices panel is visible
        return num_choices >= 2

    def __init__(
        self,
        screen_capture: Optional[Any] = None,
        click_delay: float = 0.8,
    ):
        self.capture = screen_capture
        self.click_delay = click_delay
        self._consecutive_scrolls = 0  # anti-infinite-loop: reset on click/transition
        try:
            from src.capture.adb_bridge import AdbBridge
            self.adb = AdbBridge()
        except Exception:
            self.adb = None

    def _get_screen_rect(self) -> Tuple[Optional[int], Optional[Dict[str, int]]]:
        """
        Return (hwnd, window_rect) from the attached ScreenCapture.
        Window rect is in absolute screen coordinates (win32gui.GetWindowRect convention).
        """
        if not self.capture:
            return None, None
        hwnd = getattr(self.capture, "hwnd", None)
        rect = getattr(self.capture, "window_rect", None)
        return hwnd, rect

    def _ensure_window_focus(self) -> bool:
        """Ensure the emulator window is in the foreground."""
        if not _WIN32_AVAILABLE:
            return False
        hwnd, _ = self._get_screen_rect()
        if not hwnd:
            return False
        try:
            if not win32gui.IsWindow(hwnd):
                if hasattr(self.capture, "_find_emulator_window"):
                    self.capture._find_emulator_window()
                hwnd, _ = self._get_screen_rect()
            if hwnd and win32gui.IsWindow(hwnd):
                if win32gui.GetForegroundWindow() != hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.12)
                return True
        except Exception as e:
            logger.debug(f"Could not focus emulator window: {e}")
        return False

    # ------------------------------------------------------------------ #
    #  Public click API
    #  All targets are in ABSOLUTE SCREEN coordinates.
    # ------------------------------------------------------------------ #

    def click_choice(
        self,
        choice_idx: int,
        window_rect: Optional[Dict[str, int]] = None,
        choice_text: str = "",
        ocr_boxes: Optional[List[dict]] = None,
        choices_count: int = 1
    ) -> bool:
        """
        Simulate clicking a numbered choice option (0-indexed).

        Click targeting strategy (in priority order):
        1. OCR bounding box: if RapidFuzz match score > 55, use box center
        2. Advance button detection: if screen transitioned to Continue/Kembali state
        3. Fallback button detection: generic keywords in bottom area
        4. Geometric calculation: percentage-based from window rect

        All computed targets are in ABSOLUTE SCREEN coordinates.
        """
        if self.capture and getattr(self.capture, "ad_playing", False):
            logger.warning("Ad is currently playing. Choice click aborted.")
            return False

        rect = window_rect
        if not rect:
            _, rect = self._get_screen_rect()

        if not rect or not _WIN32_AVAILABLE:
            if not _WIN32_AVAILABLE:
                logger.warning("win32api not available. Skipping click.")
            return False

        top   = rect["top"]
        left  = rect["left"]
        width  = rect["width"]
        height = rect["height"]

        if choice_idx < 0:
            logger.debug("Negative choice_idx. Redirecting to advance click.")
            return self.click_advance_dialog(window_rect=rect, scroll_first=True, ocr_boxes=ocr_boxes)

        # Geometric fallback position (used if OCR targeting fails).
        # Targets are in ABSOLUTE SCREEN coordinates.
        choices_count = max(1, choices_count)
        base_y_pct = 0.86 - max(0, choices_count - 1 - choice_idx) * 0.08
        target_x = left + int(width * 0.5)
        target_y = top + int(height * base_y_pct)
        dynamic_matched = False

        # ── 1. OCR Bounding Box Targeting ────────────────────────────────────
        if ocr_boxes:
            clean_choice = choice_text.strip().lower() if choice_text else ""
            best_box_center = None
            choice_visible = False

            # Exact substring match — only in bottom 50% where choice buttons live
            choice_zone_y = top + int(height * 0.50)
            for box in ocr_boxes:
                box_txt = box.get("text", "").strip().lower()
                if not box_txt:
                    continue
                center = box.get("center")
                if not center:
                    continue
                # Only match in the choice-button zone (bottom half of window)
                if center[1] < choice_zone_y:
                    continue
                if clean_choice and (clean_choice in box_txt or box_txt in clean_choice):
                    best_box_center = center
                    choice_visible = True
                    logger.info(f"🎯 OCR exact match: '{choice_text[:30]}' -> {best_box_center}")
                    break

            # Fuzzy match with lowered threshold (was 75 → now 55)
            # Also constrained to bottom 50% where choice buttons live.
            if not choice_visible and clean_choice:
                try:
                    from rapidfuzz import fuzz
                    best_score = 0.0
                    for box in ocr_boxes:
                        box_txt = box.get("text", "").strip().lower()
                        if not box_txt:
                            continue
                        center = box.get("center")
                        if not center or center[1] < choice_zone_y:
                            continue
                        score = fuzz.token_set_ratio(clean_choice, box_txt)
                        if score > 55 and score > best_score:
                            best_score = score
                            best_box_center = center
                            choice_visible = True
                    if choice_visible:
                        logger.info(f"🎯 OCR fuzzy match ({best_score:.0f}): '{choice_text[:30]}' -> {best_box_center}")
                except ImportError:
                    pass

            # ── 2. Advance Button Detection ─────────────────────────────────────
            # Only triggered when OCR cannot find the choice text directly.
            # Looks for Continue/Next/OK buttons in the lower portion of the screen.
            # Short keywords (≤3 chars like "ok", "다음") require stricter matching
            # to avoid false positives (e.g. "looks" contains "ok").
            if not choice_visible:
                advance_kws_long = [
                    "continue", "kembali", "mulai", "confirm",
                    "start", "next", "leave", "siguiente", "continuar", "confirmar",
                    "avanti", "prosseguire", "coba lagi",
                ]
                advance_kws_short = [
                    "ok", "clover", "次の", "承諾します", "다음", "계속", "확인", "接受",
                ]
                bottom_cutoff = top + int(height * 0.55)  # only bottom 45%
                for box in ocr_boxes:
                    center = box.get("center")
                    if not center:
                        continue
                    if center[1] < top + int(height * 0.20):
                        continue
                    box_txt = box.get("text", "").strip().lower()
                    if len(box_txt) > 25:
                        continue
                    # Long keywords: substring match, but must be in bottom 45%
                    # (dialog body text like "continue the story" is not a button)
                    if any(k in box_txt for k in advance_kws_long):
                        if center[1] < bottom_cutoff:
                            continue
                        best_box_center = center
                        choice_visible = True
                        logger.info(f"⏭️ Advance button detected: '{box.get('text','')}' at {center}")
                        break
                    # Short keywords: exact match only + box must be in bottom half
                    # AND box text must be short (<15 chars) to avoid false positives
                    # like "looks" matching "ok" or "that" matching "次の"
                    if len(box_txt) <= 15 and center[1] >= bottom_cutoff:
                        box_txt_stripped = box_txt.strip()
                        if any(k == box_txt_stripped or (len(k) >= 2 and box_txt_stripped.startswith(k)) for k in advance_kws_short):
                            best_box_center = center
                            choice_visible = True
                            logger.info(f"⏭️ Advance button detected (short): '{box.get('text','')}' at {center}")
                            break

            # ── 3. Generic Fallback Buttons ─────────────────────────────────────
            if not choice_visible and choice_idx == 0 and choices_count <= 2:
                fallback_kws = ["leave", "continue", "confirm", "ok",
                               "start", "next", "take", "attack", "run", "[1]", "1."]
                for box in ocr_boxes:
                    center = box.get("center")
                    if not center:
                        continue
                    # center is absolute screen coords; skip boxes above 72% height
                    if center[1] < top + int(height * 0.72):
                        continue
                    box_txt = box.get("text", "").strip().lower()
                    if any(k in box_txt for k in fallback_kws):
                        best_box_center = center
                        choice_visible = True
                        logger.info(f"🎯 Fallback button: '{box_txt}' at {center}")
                        break

            if best_box_center:
                target_x = best_box_center[0]
                target_y = best_box_center[1]
                dynamic_matched = True
                logger.info(f"🎯 Dynamic click target: ({target_x}, {target_y})")

        # ── 4. Geometric fallback (no OCR match) ──────────────────────────────
        if not dynamic_matched:
            target_x = left + int(width * 0.5)
            target_y = top + int(height * base_y_pct)
            # Scroll down if choice is below fold
            if choice_idx >= 2 or (choices_count > 2 and choice_idx >= choices_count - 1):
                logger.info(f"📜 Choice #{choice_idx + 1} below fold. Scrolling down...")
                self.scroll_down_dialog(window_rect=rect)
                time.sleep(0.4)
                target_y = top + int(height * (0.86 - max(0, choices_count - 1 - choice_idx) * 0.08))

        # target_x, target_y are in ABSOLUTE SCREEN coords
        return self._execute_click(target_x, target_y, f"choice #{choice_idx}", rect)

    def click_advance_dialog(
        self,
        window_rect: Optional[Dict[str, int]] = None,
        scroll_first: bool = False,
        ocr_boxes: Optional[List[dict]] = None
    ) -> bool:
        """
        Tap the dialogue advancement area (~86% down screen center).
        If scroll_first=True, swipes up to reveal hidden content first.
        All targets are in ABSOLUTE SCREEN coordinates.
        """
        if self.capture and getattr(self.capture, "ad_playing", False):
            return False

        rect = window_rect
        if not rect:
            _, rect = self._get_screen_rect()

        if not rect or not _WIN32_AVAILABLE:
            return False

        if scroll_first:
            self.scroll_down_dialog(window_rect=rect)

        # Geometric fallback in ABSOLUTE SCREEN coords
        target_x = rect["left"] + int(rect["width"] * 0.5)
        target_y = rect["top"] + int(rect["height"] * 0.86)

        ocr_matched = False
        if ocr_boxes:
            # NOTE: do NOT include "begin" — "Begin Battle" is a combat button,
            # not a dialogue advance. Combat is handled by ScreenStateMachine.
            advance_kws_long = [
                "continue", "kembali", "mulai", "confirm",
                "start", "next", "leave", "siguiente", "continuar", "confirmar",
                "avanti", "prosseguire", "coba lagi",
            ]
            # Short keywords: only match exact or prefix, box text ≤15 chars,
            # must be in bottom 45% of screen.
            advance_kws_short = [
                "ok", "clover", "次の", "承諾します", "다음", "계속", "확인", "接受",
            ]
            bottom_y = rect["top"] + int(rect["height"] * 0.55)
            for box in ocr_boxes:
                center = box.get("center")
                if not center:
                    continue
                if center[1] < rect["top"] + int(rect["height"] * 0.20):
                    continue
                box_txt = box.get("text", "").strip().lower()
                if len(box_txt) > 25:
                    continue
                if any(k in box_txt for k in advance_kws_long):
                    # Must be in bottom 45% — "continue" in dialog body text
                    # is not a clickable button
                    if center[1] < bottom_y:
                        continue
                    target_x = center[0]
                    target_y = center[1]
                    ocr_matched = True
                    logger.info(f"🎯 Advance button OCR target: '{box_txt}' -> ({target_x}, {target_y})")
                    break
                if len(box_txt) <= 15 and center[1] >= bottom_y:
                    box_txt_stripped = box_txt.strip()
                    if any(k == box_txt_stripped or (len(k) >= 2 and box_txt_stripped.startswith(k)) for k in advance_kws_short):
                        target_x = center[0]
                        target_y = center[1]
                        ocr_matched = True
                        logger.info(f"🎯 Advance button OCR target: '{box_txt}' -> ({target_x}, {target_y})")
                        break

        if not ocr_matched:
            logger.info(f"🖱️ Advance geometric fallback: ({target_x}, {target_y})")

        return self._execute_click(target_x, target_y, "advance", rect)

    def _execute_click(self, x: int, y: int, label: str, window_rect: Optional[Dict[str, int]] = None) -> bool:
        """
        Execute a single click at (x, y) in ABSOLUTE SCREEN coordinates.
        Uses ADB if connected (computes emulator-relative tap coords internally),
        otherwise Win32api SetCursorPos / mouse_event.
        """
        try:
            logger.info(f"🖱️ Clicking {label} at ({x}, {y})...")
            if self.adb and getattr(self.adb, "connected", False):
                # Compute emulator client origin from HWND for ADB scaling.
                hwnd, rect = self._get_screen_rect()
                wr = window_rect or rect or {}
                if hwnd and _WIN32_AVAILABLE:
                    try:
                        client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
                        rel_x = x - client_origin[0]
                        rel_y = y - client_origin[1]
                    except Exception:
                        rel_x = x - wr.get("left", 0)
                        rel_y = y - wr.get("top", 0)
                else:
                    rel_x = x - wr.get("left", 0)
                    rel_y = y - wr.get("top", 0)
                # CRITICAL: ADB must scale from PC window size → emulator internal resolution
                win_w = wr.get("width", 0)
                win_h = wr.get("height", 0)
                if self.adb.tap(rel_x, rel_y, win_width=win_w, win_height=win_h):
                    time.sleep(self.click_delay)
                    return True
                # ADB tap failed — fall through to Win32

            if not _WIN32_AVAILABLE:
                logger.warning("ADB tap failed and Win32 unavailable. Click not executed.")
                return False

            self._ensure_window_focus()
            # Win32 SetCursorPos and mouse_event use absolute screen coordinates
            win32api.SetCursorPos((x, y))
            time.sleep(0.15)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            time.sleep(0.08)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
            time.sleep(self.click_delay)
            return True
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return False

    def scroll_down_dialog(self, window_rect: Optional[Dict[str, int]] = None) -> bool:
        """
        Simulate a swipe up inside the dialogue container to scroll content DOWN,
        revealing choice buttons or text located below the fold.
        All swipe coordinates are in ABSOLUTE SCREEN coordinates.

        Returns False if the anti-infinite-loop guard triggers (>5 consecutive
        scrolls without reset). Call reset_scroll_guard() after a successful
        click or screen transition.
        """
        if self.capture and getattr(self.capture, "ad_playing", False):
            return False

        # ── Anti-infinite-loop: max 5 consecutive scrolls ──────────────
        self._consecutive_scrolls += 1
        if self._consecutive_scrolls > 5:
            logger.warning("🛑 Scroll guard: 5+ consecutive scrolls — refusing to scroll further.")
            return False

        rect = window_rect
        if not rect:
            _, rect = self._get_screen_rect()

        if not rect or not _WIN32_AVAILABLE:
            return False

        # Swipe points in ABSOLUTE SCREEN coords
        center_x = rect["left"] + int(rect["width"] * 0.5)
        start_y  = rect["top"] + int(rect["height"] * 0.82)
        end_y    = rect["top"] + int(rect["height"] * 0.35)

        try:
            logger.info(f"📜 Scrolling dialogue container (swipe #{self._consecutive_scrolls})...")
            if self.adb and getattr(self.adb, "connected", False):
                hwnd, _ = self._get_screen_rect()
                if hwnd and _WIN32_AVAILABLE:
                    try:
                        client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
                        rel_x = center_x - client_origin[0]
                        rel_start = start_y - client_origin[1]
                        rel_end   = end_y   - client_origin[1]
                    except Exception:
                        rel_x = int(rect["width"] * 0.5)
                        rel_start = int(rect["height"] * 0.82)
                        rel_end   = int(rect["height"] * 0.35)
                else:
                    rel_x = int(rect["width"] * 0.5)
                    rel_start = int(rect["height"] * 0.82)
                    rel_end   = int(rect["height"] * 0.35)
                # CRITICAL: scale from PC window → emulator internal resolution
                win_w = rect.get("width", 0)
                win_h = rect.get("height", 0)
                if self.adb.swipe(rel_x, rel_start, rel_x, rel_end, duration_ms=320,
                                  win_width=win_w, win_height=win_h):
                    time.sleep(0.4)
                    return True

            self._ensure_window_focus()
            win32api.SetCursorPos((center_x, start_y))
            time.sleep(0.12)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, center_x, start_y, 0, 0)
            time.sleep(0.08)
            steps = 10
            for step in range(1, steps + 1):
                inter_y = start_y + int((end_y - start_y) * (step / steps))
                win32api.SetCursorPos((center_x, inter_y))
                win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, int((end_y - start_y) / steps), 0, 0)
                time.sleep(0.02)
            time.sleep(0.08)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, center_x, end_y, 0, 0)
            time.sleep(0.4)
            return True
        except Exception as e:
            logger.debug(f"Scroll failed: {e}")
            return False

    def reset_scroll_guard(self) -> None:
        """Reset the consecutive scroll counter. Call after a successful click or transition."""
        self._consecutive_scrolls = 0
