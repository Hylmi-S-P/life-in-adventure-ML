"""
stats_panel.py - Player Character Stats Sheet for customizing AI choice reasoning.
Enables setting STR, DEX, INT, CHA, CON, WIS, Alignment, and EXP to trigger exact D20 checks.
"""

from typing import Any, Dict
import loguru

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False
    import tkinter as ctk

logger = loguru.logger


class StatsPanel:
    """Character Profile window where players adjust live stats for exact D20 check calculations."""

    def __init__(self, parent: Any, overlay: Any):
        if _CTK_AVAILABLE:
            self.top = ctk.CTkToplevel(parent)
        else:
            self.top = ctk.Toplevel(parent)

        self.overlay = overlay
        self.top.title("👤 Player Character Sheet")
        self.top.geometry("400x480")
        self.top.transient(parent)
        self.top.grab_set()

        lbl = ctk.CTkLabel(self.top, text="👤 Live Character Profile & D20 Stats", font=("Arial", 16, "bold"))
        lbl.pack(pady=10)

        desc = ctk.CTkLabel(
            self.top,
            text="AI will prioritize choices matching your stat thresholds (10/13/20)\nand avoid early ending triggers if EXP bar is high.",
            text_color="#8b949e",
            font=("Arial", 11)
        )
        desc.pack(pady=(0, 10))

        # Scrollable container for stats
        self.scroll = ctk.CTkScrollableFrame(self.top, corner_radius=6, height=300)
        self.scroll.pack(fill="both", expand=True, padx=15, pady=4)

        self.stat_vars: Dict[str, ctk.StringVar] = {}
        
        # Load current stats from overlay if present (lowercase keys, consistent with entire codebase)
        current_stats = getattr(self.overlay, "player_stats", {
            "str": 13, "dex": 13, "int": 13, "cha": 13, "con": 13, "wis": 13,
            "alignment": 0, "exp": 15
        })

        # Core 6 Stats — display names show uppercase to user, internal keys are lowercase
        stats_list = [("str", "STR — Strength (Combat/Heavy)"), ("dex", "DEX — Dexterity (Agility/Stealth)"),
                      ("int", "INT — Intelligence (Magic/Lore)"), ("cha", "CHA — Charisma (Speech/Trade)"),
                      ("con", "CON — Constitution (Vitality/Endure)"), ("wis", "WIS — Wisdom (Perception/Focus)")]

        for stat_key, label_name in stats_list:
            row = ctk.CTkFrame(self.scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            
            ctk.CTkLabel(row, text=label_name, width=240, anchor="w").pack(side="left", padx=6)
            
            var = ctk.StringVar(value=str(current_stats.get(stat_key, 13)))
            self.stat_vars[stat_key] = var
            
            entry = ctk.CTkEntry(row, textvariable=var, width=70)
            entry.pack(side="right", padx=6)

        # Alignment
        row_align = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row_align.pack(fill="x", pady=6)
        ctk.CTkLabel(row_align, text="Alignment (-100 to +100):", width=240, anchor="w").pack(side="left", padx=6)
        var_align = ctk.StringVar(value=str(current_stats.get("alignment", 0)))
        self.stat_vars["alignment"] = var_align
        ctk.CTkEntry(row_align, textvariable=var_align, width=70).pack(side="right", padx=6)

        # EXP Bar
        row_exp = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row_exp.pack(fill="x", pady=6)
        ctk.CTkLabel(row_exp, text="Current EXP (0 - 100):", width=240, anchor="w").pack(side="left", padx=6)
        var_exp = ctk.StringVar(value=str(current_stats.get("exp", 15)))
        self.stat_vars["exp"] = var_exp
        ctk.CTkEntry(row_exp, textvariable=var_exp, width=70).pack(side="right", padx=6)

        # Inventory
        row_inv = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row_inv.pack(fill="x", pady=6)
        ctk.CTkLabel(row_inv, text="Inventory (comma-separated):", width=160, anchor="w").pack(side="left", padx=6)
        current_inv = getattr(self.overlay, "player_inventory", ["Shovel", "Lantern"])
        self.inv_var = ctk.StringVar(value=", ".join(current_inv))
        ctk.CTkEntry(row_inv, textvariable=self.inv_var, width=170).pack(side="right", padx=6)

        # Buttons
        btn_frame = ctk.CTkFrame(self.top, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=12)

        btn_save = ctk.CTkButton(
            btn_frame, text="💾 Save Character Profile", command=self._on_save,
            fg_color="#238636", hover_color="#196c2e"
        )
        btn_save.pack(side="left", fill="x", expand=True, padx=(0, 5))

        btn_cancel = ctk.CTkButton(
            btn_frame, text="Cancel", command=self.top.destroy, width=80,
            fg_color="#6e7681", hover_color="#57606a"
        )
        btn_cancel.pack(side="right")

    def _on_save(self):
        new_stats = {}
        for k, var in self.stat_vars.items():
            try:
                val = int(var.get().strip())
                new_stats[k] = val
            except ValueError:
                new_stats[k] = 13
                
        self.overlay.player_stats = new_stats
        
        # Save inventory
        if hasattr(self, "inv_var"):
            inv_str = self.inv_var.get()
            inv_items = [i.strip() for i in inv_str.split(",") if i.strip()]
            self.overlay.player_inventory = inv_items
            logger.info(f"Updated Live Player Inventory -> {inv_items}")

        logger.info(f"Updated Live Player Stats -> {new_stats}")
        if hasattr(self.overlay, "status_label"):
            self.overlay.status_label.configure(text="Stats Updated", text_color="#3fb950")
        self.top.destroy()
