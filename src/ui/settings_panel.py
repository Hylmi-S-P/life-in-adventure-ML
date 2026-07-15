"""
settings_panel.py - Settings Panel dialog for adjusting OCR thresholds, Auto-Play delay, and overlay opacity.
"""

from typing import Any, Optional
import loguru

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False
    import tkinter as ctk

logger = loguru.logger


class SettingsPanel:
    """Interactive settings dialog window for customizing Life in Adventure Assistant."""

    def __init__(self, parent: Any, overlay: Any, config: Optional[Any] = None):
        if _CTK_AVAILABLE:
            self.top = ctk.CTkToplevel(parent)
        else:
            self.top = ctk.Toplevel(parent)

        self.overlay = overlay
        self.top.title("⚙️ Assistant Settings")
        self.top.geometry("380x360")
        self.top.transient(parent)
        self.top.grab_set()

        lbl = ctk.CTkLabel(self.top, text="⚙️ Configuration & Tuning Panel", font=("Arial", 16, "bold"))
        lbl.pack(pady=10)

        # 1. Overlay Opacity Slider
        opacity_frame = ctk.CTkFrame(self.top, corner_radius=6)
        opacity_frame.pack(fill="x", padx=15, pady=6)
        
        current_alpha = int(getattr(self.overlay, "window_alpha", 0.93) * 100)
        self.alpha_lbl = ctk.CTkLabel(opacity_frame, text=f"Overlay Opacity: {current_alpha}%")
        self.alpha_lbl.pack(anchor="w", padx=10, pady=(6, 2))
        
        self.alpha_slider = ctk.CTkSlider(
            opacity_frame, from_=50, to=100, number_of_steps=50,
            command=self._on_alpha_change
        )
        self.alpha_slider.set(current_alpha)
        self.alpha_slider.pack(fill="x", padx=10, pady=(0, 8))

        # 2. Auto-Play Action Delay
        delay_frame = ctk.CTkFrame(self.top, corner_radius=6)
        delay_frame.pack(fill="x", padx=15, pady=6)
        
        current_delay = getattr(self.overlay, "autoplay_delay", 2.0)
        self.delay_lbl = ctk.CTkLabel(delay_frame, text=f"Auto-Play Click Delay: {current_delay:.1f}s")
        self.delay_lbl.pack(anchor="w", padx=10, pady=(6, 2))
        
        self.delay_slider = ctk.CTkSlider(
            delay_frame, from_=0.5, to=5.0, number_of_steps=45,
            command=self._on_delay_change
        )
        self.delay_slider.set(current_delay)
        self.delay_slider.pack(fill="x", padx=10, pady=(0, 8))

        # 3. System Status info
        info = ctk.CTkLabel(
            self.top,
            text="• RAG Engine: SQLite + ChromaDB Hybrid\n• RL Pathfinder: PPO Curiosity (Active)\n• Ad-Shield: Auto-Detect & Pause Enabled",
            justify="left",
            text_color="#8b949e"
        )
        info.pack(pady=10)

        btn = ctk.CTkButton(self.top, text="Save & Close", command=self.top.destroy, fg_color="#238636", hover_color="#196c2e")
        btn.pack(pady=10)

    def _on_alpha_change(self, val: float):
        alpha = int(val) / 100.0
        self.alpha_lbl.configure(text=f"Overlay Opacity: {int(val)}%")
        self.overlay.window_alpha = alpha
        try:
            self.overlay.root.wm_attributes("-alpha", alpha)
        except Exception:
            pass

    def _on_delay_change(self, val: float):
        delay = round(val, 1)
        self.delay_lbl.configure(text=f"Auto-Play Click Delay: {delay}s")
        self.overlay.autoplay_delay = delay
