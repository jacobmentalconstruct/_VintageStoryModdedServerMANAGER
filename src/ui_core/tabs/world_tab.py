# src/ui_core/tabs/world_tab.py
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import replace

from .base_tab import BaseTab

class WorldTab(BaseTab):
    TAB_ID = "world"
    TAB_TITLE = "World Gen"
    ORDER = 15  # Place between Server (10) and Backups (20)

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)

        # --- Standard Config ---
        self.var_world_name = tk.StringVar(value="NewWorld")
        self.var_seed = tk.StringVar()
        self.var_width = tk.IntVar(value=1024000)
        self.var_height = tk.IntVar(value=256)
        
        # --- Granular "Crazy" Config (Sliders) ---
        # These map to specific WorldConfig keys if supported by the engine/mods
        self.var_sealevel = tk.DoubleVar(value=0.43)  # Standard VS default
        self.var_upheaval = tk.DoubleVar(value=0.0)   # Distortion/Mountains
        
        # --- Advanced / Modded ---
        # A raw JSON text area for specific mod keys (e.g. "rivers": true)
        self.txt_extra_json = None

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Layout: 2 Columns
        # Col 0: Standard Settings & Dimensions
        # Col 1: Advanced Generation & Mod Configs
        self.frame.columnconfigure(0, weight=1)
        self.frame.columnconfigure(1, weight=1)

        # ============================================
        # COLUMN 0: Identity & Physics
        # ============================================
        
        # --- Panel: Identification ---
        ident = ttk.LabelFrame(self.frame, text="Identity")
        ident.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        ident.columnconfigure(1, weight=1)

        ttk.Label(ident, text="World Name:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(ident, textvariable=self.var_world_name).grid(row=0, column=1, sticky="ew", padx=10, pady=6)

        ttk.Label(ident, text="Seed (Empty = Random):").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(ident, textvariable=self.var_seed).grid(row=1, column=1, sticky="ew", padx=10, pady=6)

        # --- Panel: Dimensions (Granular Control) ---
        dims = ttk.LabelFrame(self.frame, text="Dimensions & Boundaries")
        dims.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        dims.columnconfigure(1, weight=1)

        # Width
        ttk.Label(dims, text="World Width (X/Z):").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        # Spinbox for granular steps, but allow typing
        wb = ttk.Spinbox(dims, from_=512, to=30000000, increment=512, textvariable=self.var_width)
        wb.grid(row=0, column=1, sticky="ew", padx=10, pady=6)
        
        # Height
        ttk.Label(dims, text="World Height (Y):").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        hb = ttk.Spinbox(dims, from_=256, to=1024, increment=16, textvariable=self.var_height)
        hb.grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        
        ttk.Label(dims, text="⚠️ Changing Height requires a fresh world!", foreground="#D96D2B").grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=2)


        # ============================================
        # COLUMN 1: Generation & Mods
        # ============================================

        # --- Panel: Terrain Features ---
        terrain = ttk.LabelFrame(self.frame, text="Terrain & Climate")
        terrain.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        terrain.columnconfigure(1, weight=1)

        # Sea Level Slider
        ttk.Label(terrain, text="Sea Level Ratio:").grid(row=0, column=0, sticky="w", padx=10, pady=(6,0))
        sl = ttk.Scale(terrain, from_=0.1, to=1.0, variable=self.var_sealevel, orient="horizontal")
        sl.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        # Value readout
        ttk.Label(terrain, textvariable=self.var_sealevel).grid(row=0, column=1, sticky="e", padx=10)

        # Upheaval / Geologic Activity (Conceptual mapping to world gen noise)
        ttk.Label(terrain, text="Geologic Upheaval (Noise):").grid(row=2, column=0, sticky="w", padx=10, pady=(6,0))
        up = ttk.Scale(terrain, from_=0.0, to=5.0, variable=self.var_upheaval, orient="horizontal")
        up.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        ttk.Label(terrain, textvariable=self.var_upheaval).grid(row=2, column=1, sticky="e", padx=10)

        # --- Panel: JSON Overrides (For Mods) ---
        mods = ttk.LabelFrame(self.frame, text="Advanced / Mod Config (JSON)")
        mods.grid(row=1, column=1, sticky="nsew", padx=12, pady=(0, 12))
        mods.columnconfigure(0, weight=1)
        mods.rowconfigure(0, weight=1)

        self.txt_extra_json = tk.Text(mods, height=8, width=30, wrap="word")
        self.txt_extra_json.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Scrollbar for JSON area
        sb = ttk.Scrollbar(mods, orient="vertical", command=self.txt_extra_json.yview)
        self.txt_extra_json.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns", pady=10)
        
        ttk.Label(mods, text="Paste mod specific world-gen keys here.").grid(row=1, column=0, sticky="w", padx=10, pady=(0,6))

        # --- Footer Actions ---
        actions = ttk.Frame(self.frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=12)
        
        ttk.Button(actions, text="Save World Config", command=self._save_config).pack(side="right")
        ttk.Button(actions, text="Revert Changes", command=self._load_from_state).pack(side="right", padx=(0, 10))

        # Initial Load
        self._load_from_state()

        return self.frame

    # -------------------------
    # Logic
    # -------------------------

    def _load_from_state(self):
        state = self.controller.get_state()
        settings = state.world_settings

        self.var_world_name.set(settings.get("WorldName", "NewWorld"))
        self.var_seed.set(settings.get("Seed", ""))
        self.var_width.set(int(settings.get("WorldWidth", 1024000)))
        self.var_height.set(int(settings.get("WorldHeight", 256)))
        
        # Load advanced JSON if exists
        extra = settings.get("ExtraConfig", {})
        self.txt_extra_json.delete("1.0", "end")
        self.txt_extra_json.insert("1.0", json.dumps(extra, indent=2))

    def _save_config(self):
        # 1. Gather basic fields
        new_settings = {
            "WorldName": self.var_world_name.get().strip(),
            "Seed": self.var_seed.get().strip(),
            "WorldWidth": self.var_width.get(),
            "WorldHeight": self.var_height.get(),
            # These are virtual fields we might map to specific JSON keys later
            "SeaLevel": self.var_sealevel.get(),
            "Upheaval": self.var_upheaval.get() 
        }

        # 2. Parse Extra JSON
        raw_json = self.txt_extra_json.get("1.0", "end").strip()
        if raw_json:
            try:
                extra = json.loads(raw_json)
                new_settings["ExtraConfig"] = extra
            except json.JSONDecodeError as e:
                messagebox.showerror("Invalid JSON", f"Mod Config JSON is invalid:\n{e}")
                return

        # 3. Send to Controller
        try:
            # Note: You need to implement update_world_settings in AppController (Phase 2)
            if hasattr(self.controller, "update_world_settings"):
                self.controller.update_world_settings(new_settings)
                messagebox.showinfo("Saved", "World settings saved to internal state.\n(Server restart required to apply to new worlds)")
            else:
                self.log("[ERROR] Controller missing update_world_settings method.")
        except Exception as e:
            self.log(f"[ERROR] Failed to save world settings: {e}")
            messagebox.showerror("Error", str(e))
