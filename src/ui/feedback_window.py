"""
feedback_window.py - User Evaluation and Session History Window.
Renders recent RAG matches and allows evaluating AI recommendations (Success/Failure)
with optional failure comments and screenshot thumbnail previews.
"""

import os
from typing import Any, Dict, List
import loguru
from PIL import Image

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False
    import tkinter as ctk

logger = loguru.logger


class FeedbackWindow:
    """Evaluation sheet popup where users review decisions and record success/failure logs."""

    def __init__(self, parent: Any, overlay: Any):
        if _CTK_AVAILABLE:
            self.top = ctk.CTkToplevel(parent)
        else:
            self.top = ctk.Toplevel(parent)

        self.overlay = overlay
        self.logger = getattr(overlay, "session_logger", None)
        
        self.top.title("📝 Riwayat Sesi & Feedback AI")
        self.top.geometry("720x640")
        self.top.transient(parent)
        self.top.grab_set()

        # Title Header
        lbl = ctk.CTkLabel(self.top, text="📝 Live Session Logs & AI Evaluations", font=("Arial", 16, "bold"))
        lbl.pack(pady=10)

        desc = ctk.CTkLabel(
            self.top,
            text="Review each event encountered during this session.\nMark choices as Success or Failure to help retrain and improve AI policy accuracy.",
            text_color="#8b949e",
            font=("Arial", 11)
        )
        desc.pack(pady=(0, 10))

        # Main scrollable list of logs
        self.scroll = ctk.CTkScrollableFrame(self.top, corner_radius=6)
        self.scroll.pack(fill="both", expand=True, padx=15, pady=4)

        # Bottom metrics panel
        self.metrics_frame = ctk.CTkFrame(self.top, fg_color="transparent")
        self.metrics_frame.pack(fill="x", padx=15, pady=6)
        
        self.metrics_label = ctk.CTkLabel(
            self.metrics_frame, 
            text="Evaluation Progress: 0/0 reviewed", 
            font=("Arial", 11, "italic"),
            text_color="#8b949e"
        )
        self.metrics_label.pack(side="left")

        btn_close = ctk.CTkButton(
            self.top, text="Close Window", command=self.top.destroy, width=120,
            fg_color="#30363d", hover_color="#21262d"
        )
        btn_close.pack(pady=12)

        self.cards: List[ctk.CTkFrame] = []
        self._populate_logs()

    def _populate_logs(self):
        """Populate the scrollable frame with recent logs from the session buffer."""
        # Clear frame
        for widget in self.scroll.winfo_children():
            widget.destroy()

        if not self.logger or not self.logger.get_pending_logs():
            empty_lbl = ctk.CTkLabel(
                self.scroll, 
                text="No new decision events to evaluate.\n\nRun the Auto-Play bot to capture session events!",
                font=("Arial", 13),
                text_color="#8b949e",
                pady=40
            )
            empty_lbl.pack(fill="both", expand=True)
            self.metrics_label.configure(text="No active session logs.")
            return

        pending_logs = self.logger.get_pending_logs()
        self.total_logs = len(pending_logs)
        self.reviewed_count = 0
        self._update_metrics()

        for idx, log in enumerate(pending_logs):
            card = ctk.CTkFrame(self.scroll, corner_radius=6, border_width=1, border_color="#30363d")
            card.pack(fill="x", pady=6, padx=4)
            self.cards.append(card)

            # Horizontal split: Info left, Image middle, Actions right
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=8, pady=8)

            # 1. Info details
            time_str = log.get("timestamp", "").split("_")[1]
            time_formatted = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}" if len(time_str) >= 6 else time_str
            
            title_lbl = ctk.CTkLabel(
                info_frame, 
                text=f"⏱️ {time_formatted} | Key: {log.get('event_key')}", 
                font=("Arial", 12, "bold"),
                anchor="w"
            )
            title_lbl.pack(fill="x", anchor="w")

            ocr_txt = log.get("ocr_text", "")
            ocr_snippet = ocr_txt.replace('\n', ' ').strip()
            if len(ocr_snippet) > 85:
                ocr_snippet = ocr_snippet[:82] + "..."
            
            ocr_lbl = ctk.CTkLabel(
                info_frame, 
                text=f"OCR: \"{ocr_snippet}\"", 
                font=("Arial", 11, "italic"),
                text_color="#8b949e",
                anchor="w",
                justify="left",
                wraplength=340
            )
            ocr_lbl.pack(fill="x", pady=2, anchor="w")

            rec_choice = log.get("choice_recommended", "Unknown")
            choice_lbl = ctk.CTkLabel(
                info_frame, 
                text=f"💡 Rec: Choice #{log.get('choice_index') + 1} ('{rec_choice}')", 
                font=("Arial", 11, "bold"),
                text_color="#58a6ff",
                anchor="w"
            )
            choice_lbl.pack(fill="x", pady=2, anchor="w")

            # 2. Image preview (Middle)
            img_path = log.get("screenshot_path", "")
            if img_path and os.path.exists(img_path):
                try:
                    img = Image.open(img_path)
                    img.thumbnail((90, 90))
                    
                    # Create custom Tkinter Image
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    
                    # Wrap in clickable button to view full resolution
                    btn_img = ctk.CTkButton(
                        card, 
                        image=ctk_img, 
                        text="", 
                        width=img.size[0] + 6,
                        height=img.size[1] + 6,
                        fg_color="transparent",
                        hover_color="#21262d",
                        command=lambda p=img_path: self._open_full_screenshot(p)
                    )
                    btn_img.image = ctk_img  # Reference
                    btn_img.pack(side="left", padx=10, pady=8)
                    
                    # Tooltip/hint on hover
                    btn_img.bind("<Enter>", lambda e, b=btn_img: b.configure(border_width=1, border_color="#58a6ff"))
                    btn_img.bind("<Leave>", lambda e, b=btn_img: b.configure(border_width=0))
                except Exception as e:
                    logger.debug(f"Failed loading screenshot thumbnail: {e}")

            # 3. Actions Panel (Right)
            actions_frame = ctk.CTkFrame(card, fg_color="transparent", width=160)
            actions_frame.pack(side="right", padx=8, pady=8)
            actions_frame.pack_propagate(False)

            # Sub-frame for buttons
            btn_row = ctk.CTkFrame(actions_frame, fg_color="transparent")
            btn_row.pack(fill="x", pady=2)

            btn_ok = ctk.CTkButton(
                btn_row, text="✅ Sukses", width=70, height=26,
                fg_color="#238636", hover_color="#1e712e",
                command=lambda l_id=log.get("id"), c=card, af=actions_frame: self._submit_success(l_id, c, af)
            )
            btn_ok.pack(side="left", padx=2)

            btn_fail = ctk.CTkButton(
                btn_row, text="❌ Gagal", width=70, height=26,
                fg_color="#da3637", hover_color="#b62a2b",
                command=lambda l_id=log.get("id"), c=card, af=actions_frame: self._show_failure_comment_field(l_id, c, af)
            )
            btn_fail.pack(side="right", padx=2)

    def _open_full_screenshot(self, filepath: str):
        """Open full-sized screenshot using operating system viewer."""
        try:
            logger.info(f"Opening full screenshot: {filepath}")
            os.startfile(filepath)
        except Exception as e:
            logger.warning(f"Could not open image file: {e}")

    def _submit_success(self, log_id: int, card_frame: ctk.CTkFrame, actions_frame: ctk.CTkFrame):
        """Record success evaluation to SQLite."""
        if self.logger:
            self.logger.update_feedback(log_id, "success")
        
        # UI Feedback styling updates
        card_frame.configure(border_color="#238636")
        
        # Replace buttons with success text label
        for w in actions_frame.winfo_children():
            w.destroy()
        
        success_lbl = ctk.CTkLabel(actions_frame, text="✅ Sukses Dievaluasi", text_color="#3fb950", font=("Arial", 11, "bold"))
        success_lbl.pack(pady=10)
        
        self.reviewed_count += 1
        self._update_metrics()

    def _show_failure_comment_field(self, log_id: int, card_frame: ctk.CTkFrame, actions_frame: ctk.CTkFrame):
        """Expand card layout to offer failure reason text box."""
        # Clear buttons
        for w in actions_frame.winfo_children():
            w.destroy()
            
        card_frame.configure(border_color="#da3637")

        comment_var = ctk.StringVar()
        comment_entry = ctk.CTkEntry(
            actions_frame, 
            placeholder_text="Alasan gagal (opsional)...", 
            textvariable=comment_var,
            width=150, 
            height=24,
            font=("Arial", 10)
        )
        comment_entry.pack(pady=2)

        btn_submit = ctk.CTkButton(
            actions_frame, text="Kirim Alasan", width=120, height=22,
            fg_color="#bc8c05", hover_color="#9e7504",
            command=lambda l_id=log_id, c=card_frame, af=actions_frame, cv=comment_var: self._submit_failure(l_id, c, af, cv.get())
        )
        btn_submit.pack(pady=2)
        comment_entry.focus()

    def _submit_failure(self, log_id: int, card_frame: ctk.CTkFrame, actions_frame: ctk.CTkFrame, comment: str):
        """Record failure status and optional reason to SQLite."""
        clean_comment = comment.strip()
        if self.logger:
            self.logger.update_feedback(log_id, "failure", clean_comment)

        for w in actions_frame.winfo_children():
            w.destroy()

        status_text = "❌ Gagal"
        if clean_comment:
            status_text += f"\n({clean_comment[:20]}...)"
            
        fail_lbl = ctk.CTkLabel(
            actions_frame, 
            text=status_text, 
            text_color="#f85149", 
            font=("Arial", 11, "bold"),
            justify="center"
        )
        fail_lbl.pack(pady=6)

        self.reviewed_count += 1
        self._update_metrics()

    def _update_metrics(self):
        """Update bottom stats bar."""
        self.metrics_label.configure(
            text=f"Evaluation Progress: {self.reviewed_count}/{self.total_logs} reviewed in this session"
        )
