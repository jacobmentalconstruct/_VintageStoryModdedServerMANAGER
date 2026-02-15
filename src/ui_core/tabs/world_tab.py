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
    ORDER = 15

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)

        # --- Identity ---
        self.var_world_name = tk.StringVar(value="NewWorld")
        self.var_seed = tk.StringVar()

        # --- Tab 1: Genesis (Map) ---
        self.var_width = tk.IntVar(value=1024000)
        self.var_height = tk.IntVar(value=256)
        self.var_sealevel = tk.DoubleVar(value=0.43)
        self.var_landcover = tk.DoubleVar(value=1.0) # 1.0 = 100%
        self.var_upheaval = tk.DoubleVar(value=0.0)
        self.var_geo_activity = tk.StringVar(value="weak")
        self.var_climate = tk.StringVar(value="realistic")
        self.var_global_ores = tk.DoubleVar(value=1.0)
        self.var_copper = tk.StringVar(value="common")
        self.var_tin = tk.StringVar(value="rare")

        # --- Tab 2: Survival (Rules) ---
        self.var_gamemode = tk.StringVar(value="survival")
        self.var_grace_timer = tk.IntVar(value=0)
        self.var_death_punish = tk.StringVar(value="dropall")
        self.var_hunger = tk.DoubleVar(value=1.0)
        self.var_hostility = tk.StringVar(value="aggressive")
        self.var_gravity = tk.StringVar(value="sandgravel") # sandgravel or none
        self.var_microblock = tk.IntVar(value=2) # 0, 1, 2
        self.var_class_exclusive = tk.BooleanVar(value=True)
        self.var_tool_durability = tk.DoubleVar(value=1.0)

        # --- Tab 3: Temporal (Clockwork) ---
        self.var_stability = tk.BooleanVar(value=True)
        self.var_storms = tk.StringVar(value="sometimes")
        self.var_rifts = tk.StringVar(value="visible")
        self.var_sleep_storms = tk.BooleanVar(value=False)

        # --- Tab 4: Advanced ---
        self.txt_extra_json = None

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Layout: Top (Identity) + Center (Notebook) + Bottom (Actions)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        # 1. Identity Header
        top = ttk.LabelFrame(self.frame, text="World Identity")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        ttk.Label(top, text="World Name:").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        ttk.Entry(top, textvariable=self.var_world_name).grid(row=0, column=1, sticky="ew", padx=10)

        ttk.Label(top, text="Seed:").grid(row=0, column=2, sticky="w", padx=10)
        ttk.Entry(top, textvariable=self.var_seed).grid(row=0, column=3, sticky="ew", padx=10)

        # 2. The Engine (Notebook)
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)

        # --- Sub-Tab: GENESIS ---
        tab_gen = ttk.Frame(self.notebook)
        self.notebook.add(tab_gen, text="Genesis")
        self._build_genesis_tab(tab_gen)

        # --- Sub-Tab: SURVIVAL ---
        tab_surv = ttk.Frame(self.notebook)
        self.notebook.add(tab_surv, text="Survival")
        self._build_survival_tab(tab_surv)

        # --- Sub-Tab: TEMPORAL ---
        tab_time = ttk.Frame(self.notebook)
        self.notebook.add(tab_time, text="Temporal")
        self._build_temporal_tab(tab_time)

        # --- Sub-Tab: ADVANCED ---
        tab_adv = ttk.Frame(self.notebook)
        self.notebook.add(tab_adv, text="Advanced (JSON)")
        self._build_advanced_tab(tab_adv)

        # 3. Actions Footer
        bot = ttk.Frame(self.frame)
        bot.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        
        ttk.Button(bot, text="Save Configuration", command=self._save_config).pack(side="right")
        ttk.Button(bot, text="Revert to Saved", command=self._load_from_state).pack(side="right", padx=10)

        self._load_from_state()
        return self.frame

    # =========================================================
    # BUILDERS
    # =========================================================

    def _build_genesis_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        # Dimensions
        g_dim = ttk.LabelFrame(parent, text="Dimensions")
        g_dim.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(g_dim, text="Width (X/Z):").grid(row=0, column=0, padx=10, pady=5)
        ttk.Spinbox(g_dim, from_=512, to=30000000, increment=512, textvariable=self.var_width).grid(row=0, column=1, sticky="ew")
        
        ttk.Label(g_dim, text="Height (Y):").grid(row=0, column=2, padx=10)
        ttk.Spinbox(g_dim, from_=256, to=1024, increment=16, textvariable=self.var_height).grid(row=0, column=3, sticky="ew")

        # Terrain
        g_ter = ttk.LabelFrame(parent, text="Terrain & Oceans")
        g_ter.pack(fill="x", padx=10, pady=5)
        g_ter.columnconfigure(1, weight=1)

        # Sea Level
        ttk.Label(g_ter, text="Sea Level:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        ttk.Scale(g_ter, from_=0.1, to=1.0, variable=self.var_sealevel).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(g_ter, textvariable=self.var_sealevel).grid(row=0, column=2, padx=10)

        # Landcover
        ttk.Label(g_ter, text="Landcover:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ttk.Scale(g_ter, from_=0.1, to=5.0, variable=self.var_landcover).grid(row=1, column=1, sticky="ew", padx=10)
        ttk.Label(g_ter, textvariable=self.var_landcover).grid(row=1, column=2, padx=10)

        # Upheaval
        ttk.Label(g_ter, text="Upheaval Rate:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        ttk.Scale(g_ter, from_=0.0, to=5.0, variable=self.var_upheaval).grid(row=2, column=1, sticky="ew", padx=10)
        ttk.Label(g_ter, textvariable=self.var_upheaval).grid(row=2, column=2, padx=10)

        # Resources
        g_res = ttk.LabelFrame(parent, text="Resources & Climate")
        g_res.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(g_res, text="Global Ores (Multiplier):").grid(row=0, column=0, padx=10, pady=5)
        ttk.Spinbox(g_res, from_=0.1, to=5.0, increment=0.1, textvariable=self.var_global_ores, width=5).grid(row=0, column=1)

        ttk.Label(g_res, text="Surface Copper:").grid(row=0, column=2, padx=10)
        cb_cop = ttk.Combobox(g_res, textvariable=self.var_copper, values=["common", "uncommon", "rare", "very rare"], width=10)
        cb_cop.grid(row=0, column=3)

        ttk.Label(g_res, text="Surface Tin:").grid(row=0, column=4, padx=10)
        cb_tin = ttk.Combobox(g_res, textvariable=self.var_tin, values=["common", "uncommon", "rare", "very rare"], width=10)
        cb_tin.grid(row=0, column=5)


    def _build_survival_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        # Difficulty
        s_diff = ttk.LabelFrame(parent, text="Core Difficulty")
        s_diff.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        
        ttk.Label(s_diff, text="Game Mode:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        ttk.Combobox(s_diff, textvariable=self.var_gamemode, values=["survival", "creative"]).grid(row=0, column=1, sticky="w")

        ttk.Label(s_diff, text="Death Penalty:").grid(row=0, column=2, sticky="w", padx=10)
        ttk.Combobox(s_diff, textvariable=self.var_death_punish, values=["dropall", "dropgear", "keepall"]).grid(row=0, column=3, sticky="w")

        ttk.Label(s_diff, text="Grace Timer (Days):").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ttk.Spinbox(s_diff, from_=0, to=100, textvariable=self.var_grace_timer, width=5).grid(row=1, column=1, sticky="w")

        # Mechanics
        s_mech = ttk.LabelFrame(parent, text="Mechanics")
        s_mech.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        ttk.Label(s_mech, text="Hunger Rate:").pack(anchor="w", padx=10, pady=2)
        ttk.Scale(s_mech, from_=0.1, to=3.0, variable=self.var_hunger).pack(fill="x", padx=10, pady=5)
        
        ttk.Label(s_mech, text="Tool Durability:").pack(anchor="w", padx=10, pady=2)
        ttk.Scale(s_mech, from_=0.1, to=5.0, variable=self.var_tool_durability).pack(fill="x", padx=10, pady=5)

        ttk.Checkbutton(s_mech, text="Class Exclusive Recipes", variable=self.var_class_exclusive).pack(anchor="w", padx=10, pady=5)

        # Physics
        s_phys = ttk.LabelFrame(parent, text="Physics")
        s_phys.grid(row=1, column=1, sticky="nsew", padx=10, pady=5)

        ttk.Label(s_phys, text="Block Gravity:").pack(anchor="w", padx=10, pady=2)
        ttk.Combobox(s_phys, textvariable=self.var_gravity, values=["sandgravel", "none"]).pack(fill="x", padx=10, pady=2)

        ttk.Label(s_phys, text="Microblock Chiseling:").pack(anchor="w", padx=10, pady=2)
        ttk.Combobox(s_phys, textvariable=self.var_microblock, values=[0, 1, 2]).pack(fill="x", padx=10, pady=2)
        ttk.Label(s_phys, text="(0=Off, 1=Basic, 2=Creative/All)", font=("Segoe UI", 8), foreground="#7B7468").pack(anchor="w", padx=10)

    def _build_temporal_tab(self, parent):
        t_pnl = ttk.LabelFrame(parent, text="Temporal Stability")
        t_pnl.pack(fill="x", padx=10, pady=10)

        ttk.Checkbutton(t_pnl, text="Enable Temporal Stability", variable=self.var_stability).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=10)

        ttk.Label(t_pnl, text="Temporal Storms:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ttk.Combobox(t_pnl, textvariable=self.var_storms, values=["off", "rare", "sometimes", "often", "veryoften"]).grid(row=1, column=1, sticky="ew")

        ttk.Label(t_pnl, text="Temporal Rifts:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        ttk.Combobox(t_pnl, textvariable=self.var_rifts, values=["off", "visible", "invisible"]).grid(row=2, column=1, sticky="ew")

        ttk.Checkbutton(t_pnl, text="Allow Sleep During Storms", variable=self.var_sleep_storms).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=10)

    def _build_advanced_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.txt_extra_json = tk.Text(parent, height=10, width=40, wrap="word")
        self.txt_extra_json.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        sb = ttk.Scrollbar(parent, orient="vertical", command=self.txt_extra_json.yview)
        self.txt_extra_json.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns", pady=10)
        
        ttk.Label(parent, text="Use this for mod-specific keys not covered in other tabs.", foreground="#B8AF9F").grid(row=1, column=0, sticky="w", padx=10, pady=(0,10))


    # =========================================================
    # LOGIC
    # =========================================================

    def _load_from_state(self):
        state = self.controller.get_state()
        s = state.world_settings

        # Identity
        self.var_world_name.set(s.get("WorldName", "NewWorld"))
        self.var_seed.set(s.get("Seed", ""))

        # Genesis
        self.var_width.set(s.get("WorldWidth", 1024000))
        self.var_height.set(s.get("WorldHeight", 256))
        self.var_sealevel.set(s.get("SeaLevel", 0.43))
        self.var_landcover.set(s.get("Landcover", 1.0))
        self.var_upheaval.set(s.get("UpheavalRate", 0.0))
        self.var_global_ores.set(s.get("GlobalDepositSpawnRate", 1.0))
        self.var_copper.set(s.get("SurfaceCopperDepositFrequency", "common"))
        self.var_tin.set(s.get("SurfaceTinDepositFrequency", "rare"))

        # Survival
        self.var_gamemode.set(s.get("GameMode", "survival"))
        self.var_grace_timer.set(s.get("GraceTimer", 0))
        self.var_death_punish.set(s.get("DeathPunishment", "dropall"))
        self.var_hunger.set(s.get("HungerRate", 1.0))
        self.var_gravity.set(s.get("BlockGravity", "sandgravel"))
        self.var_microblock.set(s.get("MicroblockChiseling", 2))
        self.var_class_exclusive.set(s.get("ClassExclusiveRecipes", True))
        self.var_tool_durability.set(s.get("ToolDurability", 1.0))

        # Temporal
        self.var_stability.set(s.get("TemporalStability", True))
        self.var_storms.set(s.get("TemporalStorms", "sometimes"))
        self.var_rifts.set(s.get("TemporalRifts", "visible"))
        self.var_sleep_storms.set(s.get("SleepDuringStorms", False))

        # Advanced JSON
        extra = s.get("ExtraConfig", {})
        if self.txt_extra_json:
            self.txt_extra_json.delete("1.0", "end")
            self.txt_extra_json.insert("1.0", json.dumps(extra, indent=2))

    def _save_config(self):
        # 1. Harvest all vars
        try:
            new_settings = {
                "WorldName": self.var_world_name.get().strip(),
                "Seed": self.var_seed.get().strip(),
                
                # Genesis
                "WorldWidth": self.var_width.get(),
                "WorldHeight": self.var_height.get(),
                "SeaLevel": self.var_sealevel.get(),
                "Landcover": self.var_landcover.get(),
                "UpheavalRate": self.var_upheaval.get(),
                "GlobalDepositSpawnRate": self.var_global_ores.get(),
                "SurfaceCopperDepositFrequency": self.var_copper.get(),
                "SurfaceTinDepositFrequency": self.var_tin.get(),

                # Survival
                "GameMode": self.var_gamemode.get(),
                "GraceTimer": self.var_grace_timer.get(),
                "DeathPunishment": self.var_death_punish.get(),
                "HungerRate": self.var_hunger.get(),
                "BlockGravity": self.var_gravity.get(),
                "MicroblockChiseling": self.var_microblock.get(),
                "ClassExclusiveRecipes": self.var_class_exclusive.get(),
                "ToolDurability": self.var_tool_durability.get(),

                # Temporal
                "TemporalStability": self.var_stability.get(),
                "TemporalStorms": self.var_storms.get(),
                "TemporalRifts": self.var_rifts.get(),
                "SleepDuringStorms": self.var_sleep_storms.get(),
            }
        except Exception as e:
            messagebox.showerror("Validation Error", f"Check your inputs:\n{e}")
            return

        # 2. Parse Extra JSON
        if self.txt_extra_json:
            raw_json = self.txt_extra_json.get("1.0", "end").strip()
            if raw_json:
                try:
                    extra = json.loads(raw_json)
                    new_settings["ExtraConfig"] = extra
                except json.JSONDecodeError as e:
                    messagebox.showerror("Invalid JSON", f"Advanced Config JSON is invalid:\n{e}")
                    return

        # 3. Send to Controller
        if hasattr(self.controller, "update_world_settings"):
            self.controller.update_world_settings(new_settings)
            messagebox.showinfo("Saved", "World Config saved.\n\nNote: Changes only affect NEW worlds.\nDelete your old save if you want these to take effect.")
        else:
            self.log("[ERROR] Controller missing update_world_settings")