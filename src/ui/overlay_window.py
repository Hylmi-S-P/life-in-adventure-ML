"""
overlay_window.py - CustomTkinter Transparent UI Overlay for Life in Adventure.
Displays real-time event identification, D20 stat requirements, and AI choice recommendations
directly alongside MuMuPlayer.
"""

import sys
import re
import time
import threading
from typing import Dict, List, Any, Optional, Tuple
import loguru

from src.core.thread_safe_state import ThreadSafeState
from src.core.screen_dedup import ScreenDeduplicator
from src.core.screen_state import ScreenStateMachine, ScreenState
from src.core.button_scanner import ButtonScanner
from src.core.session_memory import SessionMemory
from src.core.action_selector import ActionSelector, BotAction
from src.core.safety import LoadingState, DeadLoopState, MultiStepPlan, detect_dlc, tag_dlc_events
from src.capture.auto_clicker import AutoClicker

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False
    import tkinter as ctk

logger = loguru.logger


class OverlayWindow:
    """
    Floating, topmost, semi-transparent UI window that docks near MuMuPlayer.
    Shows current identified event, AI choice scores, and manual search bar.
    """

    def __init__(self, config: Optional[Any] = None):
        if _CTK_AVAILABLE:
            ctk.set_appearance_mode("Dark")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = ctk.Tk()

        self.root.title("Life in Adventure AI Assistant")
        self.root.geometry("420x580+50+50")
        self.root.minsize(360, 400)
        
        # Window attributes for overlay mode
        try:
            self.root.wm_attributes("-topmost", True)
            self.root.wm_attributes("-alpha", 0.93)
        except Exception as e:
            logger.debug(f"Could not set window topmost/alpha attributes: {e}")

        self.capture = None
        self.ocr = None
        self.normalizer = None
        self.retriever = None
        self.ai_engine = None

        # Central thread-safe state (eliminates race conditions between UI & worker threads)
        self.state = ThreadSafeState()
        # Legacy attribute aliases kept so StatsPanel / external code still works.
        # Reads return copies; writes proxy through the thread-safe state.
        self.player_inventory = self.state.player_inventory  # cached snapshot

        # Frame deduplication: skip OCR+RAG when the screen hasn't changed.
        self.dedup = ScreenDeduplicator()

        from src.capture.session_logger import SessionLogger
        self.session_logger = SessionLogger()

        self._build_ui()

    def _build_ui(self):
        """Construct CustomTkinter layout."""
        # Top Header & Status Bar
        self.header_frame = ctk.CTkFrame(self.root, corner_radius=8)
        self.header_frame.pack(fill="x", padx=10, pady=8)

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="⚔️ LiA Quest Assistant v1.0",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.pack(side="left", padx=10, pady=8)

        self.status_label = ctk.CTkLabel(
            self.header_frame,
            text="Ready",
            text_color="orange",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.status_label.pack(side="right", padx=10, pady=8)

        # Language dropdown selector
        self.lang_var = ctk.StringVar(value="English")
        self.lang_dropdown = ctk.CTkComboBox(
            self.header_frame,
            values=["English", "Indonesian", "Korean", "Spanish", "Portuguese", "Japanese"],
            variable=self.lang_var,
            width=100,
            font=ctk.CTkFont(size=11)
        )
        self.lang_dropdown.pack(side="right", padx=6, pady=8)
        # Sync language changes into thread-safe state (background thread must NOT
        # read self.lang_var directly — Tk StringVar access from non-main thread
        # can segfault Tcl/Tk).
        self.state.set_language(self.lang_var.get())
        self.lang_dropdown.bind("<<ComboboxSelected>>",
                                 lambda _e: self.state.set_language(self.lang_var.get()))

        # Action Buttons
        self.btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=10, pady=4)

        self.btn_scan = ctk.CTkButton(
            self.btn_frame,
            text="📸 Scan (F9)",
            command=self._on_scan_clicked,
            fg_color="#1f6feb",
            hover_color="#1158c7"
        )
        self.btn_scan.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_autoplay = ctk.CTkButton(
            self.btn_frame,
            text="🎮 Auto (F10)",
            command=self._on_toggle_autoplay,
            width=90,
            fg_color="#6e7681",
            hover_color="#57606a"
        )
        self.btn_autoplay.pack(side="left", padx=(0, 4))

        self.btn_stats = ctk.CTkButton(
            self.btn_frame,
            text="👤 Stats (F11)",
            command=self._on_open_stats,
            width=90,
            fg_color="#8957e5",
            hover_color="#713fc2"
        )
        self.btn_stats.pack(side="left", padx=(0, 4))

        self.btn_feedback = ctk.CTkButton(
            self.btn_frame,
            text="📝 Logs",
            command=self._on_open_feedback,
            width=65,
            fg_color="#bc8c05",
            hover_color="#9e7504"
        )
        self.btn_feedback.pack(side="left", padx=(0, 4))

        self.btn_test_query = ctk.CTkButton(
            self.btn_frame,
            text="⚙️",
            command=self._on_open_settings,
            width=35,
            fg_color="#238636",
            hover_color="#196c2e"
        )
        self.btn_test_query.pack(side="right")

        # Main Info & Event Box
        self.info_frame = ctk.CTkScrollableFrame(self.root, corner_radius=8, label_text="Event & Recommendations")
        self.info_frame.pack(fill="both", expand=True, padx=10, pady=8)

        # Bind Hotkeys
        try:
            self.root.bind("<F9>", lambda e: self._on_scan_clicked())
            self.root.bind("<F10>", lambda e: self._on_toggle_autoplay())
            self.root.bind("<F11>", lambda e: self._on_open_stats())
            logger.info("Bound Hotkeys: F9 (Scan), F10 (Auto-Play Toggle), F11 (Character Stats)")
        except Exception as e:
            logger.debug(f"Could not bind hotkeys: {e}")

        self.event_title_var = ctk.StringVar(value="No event scanned yet.")
        self.event_title_label = ctk.CTkLabel(
            self.info_frame,
            textvariable=self.event_title_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=360,
            justify="left"
        )
        self.event_title_label.pack(anchor="w", padx=8, pady=(4, 8))

        self.reasoning_var = ctk.StringVar(value="Click 'Scan' or enable 'Auto-Play' when inside MuMuPlayer.")
        self.reasoning_label = ctk.CTkLabel(
            self.info_frame,
            textvariable=self.reasoning_var,
            font=ctk.CTkFont(size=12),
            text_color="#8b949e",
            wraplength=360,
            justify="left"
        )
        self.reasoning_label.pack(anchor="w", padx=8, pady=(0, 12))

        # Container for dynamic choice cards
        self.choices_container = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        self.choices_container.pack(fill="x", expand=True)

        # State flags for Auto-Play loop
        self.clicker = None

    # ------------------------------------------------------------------ #
    #  Thread-safe property proxies (UI thread ↔ background thread)
    # ------------------------------------------------------------------ #
    @property
    def player_stats(self) -> Dict[str, Any]:
        """Thread-safe read of player stats (returns a copy)."""
        return self.state.player_stats

    @player_stats.setter
    def player_stats(self, value: Optional[Dict[str, Any]]):
        self.state.player_stats = value

    @property
    def autoplay_active(self) -> bool:
        return self.state.autoplay_active

    @autoplay_active.setter
    def autoplay_active(self, value: bool):
        self.state.autoplay_active = value

    def show_loading(self, message: str = "Loading KB..."):
        """Update status label during background thread init."""
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.configure(text=message, text_color="yellow")
            self.root.update_idletasks()

    def show_error(self, message: str):
        """Display error banner on UI."""
        logger.error(f"UI Error: {message}")
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.configure(text="Error", text_color="red")
        if hasattr(self, "reasoning_var") and self.reasoning_var:
            self.reasoning_var.set(f"⚠️ {message}")

    def attach_components(self, capture, ocr, normalizer, retriever, ai_engine, clicker=None):
        """Attach backend pipeline components including AutoClicker."""
        self.capture = capture
        self.ocr = ocr
        self.normalizer = normalizer
        self.retriever = retriever
        self.ai_engine = ai_engine
        self.clicker = clicker
        
        self.status_label.configure(text="Connected", text_color="#3fb950")
        logger.info("Pipeline components & AutoClicker attached to OverlayWindow.")

    def _on_scan_clicked(self):
        """Trigger background OCR capture and RAG/AI evaluation."""
        if not self.retriever:
            self.show_error("RAG Retriever not yet loaded!")
            return

        self.status_label.configure(text="Scanning...", text_color="orange")
        threading.Thread(target=self._run_scan_thread, daemon=True).start()

    def _on_toggle_autoplay(self):
        """Toggle full autonomous Auto-Play mode on or off."""
        if self.state.autoplay_active:
            # --- STOP ---
            self.state.autoplay_active = False
            self.btn_autoplay.configure(text="🎮 Auto (F10)", fg_color="#6e7681", hover_color="#57606a")
            self.status_label.configure(text="Connected", text_color="#3fb950")
            logger.info("🛑 Auto-Play loop DISABLED.")
            # Automatically pop up Feedback window if there are pending logs!
            if hasattr(self, "session_logger") and self.session_logger.get_pending_logs():
                self.root.after(500, self._on_open_feedback)
            return

        # --- START ---
        # Thread-singleton guard: refuse to spawn a second auto-play loop even
        # if the user double-clicks or a previous thread hasn't exited yet.
        if not self.state.try_acquire_autoplay():
            logger.warning("Auto-Play thread is still running. Ignoring toggle.")
            return

        self.state.autoplay_active = True
        self.btn_autoplay.configure(text="🛑 Stop Auto", fg_color="#da3637", hover_color="#b62a2b")
        self.status_label.configure(text="Auto-Playing...", text_color="#a371f7")

        # Clear previous buffer so feedback window starts fresh
        if hasattr(self, "session_logger"):
            self.session_logger.clear_session_buffer()
        # Reset dedup so the fresh session doesn't inherit stale frame hash
        self.dedup.reset()

        t = threading.Thread(target=self._auto_play_loop, daemon=True)
        self.state.register_autoplay_thread(t)
        t.start()
        logger.info("🤖 Full Autonomous Auto-Play loop ENABLED.")

    def _on_open_stats(self):
        """Open Player Character Profile & Stat adjustment dialog."""
        try:
            from src.ui.stats_panel import StatsPanel
            StatsPanel(self.root, self)
        except Exception as e:
            logger.error(f"Failed to open StatsPanel: {e}")

    def _on_open_feedback(self):
        """Open the Session Logs & User Feedback window."""
        try:
            from src.ui.feedback_window import FeedbackWindow
            FeedbackWindow(self.root, self)
        except Exception as e:
            logger.error(f"Failed to open FeedbackWindow: {e}")

    # ------------------------------------------------------------------ #
    #  P2.4 — OCR stats parser for auto player_stats update
    # ------------------------------------------------------------------ #
    _STAT_PATTERNS = {
        "str": re.compile(r"(?:str|strength)[^\d]*(\d+)", re.IGNORECASE),
        "dex": re.compile(r"(?:dex|dexterity)[^\d]*(\d+)", re.IGNORECASE),
        "int": re.compile(r"(?:int|intelligence)[^\d]*(\d+)", re.IGNORECASE),
        "cha": re.compile(r"(?:cha|charisma)[^\d]*(\d+)", re.IGNORECASE),
        "con": re.compile(r"(?:con|constitution)[^\d]*(\d+)", re.IGNORECASE),
        "wis": re.compile(r"(?:wis|wisdom)[^\d]*(\d+)", re.IGNORECASE),
        "exp": re.compile(r"(?:exp|experience)[^\d]*(\d+)", re.IGNORECASE),
    }

    def _ocr_parse_stats(self, ocr_text: str) -> Optional[Dict[str, int]]:
        """
        Parse STR/DEX/INT/CHA/CON/WIS/EXP from OCR text of the stats panel.
        Returns a dict with lowercase keys, or None if fewer than 4 stats found.
        """
        parsed = {}
        for stat, pattern in self._STAT_PATTERNS.items():
            m = pattern.search(ocr_text)
            if m:
                try:
                    parsed[stat] = int(m.group(1))
                except ValueError:
                    pass
        if len(parsed) >= 4:
            return parsed
        return None

    def _on_open_settings(self):
        """Open configuration and tuning dialog."""
        try:
            from src.ui.settings_panel import SettingsPanel
            SettingsPanel(self.root, self)
        except Exception as e:
            logger.error(f"Failed to open SettingsPanel: {e}")

    def _auto_play_loop(self):
        """
        Action-aware autoplay:
          capture → OCR → ButtonScanner → SessionMemory → ActionSelector → execute
        RAG only when selector.needs_rag() (CHOICE screens, not Continue/Combat).
        """
        stuck_iterations = 0
        screen_classifier = ScreenStateMachine()
        scanner = ButtonScanner()
        selector = ActionSelector(scanner=scanner)
        memory = SessionMemory()
        loading_state = LoadingState()
        dead_loop = DeadLoopState(max_repeat=10)
        multi_step = MultiStepPlan()

        while self.state.autoplay_active:
            try:
                # ── 1. Ad-Shield ──────────────────────────────────────────────
                ad_playing = bool(self.capture and getattr(self.capture, "ad_playing", False))
                if ad_playing:
                    logger.warning("🛑 Ad-Shield: pausing 4s")
                    time.sleep(4.0)
                    continue

                # ── 2. Capture + dedup + OCR ──────────────────────────────────
                img = None
                ocr_text = ""
                ocr_boxes: List[dict] = []
                cap_rect: Dict[str, int] = {}
                if self.capture and self.ocr:
                    frame = self.capture.capture_frame()
                    if frame:
                        img = frame.image
                        cap_rect = frame.window_rect or {}
                        cap_origin = frame.capture_origin
                        crop_offset_y = int(img.height * 0.35)
                        dedup_img = img.crop((0, crop_offset_y, img.width, img.height))
                        is_dup, dup_count = self.dedup.is_duplicate(dedup_img)
                        if is_dup and dup_count >= 2:
                            logger.info(
                                f"♻️ Screen unchanged {dup_count} cycles — advance"
                            )
                            action = BotAction(type="advance", reason="dedup_unchanged")
                            self._execute_bot_action(
                                action, ocr_boxes=[], cap_rect=cap_rect, memory=memory
                            )
                            self.dedup.reset()
                            time.sleep(1.0)
                            continue
                        ocr_text, ocr_boxes = self.ocr.extract_text_and_boxes(img)
                        ox, oy = cap_origin
                        rescale = 1.0 / getattr(self.ocr, "resize_factor", 1.0)
                        for box in ocr_boxes:
                            c = box.get("center")
                            if c:
                                box["center"] = (
                                    int(c[0] * rescale) + ox,
                                    int(c[1] * rescale) + oy + crop_offset_y,
                                )
                            bbox = box.get("bbox")
                            if bbox:
                                box["bbox"] = [
                                    [
                                        int(pt[0] * rescale) + ox,
                                        int(pt[1] * rescale) + oy + crop_offset_y,
                                    ]
                                    for pt in bbox
                                ]

                if ocr_text:
                    parsed = self._ocr_parse_stats(ocr_text)
                    if parsed:
                        self.state.player_stats = parsed
                        logger.info(f"📊 Stats from OCR: {parsed}")

                if not ocr_text or not ocr_text.strip():
                    stuck_iterations += 1
                    # #5: Loading screen detection
                    if loading_state.check(ocr_text or ""):
                        logger.info(f"⏳ Loading screen detected (t+{loading_state.consecutive_no_text*1.5:.0f}s) — waiting")
                        loading_state.wait(max_wait=12.0)
                    if stuck_iterations >= 3:
                        self._execute_bot_action(
                            BotAction(type="scroll", reason="empty_ocr"),
                            ocr_boxes=ocr_boxes,
                            cap_rect=cap_rect,
                            memory=memory,
                        )
                        stuck_iterations = 0
                    time.sleep(1.5)
                    continue

                # ── 3. UI-first: buttons + screen state ────────────────────────
                buttons = scanner.scan(ocr_boxes, ocr_text, cap_rect)
                screen_state, st_conf = screen_classifier.classify(
                    ocr_text, ocr_boxes, ad_playing
                )
                logger.debug(
                    f"🖥️ state={screen_state.value} conf={st_conf:.2f} "
                    f"buttons={[b.kind for b in buttons[:6]]} "
                    f"pending_cont={memory.pending_continue}"
                )

                # ── 4. Lazy RAG (only if selector says so) ────────────────────
                ret_res = None
                rec = None
                full_ev = None
                active_lang = self.state.get_language()
                stats = self.state.player_stats
                inv = self.state.player_inventory

                if self.retriever and selector.needs_rag(
                    screen_state, buttons, memory, ad_playing=ad_playing
                ):
                    ret_res = self.retriever.retrieve_for_ocr(
                        ocr_text,
                        language=active_lang,
                        player_stats=stats,
                        player_inventory=inv,
                    )
                    if ret_res.get("matched") and ret_res.get("event"):
                        ekey = ret_res["event"].get("event_key") or ""
                        full_ev = ret_res.get("event_full")
                        if full_ev is None:
                            full_ev = self.retriever.kb.get_event_with_choices(ekey)
                        if full_ev:
                            full_ev["choices"] = ret_res.get("choices") or full_ev.get(
                                "choices", []
                            )
                        score = ret_res.get("confidence", 0.0)
                        logger.info(
                            f"✅ RAG matched: '{ekey}' (Score: {score:.2f}, Lang: {active_lang})"
                        )
                        if self.ai_engine and full_ev:
                            rec = self.ai_engine.recommend_choice(
                                full_ev,
                                player_state={
                                    "stats": stats,
                                    "player_exp": stats.get("exp", 0),
                                    "player_alignment": stats.get("alignment", 0),
                                },
                            )
                        self.root.after(
                            0, lambda ev=full_ev, r=rec or {}: self._update_display(ev, r)
                        )
                        if (
                            rec
                            and rec.get("recommended_choice_idx", -1) >= 0
                            and hasattr(self, "session_logger")
                        ):
                            self.session_logger.log_event(
                                event_key=ekey,
                                ocr_text=ocr_text,
                                choice_recommended=rec.get(
                                    "recommended_choice_text", "Unknown"
                                ),
                                choice_index=rec["recommended_choice_idx"],
                                screenshot_image=img,
                            )
                    else:
                        cands = (ret_res or {}).get("candidates") or []
                        best = cands[0] if cands else {}
                        preview = ocr_text.replace("\n", " ").strip()[:45]
                        logger.info(
                            f"🔎 OCR: '{preview}…' | "
                            f"Top: '{best.get('event_key', 'None')}' "
                            f"(Score: {best.get('confidence', 0):.2f})"
                        )
                        stuck_iterations += 1
                        # Adaptive weak match
                        if (
                            stuck_iterations >= 2
                            and best.get("confidence", 0) >= 0.46
                            and best.get("event_key")
                        ):
                            full_ev = self.retriever.kb.get_event_with_choices(
                                best["event_key"]
                            )
                            if full_ev and self.ai_engine:
                                rec = self.ai_engine.recommend_choice(
                                    full_ev,
                                    player_state={
                                        "stats": stats,
                                        "player_exp": stats.get("exp", 0),
                                        "player_alignment": stats.get("alignment", 0),
                                    },
                                )
                                ret_res = {
                                    "matched": True,
                                    "event": {"event_key": best["event_key"]},
                                    "confidence": best.get("confidence", 0),
                                    "choices": full_ev.get("choices", []),
                                    "event_full": full_ev,
                                }
                                logger.info(
                                    f"⚡ Adaptive fallback: {best['event_key']} "
                                    f"score={best.get('confidence', 0):.2f}"
                                )
                else:
                    stuck_iterations = 0

                # ── 5. Select + execute action ────────────────────────────────
                action = selector.select(
                    screen_state=screen_state,
                    buttons=buttons,
                    memory=memory,
                    rag_result=ret_res,
                    recommendation=rec,
                    ad_playing=ad_playing,
                    stuck_iterations=stuck_iterations,
                )
                logger.info(
                    f"🎯 Action: {action.type} reason={action.reason} "
                    f"text={action.target_text!r} idx={action.choice_idx}"
                )
                did = self._execute_bot_action(
                    action,
                    ocr_boxes=ocr_boxes,
                    cap_rect=cap_rect,
                    memory=memory,
                    full_ev=full_ev,
                    pre_img=img,
                    choices_count=len((full_ev or {}).get("choices") or []),
                )
                # #4: Dead loop detection
                ekey_dead = None
                if full_ev:
                    ekey_dead = full_ev.get("event_key")
                if did and dead_loop.record_and_check(
                    action.type,
                    event_key=ekey_dead,
                    screen_text_snapshot=ocr_text or "",
                ):
                    logger.warning(
                        f"🔄 Dead loop detected ({dead_loop.break_count}x) — "
                        f"breaking: {action.type} on {ekey_dead}"
                    )
                    if dead_loop.break_count >= 3:
                        logger.error("💀 Force-killing autoplay due to 3rd dead loop trigger")
                        self.state.autoplay_active = False
                        self.dedup.reset()
                    else:
                        # Break pattern: force advance + scroll
                        self.clicker.scroll_down_dialog(window_rect=cap_rect)
                        self.clicker.click_advance_dialog(
                            scroll_first=False, ocr_boxes=[], window_rect=cap_rect
                        )
                        self.dedup.reset()
                    continue

                # #3: Multi-step plan detection
                if did and action.type not in ("continue", "advance", "dismiss", "wait", "scroll"):
                    plan_name = MultiStepPlan.match_plan(
                        action.target_text or action.type
                    )
                    if plan_name:
                        ekey_plan = None
                        if full_ev:
                            ekey_plan = full_ev.get("event_key")
                        multi_step.start_plan(plan_name, event_key=ekey_plan or "")
                        logger.info(
                            f"📋 Multi-step plan '{plan_name}' started — "
                            f"next: {multi_step.get_next_action()}"
                        )
                if multi_step.active and did:
                    next_txt = multi_step.get_next_action()
                    if next_txt:
                        logger.info(
                            f"📋 Plan step {multi_step.current_step + 1}/{len(multi_step.steps)}: "
                            f"'{next_txt}'"
                        )
                if did and action.type in (
                    "choice",
                    "continue",
                    "advance",
                    "battle",
                    "dismiss",
                ):
                    stuck_iterations = 0
                    self.dedup.reset()
                    if self.clicker:
                        self.clicker.reset_scroll_guard()
                elif action.type == "wait":
                    time.sleep(1.2)
                else:
                    time.sleep(0.8)

            except (ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"IO/Network error in auto-play: {e}")
                time.sleep(3.0)
            except KeyError as e:
                logger.exception(f"Schema error (missing key {e})")
                time.sleep(1.0)
            except Exception as e:
                logger.exception(f"Unexpected error in auto-play: {e}")
                time.sleep(2.0)

    def _execute_bot_action(
        self,
        action: BotAction,
        *,
        ocr_boxes: List[dict],
        cap_rect: Dict[str, int],
        memory: SessionMemory,
        full_ev: Optional[Dict[str, Any]] = None,
        pre_img=None,
        choices_count: int = 1,
    ) -> bool:
        """Execute a BotAction via AutoClicker; update SessionMemory.

        Handles all action types from ActionSelector:
          continue/advance/dismiss, combat, choice, merchant/recovery/
          explore/social/quest/navigation/action, scroll, wait.
        """
        if not self.clicker:
            memory.record(action.type, reason=action.reason + "|no_clicker")
            return False

        ekey = action.event_key

        if action.type == "wait":
            memory.record("wait", reason=action.reason)
            return False

        if action.type == "scroll":
            ok = bool(self.clicker.scroll_down_dialog(window_rect=cap_rect))
            time.sleep(0.4)
            ok = self.clicker.click_advance_dialog(
                scroll_first=False, ocr_boxes=ocr_boxes, window_rect=cap_rect
            ) or ok
            memory.record("scroll", reason=action.reason)
            return ok

        # ── Nav types: continue, advance, dismiss (click advance dialog) ──────
        if action.type in ("continue", "advance", "dismiss"):
            ok = self.clicker.click_advance_dialog(
                scroll_first=False, ocr_boxes=ocr_boxes, window_rect=cap_rect,
            )
            memory.record(
                "continue" if action.type != "dismiss" else "dismiss",
                event_key=ekey, reason=action.reason,
            )
            memory.clear_pending()
            return ok

        # ── Combat action ────────────────────────────────────────────────
        if action.type in ("combat", "battle"):
            if action.target_text:
                ok = self.clicker.click_choice(
                    0, window_rect=cap_rect, choice_text=action.target_text,
                    ocr_boxes=ocr_boxes, choices_count=1,
                )
            if not ok:
                ok = self.clicker.click_advance_dialog(
                    scroll_first=False, ocr_boxes=ocr_boxes, window_rect=cap_rect,
                )
            memory.record("combat", event_key=ekey, reason=action.reason)
            memory.clear_pending()
            return ok

        # ── Interactive non-RAG action (merchant/recovery/explore/…) ──────
        interactive_kinds = frozenset(
            "merchant|recovery|explore|social|quest|navigation|popup|action".split("|")
        )
        if action.type in interactive_kinds:
            # Click by text match if available, else geometric advance
            if action.target_text or action.target_center:
                ok = self.clicker.click_choice(
                    0 if action.choice_idx is None else action.choice_idx,
                    window_rect=cap_rect,
                    choice_text=action.target_text or "",
                    ocr_boxes=ocr_boxes,
                    choices_count=choices_count or 1,
                )
            if not ok:
                ok = self.clicker.click_advance_dialog(
                    scroll_first=False, ocr_boxes=ocr_boxes, window_rect=cap_rect,
                )
            memory.record(action.type, event_key=ekey, reason=action.reason)
            memory.clear_pending()
            return ok

        # ── RAG choice ────────────────────────────────────────────────
        if action.type == "choice":
            idx = action.choice_idx if action.choice_idx is not None else 0
            txt = action.target_text or ""
            logger.info(f"🎮 Clicking choice #{idx + 1} ('{txt[:30]}')")
            ok = self.clicker.click_choice(
                idx, window_rect=cap_rect, choice_text=txt,
                ocr_boxes=ocr_boxes, choices_count=max(1, choices_count),
            )
            memory.record(
                "choice", event_key=ekey, choice_text=txt, choice_idx=idx,
                reason=action.reason,
            )
            if pre_img is not None:
                self._wait_for_transition(pre_img, cap_rect)
            self._maybe_click_continue_after_choice(cap_rect)
            return ok

        memory.record(action.type, reason=action.reason)
        return False

    def _maybe_click_continue_after_choice(self, cap_rect: dict) -> None:
        """
        After a choice click + transition, many LiA events show a Continue
        button on the result screen. Tap it once if detected so we don't
        re-enter RAG on the same narrative (feedback ID 31).
        """
        if not self.clicker or not self.capture or not self.ocr:
            return
        try:
            frame = self.capture.capture_frame()
            if not frame or not frame.image:
                return
            img = frame.image
            ox, oy = frame.capture_origin
            crop_offset_y = int(img.height * 0.35)
            ocr_text, ocr_boxes = self.ocr.extract_text_and_boxes(img)
            rescale = 1.0 / getattr(self.ocr, "resize_factor", 1.0)
            for box in ocr_boxes:
                c = box.get("center")
                if c:
                    box["center"] = (
                        int(c[0] * rescale) + ox,
                        int(c[1] * rescale) + oy + crop_offset_y,
                    )
            text_l = (ocr_text or "").lower()
            has_continue = "continue" in text_l or "kembali" in text_l
            has_continue_box = any(
                "continue" in (b.get("text") or "").lower()
                or "kembali" in (b.get("text") or "").lower()
                for b in ocr_boxes
            )
            if has_continue or has_continue_box:
                logger.info("➡️ Post-choice Continue detected — tapping advance")
                wr = frame.window_rect or cap_rect
                self.clicker.click_advance_dialog(
                    scroll_first=False, ocr_boxes=ocr_boxes, window_rect=wr
                )
                time.sleep(0.8)
        except Exception as e:
            logger.debug(f"Post-choice continue check failed: {e}")

    def _wait_for_transition(self, pre_click_img, cap_rect: dict) -> None:
        """
        Wait for the game screen to stabilise after a click.
        Polls OCR at intervals; returns once the screen is different from
        pre_click_img AND OCR text is non-trivial (not garbage/transitional).
        Gutters: max 6 seconds.
        """
        max_wait = 6.0
        interval = 0.8
        waited = 0.0
        garbage_pattern = re.compile(r'^[\s\uAC00-\uD7A3\u3040-\u309F\u30A0-\u30FF]{0,5}$')
        # Seed dedup with pre-click image so subsequent frames are compared to it
        check_dedup = ScreenDeduplicator()
        check_dedup.is_duplicate(pre_click_img)  # seed baseline
        
        logger.info("⏳ Waiting for screen transition after click...")
        while waited < max_wait:
            time.sleep(interval)
            waited += interval
            if not self.capture:
                continue
            frame = self.capture.capture_frame()
            if not frame or not frame.image:
                continue
            
            cur_img = frame.image
            # Check if screen actually changed from pre-click image
            is_dup, _ = check_dedup.is_duplicate(cur_img)
            if is_dup:
                logger.debug(f"  Still same screen (t+{waited:.1f}s)...")
                continue
            
            # Screen changed — now check OCR quality
            if self.ocr:
                new_text = self.ocr.extract_text(cur_img)
                if not new_text or not new_text.strip():
                    continue
                # Reject garbage: single symbol or very short non-English text
                if garbage_pattern.match(new_text.strip()):
                    logger.debug(f"  Transition garbage: '{new_text[:40]}'")
                    continue
                if len(new_text.strip()) < 15:
                    logger.debug(f"  Text too short ({len(new_text.strip())} chars), still loading...")
                    continue
                
                logger.info(f"✅ Screen stabilised after {waited:.1f}s — OCR: {new_text[:80]}...")
                return
        
        logger.warning(f"⚠️ Transition wait timed out after {max_wait}s — continuing anyway.")

    def _run_scan_thread(self):
        """Worker thread for screen capture and analysis."""
        try:
            ocr_text = ""
            img = None
            if self.capture and self.ocr:
                frame = self.capture.capture_frame()
                if frame:
                    img = frame.image
                    ocr_text = self.ocr.extract_text(img)

            if not ocr_text or not ocr_text.strip():
                logger.info("Scan completed: No readable text detected on screen.")
                # Lambda fix: capture by value via default args
                self.root.after(0, lambda t=ocr_text: self._update_no_match(t))
                return

            # Read from thread-safe state snapshot (NOT Tk StringVar from background thread).
            if not self.retriever:
                logger.warning("Scan: RAG retriever not available. Skipping query.")
                self.root.after(0, lambda: self._update_no_match(""))
                return

            active_lang = self.state.get_language()
            stats = self.state.player_stats
            inv = self.state.player_inventory
            ret_res = self.retriever.retrieve_for_ocr(
                ocr_text,
                language=active_lang,
                player_stats=stats,
                player_inventory=inv,
            )
            if ret_res.get("matched") and ret_res.get("event"):
                event_data = ret_res["event"]
                full_ev = ret_res.get("event_full")  # already includes choices — no double-fetch
                if full_ev is None:
                    full_ev = self.retriever.kb.get_event_with_choices(event_data["event_key"])
                if full_ev:
                    full_ev["choices"] = ret_res["choices"]

                rec = {}
                if self.ai_engine and full_ev:
                    rec = self.ai_engine.recommend_choice(full_ev, player_state={"stats": stats, "player_exp": stats.get("exp", 0), "player_alignment": stats.get("alignment", 0)})

                # Lambda fix: capture by value via default args
                self.root.after(0, lambda ev=full_ev, r=rec: self._update_display(ev, r))

                if rec and rec.get("recommended_choice_idx", -1) >= 0:
                    if hasattr(self, "session_logger"):
                        self.session_logger.log_event(
                            event_key=event_data["event_key"],
                            ocr_text=ocr_text,
                            choice_recommended=rec.get("recommended_choice_text", "Unknown"),
                            choice_index=rec["recommended_choice_idx"],
                            screenshot_image=img,
                        )
            else:
                self.root.after(0, lambda t=ocr_text: self._update_no_match(t))
        except Exception as e:
            logger.exception(f"Scan thread failed: {e}")
            self.root.after(0, lambda msg=str(e): self.show_error(msg))

    def _update_display(self, event_data: Dict[str, Any], recommendation: Dict[str, Any]):
        """Update UI elements on main thread with new event and choices."""
        self.status_label.configure(text="Event Found", text_color="#3fb950")
        self.event_title_var.set(f"📜 {event_data.get('event_key', 'Unknown Event')}\n{event_data.get('clean_text', '')[:140]}...")
        self.reasoning_var.set(recommendation.get("reasoning", "No AI recommendation available."))

        # Clear old choices
        for child in self.choices_container.winfo_children():
            child.destroy()

        # Render new choices
        choices = event_data.get("choices", [])
        evals = recommendation.get("choice_evaluations", [])
        
        for idx, ch in enumerate(choices):
            is_rec = evals[idx].get("recommended", False) if idx < len(evals) else False
            card_color = "#1f6feb" if is_rec else "#21262d"
            
            card = ctk.CTkFrame(self.choices_container, fg_color=card_color, corner_radius=6)
            card.pack(fill="x", pady=3)
            
            prefix = "⭐ [BEST] " if is_rec else f"[{idx+1}] "
            ch_text = prefix + ch.get("text", "")
            if ch.get("required"):
                ch_text += f"  |  Check: {ch.get('required')}"

            lbl = ctk.CTkLabel(
                card,
                text=ch_text,
                font=ctk.CTkFont(size=12, weight="bold" if is_rec else "normal"),
                text_color="white",
                wraplength=340,
                justify="left"
            )
            lbl.pack(anchor="w", padx=8, pady=6)

    def _update_no_match(self, ocr_text: str):
        """Handle unmatched OCR screen text."""
        self.status_label.configure(text="No Match", text_color="#f85149")
        self.event_title_var.set("No matching event found.")
        self.reasoning_var.set(f"Scanned text (`{ocr_text[:60]}`) did not match any offline KB events with high confidence.")

    def _on_search_prompt(self):
        """Prompt user for manual RAG search query."""
        dialog = ctk.CTkInputDialog(text="Enter event keyword or item name:", title="Manual RAG Search")
        query = dialog.get_input()
        if query and self.retriever:
            ret_res = self.retriever.retrieve_for_ocr(query)
            if ret_res.get("matched") and ret_res.get("event"):
                full_ev = ret_res.get("event_full")  # already includes choices — no double-fetch
                if full_ev is None:
                    full_ev = self.retriever.kb.get_event_with_choices(ret_res["event"]["event_key"])
                rec = self.ai_engine.recommend_choice(full_ev) if self.ai_engine else {}
                self._update_display(full_ev, rec)
            else:
                self._update_no_match(query)

    def run(self):
        """Start CustomTkinter event loop."""
        logger.info("Starting OverlayWindow CustomTkinter mainloop...")
        self.root.mainloop()
