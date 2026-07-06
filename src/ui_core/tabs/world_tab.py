# src/ui_core/tabs/world_tab.py
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import replace

try:
    from src.orchestration_core.errors import ValidationError
except ModuleNotFoundError:  # fallback for non -m launch
    from orchestration_core.errors import ValidationError

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
        self.var_profile = tk.StringVar(value="Standard")

        # --- Tab 1: Genesis (Map) ---
        self.var_width = tk.IntVar(value=1024000)
        self.var_length = tk.IntVar(value=1024000)
        self.var_height = tk.IntVar(value=256)
        self.var_polar_distance = tk.IntVar(value=100000)
        self.var_landcover_percent = tk.DoubleVar(value=97.5)
        self.var_landcover_scale = tk.DoubleVar(value=5.0)
        self.var_upheaval_percent = tk.DoubleVar(value=30.0)
        self.var_geo_activity_percent = tk.DoubleVar(value=5.0)
        self.var_landform_scale = tk.DoubleVar(value=1.0)
        self.var_world_climate = tk.StringVar(value="realistic")
        self.var_world_edge = tk.StringVar(value="traversable")
        self.var_global_temperature = tk.DoubleVar(value=1.0)
        self.var_global_precipitation = tk.DoubleVar(value=1.0)
        self.var_global_forestation = tk.DoubleVar(value=0.0)
        self.var_global_ores = tk.DoubleVar(value=1.0)
        self.var_surface_copper = tk.DoubleVar(value=0.12)
        self.var_surface_tin = tk.DoubleVar(value=0.007)
        self.var_snow_accum = tk.BooleanVar(value=True)

        # --- Tab 2: Survival (Rules) ---
        self.var_gamemode = tk.StringVar(value="survival")
        self.var_starting_climate = tk.StringVar(value="temperate")
        self.var_spawn_radius = tk.IntVar(value=50)
        self.var_grace_timer = tk.IntVar(value=0)
        self.var_death_punish = tk.StringVar(value="drop")
        self.var_dropped_items_timer = tk.IntVar(value=600)
        self.var_seasons = tk.StringVar(value="enabled")
        self.var_player_lives = tk.IntVar(value=-1)
        self.var_hunger = tk.DoubleVar(value=1.0)
        self.var_hostility = tk.StringVar(value="aggressive")
        self.var_creature_strength = tk.DoubleVar(value=1.0)
        self.var_player_health = tk.DoubleVar(value=15.0)
        self.var_gravity = tk.StringVar(value="sandgravel") # sandgravel or none
        self.var_cave_ins = tk.StringVar(value="off")
        self.var_microblock = tk.StringVar(value="stonewood")
        self.var_class_exclusive = tk.BooleanVar(value=True)
        self.var_tool_durability = tk.DoubleVar(value=1.0)
        self.var_tool_mining_speed = tk.DoubleVar(value=1.0)
        self.var_propick_radius = tk.IntVar(value=6)
        self.var_allow_map = tk.BooleanVar(value=True)
        self.var_allow_coordinate_hud = tk.BooleanVar(value=True)

        # --- Tab 3: Temporal (Clockwork) ---
        self.var_stability = tk.BooleanVar(value=True)
        self.var_storms = tk.StringVar(value="sometimes")
        self.var_storm_duration = tk.DoubleVar(value=1.0)
        self.var_rifts = tk.StringVar(value="visible")
        self.var_gear_respawns = tk.IntVar(value=20)
        self.var_sleep_storms = tk.BooleanVar(value=False)

        # --- Tab 4: Advanced ---
        self.txt_extra_json = None
        self.cmb_profiles = None
        self._tree_servers = None
        self._server_rows = {}
        self._generation_locked_buttons = []

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Layout: Identity + server list + settings notebook + actions
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)

        # 1. Identity Header
        top = ttk.LabelFrame(self.frame, text="World Identity")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        ttk.Label(top, text="World Name:").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        ttk.Entry(top, textvariable=self.var_world_name).grid(row=0, column=1, sticky="ew", padx=10)

        ttk.Label(top, text="Seed:").grid(row=0, column=2, sticky="w", padx=10)
        ttk.Entry(top, textvariable=self.var_seed).grid(row=0, column=3, sticky="ew", padx=10)

        ttk.Label(top, text="Config:").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        self.cmb_profiles = ttk.Combobox(top, textvariable=self.var_profile)
        self.cmb_profiles.grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 10))
        btn_load_profile = ttk.Button(top, text="Load", command=self._load_profile)
        btn_load_profile.grid(row=1, column=2, sticky="ew", padx=(10, 4), pady=(0, 10))

        profile_buttons = ttk.Frame(top)
        profile_buttons.grid(row=1, column=3, sticky="e", padx=10, pady=(0, 10))
        btn_save_profile = ttk.Button(profile_buttons, text="Save/Overwrite", command=self._save_profile)
        btn_save_profile.pack(side="left")
        btn_delete_profile = ttk.Button(profile_buttons, text="Delete", command=self._delete_profile)
        btn_delete_profile.pack(side="left", padx=(6, 0))
        self._generation_locked_buttons.extend([btn_load_profile, btn_save_profile, btn_delete_profile])

        # 2. Existing server worlds
        worlds = ttk.LabelFrame(self.frame, text="Server Worlds")
        worlds.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        worlds.columnconfigure(0, weight=1)

        columns = ("name", "id", "map", "port", "path")
        self._tree_servers = ttk.Treeview(worlds, columns=columns, show="headings", selectmode="browse", height=4)
        self._tree_servers.heading("name", text="Name")
        self._tree_servers.heading("id", text="ID")
        self._tree_servers.heading("map", text="Map")
        self._tree_servers.heading("port", text="Port")
        self._tree_servers.heading("path", text="Data Root")
        self._tree_servers.column("name", width=150, anchor="w")
        self._tree_servers.column("id", width=130, anchor="w")
        self._tree_servers.column("map", width=80, anchor="center")
        self._tree_servers.column("port", width=70, anchor="center")
        self._tree_servers.column("path", width=520, anchor="w")
        self._tree_servers.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=8)
        self._tree_servers.bind("<Double-1>", lambda _e: self._select_server_from_tree())

        srv_scroll = ttk.Scrollbar(worlds, orient="vertical", command=self._tree_servers.yview)
        self._tree_servers.configure(yscrollcommand=srv_scroll.set)
        srv_scroll.grid(row=0, column=1, sticky="ns", pady=8)

        srv_buttons = ttk.Frame(worlds)
        srv_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(srv_buttons, text="Refresh", command=self._refresh_server_list).pack(side="left")
        btn_use_selected = ttk.Button(srv_buttons, text="Use Selected", command=self._select_server_from_tree)
        btn_use_selected.pack(side="left", padx=(8, 0))
        self._generation_locked_buttons.append(btn_use_selected)

        # 2. The Engine (Notebook)
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

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
        bot = ttk.LabelFrame(self.frame, text="World Lifecycle")
        bot.grid(row=3, column=0, sticky="ew", padx=12, pady=12)
        
        btn_revert = ttk.Button(bot, text="Revert to Saved", command=self._load_from_state)
        btn_revert.pack(side="left", padx=(8, 4), pady=8)
        btn_save_config = ttk.Button(bot, text="Save Configuration", command=self._save_config)
        btn_save_config.pack(side="left", padx=4, pady=8)
        btn_generate = ttk.Button(bot, text="Generate Map", command=self._generate_map)
        btn_generate.pack(side="right", padx=(4, 8), pady=8)
        self._generation_locked_buttons.extend([btn_revert, btn_save_config, btn_generate])

        self._refresh_server_list()
        self._refresh_profiles()
        self._load_from_state()
        self._refresh_generation_lock()
        return self.frame

    def on_show(self) -> None:
        self._refresh_server_list()
        self._refresh_profiles()
        self._load_from_state()
        self._refresh_generation_lock()

    def refresh(self) -> None:
        self._refresh_generation_lock()

    # =========================================================
    # BUILDERS
    # =========================================================

    def _spin(self, parent, label, variable, row, column, from_, to, increment, *, width=10, columns=1):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=10, pady=5)
        ttk.Spinbox(
            parent,
            from_=from_,
            to=to,
            increment=increment,
            textvariable=variable,
            width=width,
        ).grid(row=row, column=column + 1, sticky="ew", padx=10, pady=5)
        if columns > 1:
            parent.columnconfigure(column + 1, weight=1)

    def _combo(self, parent, label, variable, row, column, values, *, width=18, columns=1):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=10, pady=5)
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            width=width,
        ).grid(row=row, column=column + 1, sticky="ew", padx=10, pady=5)
        if columns > 1:
            parent.columnconfigure(column + 1, weight=1)

    def _build_genesis_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        # Dimensions
        g_dim = ttk.LabelFrame(parent, text="Dimensions")
        g_dim.pack(fill="x", padx=10, pady=10)
        for col in (1, 3):
            g_dim.columnconfigure(col, weight=1)
        
        self._spin(g_dim, "Width:", self.var_width, 0, 0, 512, 30000000, 512)
        self._spin(g_dim, "Length:", self.var_length, 0, 2, 512, 30000000, 512)
        self._spin(g_dim, "Height:", self.var_height, 1, 0, 256, 1024, 16)
        self._spin(g_dim, "Pole to Equator:", self.var_polar_distance, 1, 2, 5000, 800000, 5000)

        # Terrain
        g_ter = ttk.LabelFrame(parent, text="Terrain & Landcover")
        g_ter.pack(fill="x", padx=10, pady=5)
        for col in (1, 3):
            g_ter.columnconfigure(col, weight=1)

        self._spin(g_ter, "Landcover %:", self.var_landcover_percent, 0, 0, 0, 100, 0.5)
        self._spin(g_ter, "Landcover Scale:", self.var_landcover_scale, 0, 2, 0.1, 5, 0.1)
        self._spin(g_ter, "Upheaval %:", self.var_upheaval_percent, 1, 0, 0, 100, 1)
        self._spin(g_ter, "Geologic Activity %:", self.var_geo_activity_percent, 1, 2, 0, 40, 1)
        self._spin(g_ter, "Landform Scale:", self.var_landform_scale, 2, 0, 0.2, 3, 0.1)
        self._combo(g_ter, "World Climate:", self.var_world_climate, 2, 2, ["realistic", "patchy"])
        self._combo(g_ter, "World Edge:", self.var_world_edge, 3, 0, ["traversable", "blocked"])
        ttk.Checkbutton(g_ter, text="Snow Accumulation", variable=self.var_snow_accum).grid(row=3, column=2, columnspan=2, sticky="w", padx=10, pady=5)

        # Resources
        g_res = ttk.LabelFrame(parent, text="Resources & Climate")
        g_res.pack(fill="x", padx=10, pady=10)
        for col in (1, 3):
            g_res.columnconfigure(col, weight=1)

        self._spin(g_res, "Temperature Mul:", self.var_global_temperature, 0, 0, 0, 5, 0.1)
        self._spin(g_res, "Rainfall Mul:", self.var_global_precipitation, 0, 2, 0, 5, 0.1)
        self._spin(g_res, "Forestation Offset:", self.var_global_forestation, 1, 0, -1, 1, 0.1)
        self._spin(g_res, "Ore Deposit Mul:", self.var_global_ores, 1, 2, 0, 99, 0.1)
        self._spin(g_res, "Surface Copper:", self.var_surface_copper, 2, 0, 0, 5, 0.01)
        self._spin(g_res, "Surface Tin:", self.var_surface_tin, 2, 2, 0, 5, 0.001)


    def _build_survival_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        # Difficulty
        s_diff = ttk.LabelFrame(parent, text="Core Difficulty")
        s_diff.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        for col in (1, 3):
            s_diff.columnconfigure(col, weight=1)
        
        self._combo(s_diff, "Game Mode:", self.var_gamemode, 0, 0, ["survival", "creative"])
        self._combo(s_diff, "Starting Climate:", self.var_starting_climate, 0, 2, ["temperate", "hot", "warm", "cool", "icy"])
        self._combo(s_diff, "Death Penalty:", self.var_death_punish, 1, 0, ["drop", "dropall", "dropcontents", "keep"])
        self._spin(s_diff, "Grace Timer:", self.var_grace_timer, 1, 2, 0, 100, 1)
        self._spin(s_diff, "Spawn Radius:", self.var_spawn_radius, 2, 0, 0, 100000, 10)
        self._spin(s_diff, "Dropped Items Timer:", self.var_dropped_items_timer, 2, 2, 0, 86400, 60)
        self._combo(s_diff, "Seasons:", self.var_seasons, 3, 0, ["enabled", "spring", "summer", "autumn", "winter"])
        self._spin(s_diff, "Player Lives:", self.var_player_lives, 3, 2, -1, 999, 1)

        # Mechanics
        s_mech = ttk.LabelFrame(parent, text="Mechanics")
        s_mech.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        s_mech.columnconfigure(1, weight=1)

        self._spin(s_mech, "Hunger Speed:", self.var_hunger, 0, 0, 0, 10, 0.1, columns=2)
        self._spin(s_mech, "Player Health:", self.var_player_health, 1, 0, 1, 999, 1, columns=2)
        self._spin(s_mech, "Tool Durability:", self.var_tool_durability, 2, 0, 0, 99, 0.1, columns=2)
        self._spin(s_mech, "Tool Mining Speed:", self.var_tool_mining_speed, 3, 0, 0, 99, 0.1, columns=2)
        self._spin(s_mech, "Propick Node Radius:", self.var_propick_radius, 4, 0, 0, 99, 1, columns=2)
        ttk.Checkbutton(s_mech, text="Class Exclusive Recipes", variable=self.var_class_exclusive).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        ttk.Checkbutton(s_mech, text="Allow Map", variable=self.var_allow_map).grid(row=6, column=0, sticky="w", padx=10, pady=5)
        ttk.Checkbutton(s_mech, text="Allow Coordinate HUD", variable=self.var_allow_coordinate_hud).grid(row=6, column=1, sticky="w", padx=10, pady=5)

        # Physics
        s_phys = ttk.LabelFrame(parent, text="Physics")
        s_phys.grid(row=1, column=1, sticky="nsew", padx=10, pady=5)
        s_phys.columnconfigure(1, weight=1)

        self._combo(s_phys, "Block Gravity:", self.var_gravity, 0, 0, ["sandgravel", "sandgravelsoil", "none"], columns=2)
        self._combo(s_phys, "Cave-ins:", self.var_cave_ins, 1, 0, ["off", "on"], columns=2)
        self._combo(s_phys, "Microblock Chiseling:", self.var_microblock, 2, 0, ["off", "stonewood", "all"], columns=2)
        self._combo(s_phys, "Creature Hostility:", self.var_hostility, 3, 0, ["aggressive", "passive", "off"], columns=2)
        self._spin(s_phys, "Creature Strength:", self.var_creature_strength, 4, 0, 0, 99, 0.1, columns=2)

    def _build_temporal_tab(self, parent):
        t_pnl = ttk.LabelFrame(parent, text="Temporal Stability")
        t_pnl.pack(fill="x", padx=10, pady=10)
        t_pnl.columnconfigure(1, weight=1)

        ttk.Checkbutton(t_pnl, text="Enable Temporal Stability", variable=self.var_stability).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=10)

        ttk.Label(t_pnl, text="Temporal Storms:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ttk.Combobox(t_pnl, textvariable=self.var_storms, values=["off", "veryrare", "rare", "sometimes", "often", "veryoften"]).grid(row=1, column=1, sticky="ew")

        self._spin(t_pnl, "Storm Duration Mul:", self.var_storm_duration, 2, 0, 0, 99, 0.1, columns=2)

        ttk.Label(t_pnl, text="Temporal Rifts:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        ttk.Combobox(t_pnl, textvariable=self.var_rifts, values=["off", "invisible", "visible"]).grid(row=3, column=1, sticky="ew")

        self._spin(t_pnl, "Gear Respawn Uses:", self.var_gear_respawns, 4, 0, -1, 9999, 1, columns=2)
        ttk.Checkbutton(t_pnl, text="Allow Sleep During Storms", variable=self.var_sleep_storms).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=10)

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

    def _refresh_generation_lock(self) -> None:
        generating = bool(self.controller.map_generation_status().get("in_progress"))
        state = "disabled" if generating else "normal"
        for button in self._generation_locked_buttons:
            try:
                button.configure(state=state)
            except Exception:
                pass
        if self.cmb_profiles:
            self.cmb_profiles.configure(state="disabled" if generating else "normal")

    def _refresh_profiles(self) -> None:
        if not self.cmb_profiles:
            return
        try:
            profiles = self.controller.list_world_profiles()
        except Exception as e:
            self.log(f"[ERROR] Failed loading world configs: {e}")
            profiles = {}
        self.cmb_profiles["values"] = list(profiles.keys())

    def _load_profile(self) -> None:
        name = self.var_profile.get().strip()
        if not name:
            messagebox.showinfo("Load Config", "Select or enter a world config name.")
            return

        profiles = self.controller.list_world_profiles()
        settings = profiles.get(name)
        if settings is None:
            messagebox.showerror("Load Config", f"World config not found: {name}")
            return

        self._load_settings(dict(settings))
        self.log(f"[OK] Loaded world config: {name}")

    def _save_profile(self) -> None:
        name = self.var_profile.get().strip()
        if not name:
            messagebox.showinfo("Save Config", "Enter a world config name.")
            return

        try:
            settings = self._collect_settings()
            self.controller.save_world_profile(name, settings)
        except ValidationError as e:
            messagebox.showerror("Save Config", str(e))
            return
        except Exception as e:
            messagebox.showerror("Save Config", str(e))
            return

        self.var_profile.set(name)
        self._refresh_profiles()
        messagebox.showinfo("Save Config", f"Saved world config: {name}")

    def _delete_profile(self) -> None:
        name = self.var_profile.get().strip()
        if not name:
            messagebox.showinfo("Delete Config", "Select or enter a world config name.")
            return
        if not messagebox.askyesno("Delete Config", f"Delete saved world config '{name}'?"):
            return

        try:
            self.controller.delete_world_profile(name)
        except ValidationError as e:
            messagebox.showerror("Delete Config", str(e))
            return
        except Exception as e:
            messagebox.showerror("Delete Config", str(e))
            return

        self.var_profile.set("Standard")
        self._refresh_profiles()
        messagebox.showinfo("Delete Config", f"Deleted world config: {name}")

    def _load_from_state(self):
        state = self.controller.get_state()
        self._load_settings(state.world_settings)

    def _load_settings(self, settings):
        s = settings or {}

        # Identity
        self.var_world_name.set(s.get("WorldName", "NewWorld"))
        self.var_seed.set(s.get("Seed", ""))

        # Genesis
        self.var_width.set(int(s.get("worldWidth", s.get("WorldWidth", 1024000))))
        self.var_length.set(int(s.get("worldLength", s.get("WorldLength", s.get("WorldWidth", 1024000)))))
        self.var_height.set(int(s.get("MapSizeY", s.get("WorldHeight", 256))))
        self.var_polar_distance.set(int(s.get("polarEquatorDistance", 100000)))
        self.var_landcover_percent.set(float(s.get("landcover", 0.975)) * 100)
        self.var_landcover_scale.set(float(s.get("oceanscale", s.get("Landcover", 5.0))))
        self.var_upheaval_percent.set(max(0, min(100, float(s.get("upheavelCommonness", s.get("UpheavalRate", 0.3))) * 100)))
        self.var_geo_activity_percent.set(float(s.get("geologicActivity", 0.05)) * 100)
        self.var_landform_scale.set(float(s.get("landformScale", 1.0)))
        self.var_world_climate.set(s.get("worldClimate", "realistic"))
        self.var_world_edge.set(s.get("worldEdge", "traversable"))
        self.var_global_temperature.set(float(s.get("globalTemperature", 1.0)))
        self.var_global_precipitation.set(float(s.get("globalPrecipitation", 1.0)))
        self.var_global_forestation.set(float(s.get("globalForestation", 0.0)))
        self.var_global_ores.set(float(s.get("globalDepositSpawnRate", s.get("GlobalDepositSpawnRate", 1.0))))
        self.var_surface_copper.set(float(s.get("surfaceCopperDeposits", 0.12)))
        self.var_surface_tin.set(float(s.get("surfaceTinDeposits", 0.007)))
        self.var_snow_accum.set(self._as_bool(s.get("snowAccum", True)))

        # Survival
        self.var_gamemode.set(s.get("gameMode", s.get("GameMode", "survival")))
        self.var_starting_climate.set(s.get("startingClimate", "temperate"))
        self.var_spawn_radius.set(int(s.get("spawnRadius", 50)))
        self.var_grace_timer.set(int(s.get("graceTimer", s.get("GraceTimer", 0))))
        self.var_death_punish.set(s.get("deathPunishment", s.get("DeathPunishment", "drop")))
        self.var_dropped_items_timer.set(int(s.get("droppedItemsTimer", 600)))
        self.var_seasons.set(s.get("seasons", "enabled"))
        self.var_player_lives.set(int(s.get("playerlives", -1)))
        self.var_hunger.set(float(s.get("playerHungerSpeed", s.get("HungerRate", 1.0))))
        self.var_hostility.set(s.get("creatureHostility", "aggressive"))
        self.var_creature_strength.set(float(s.get("creatureStrength", 1.0)))
        self.var_player_health.set(float(s.get("playerHealthPoints", 15.0)))
        self.var_gravity.set(s.get("blockGravity", s.get("BlockGravity", "sandgravel")))
        self.var_cave_ins.set(s.get("caveIns", "off"))
        self.var_microblock.set(self._microblock_value(s.get("microblockChiseling", s.get("MicroblockChiseling", "stonewood"))))
        self.var_class_exclusive.set(self._as_bool(s.get("classExclusiveRecipes", s.get("ClassExclusiveRecipes", True))))
        self.var_tool_durability.set(float(s.get("toolDurability", s.get("ToolDurability", 1.0))))
        self.var_tool_mining_speed.set(float(s.get("toolMiningSpeed", 1.0)))
        self.var_propick_radius.set(int(s.get("propickNodeSearchRadius", 6)))
        self.var_allow_map.set(self._as_bool(s.get("allowMap", True)))
        self.var_allow_coordinate_hud.set(self._as_bool(s.get("allowCoordinateHud", True)))

        # Temporal
        self.var_stability.set(self._as_bool(s.get("temporalStability", s.get("TemporalStability", True))))
        self.var_storms.set(s.get("temporalStorms", s.get("TemporalStorms", "sometimes")))
        self.var_storm_duration.set(float(s.get("tempstormDurationMul", 1.0)))
        self.var_rifts.set(s.get("temporalRifts", s.get("TemporalRifts", "visible")))
        self.var_gear_respawns.set(int(s.get("temporalGearRespawnUses", 20)))
        self.var_sleep_storms.set(self._as_bool(s.get("temporalStormSleeping", s.get("SleepDuringStorms", False))))

        # Advanced JSON
        extra = s.get("ExtraConfig", {})
        if self.txt_extra_json:
            self.txt_extra_json.delete("1.0", "end")
            self.txt_extra_json.insert("1.0", json.dumps(extra, indent=2))

    def _refresh_server_list(self) -> None:
        if not self._tree_servers:
            return

        for iid in self._tree_servers.get_children():
            self._tree_servers.delete(iid)
        self._server_rows.clear()

        state = self.controller.get_state()
        try:
            servers = self.controller.list_server_worlds()
        except Exception as e:
            self.log(f"[ERROR] Failed loading server worlds: {e}")
            return

        for info in servers:
            server_id = str(info.get("id", ""))
            if not server_id:
                continue
            iid = f"srv_{server_id}"
            self._tree_servers.insert(
                "",
                "end",
                iid=iid,
                values=(
                    info.get("name", server_id),
                    server_id,
                    info.get("map_status", "Unknown"),
                    info.get("port", state.port),
                    info.get("data_path", ""),
                ),
            )
            self._server_rows[iid] = server_id
            if server_id == state.selected_server_id:
                self._tree_servers.selection_set(iid)
                self._tree_servers.focus(iid)
                self._tree_servers.see(iid)

    def _select_server_from_tree(self) -> None:
        if not self._tree_servers:
            return
        sel = self._tree_servers.selection()
        if not sel:
            messagebox.showinfo("Select Server", "Select a server world first.")
            return

        server_id = self._server_rows.get(sel[0])
        if not server_id:
            return

        try:
            self.controller.select_server_world(server_id)
            self._load_from_state()
            self._refresh_server_list()
        except ValidationError as e:
            messagebox.showerror("Select Server", str(e))
        except Exception as e:
            messagebox.showerror("Select Server", str(e))

    def _as_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
        return bool(value)

    def _microblock_value(self, value) -> str:
        if value == 0 or value == "0":
            return "off"
        if value == 1 or value == "1":
            return "stonewood"
        if value == 2 or value == "2":
            return "all"
        return str(value or "stonewood")

    def _save_config(self):
        try:
            new_settings = self._collect_settings()
        except Exception as e:
            messagebox.showerror("Validation Error", f"Check your inputs:\n{e}")
            return

        self._save_settings_to_controller(new_settings)

    def _collect_settings(self):
        new_settings = {
            "WorldName": self.var_world_name.get().strip(),
            "Seed": self.var_seed.get().strip(),

            # Genesis
            "worldWidth": self.var_width.get(),
            "worldLength": self.var_length.get(),
            "MapSizeY": self.var_height.get(),
            "polarEquatorDistance": self.var_polar_distance.get(),
            "landcover": round(self.var_landcover_percent.get() / 100, 4),
            "oceanscale": self.var_landcover_scale.get(),
            "upheavelCommonness": round(self.var_upheaval_percent.get() / 100, 4),
            "geologicActivity": round(self.var_geo_activity_percent.get() / 100, 4),
            "landformScale": self.var_landform_scale.get(),
            "worldClimate": self.var_world_climate.get(),
            "worldEdge": self.var_world_edge.get(),
            "globalTemperature": self.var_global_temperature.get(),
            "globalPrecipitation": self.var_global_precipitation.get(),
            "globalForestation": self.var_global_forestation.get(),
            "globalDepositSpawnRate": self.var_global_ores.get(),
            "surfaceCopperDeposits": self.var_surface_copper.get(),
            "surfaceTinDeposits": self.var_surface_tin.get(),
            "snowAccum": self.var_snow_accum.get(),

            # Survival
            "gameMode": self.var_gamemode.get(),
            "startingClimate": self.var_starting_climate.get(),
            "spawnRadius": self.var_spawn_radius.get(),
            "graceTimer": self.var_grace_timer.get(),
            "deathPunishment": self.var_death_punish.get(),
            "droppedItemsTimer": self.var_dropped_items_timer.get(),
            "seasons": self.var_seasons.get(),
            "playerlives": self.var_player_lives.get(),
            "playerHungerSpeed": self.var_hunger.get(),
            "creatureHostility": self.var_hostility.get(),
            "creatureStrength": self.var_creature_strength.get(),
            "playerHealthPoints": self.var_player_health.get(),
            "blockGravity": self.var_gravity.get(),
            "caveIns": self.var_cave_ins.get(),
            "microblockChiseling": self.var_microblock.get(),
            "classExclusiveRecipes": self.var_class_exclusive.get(),
            "toolDurability": self.var_tool_durability.get(),
            "toolMiningSpeed": self.var_tool_mining_speed.get(),
            "propickNodeSearchRadius": self.var_propick_radius.get(),
            "allowMap": self.var_allow_map.get(),
            "allowCoordinateHud": self.var_allow_coordinate_hud.get(),

            # Temporal
            "temporalStability": self.var_stability.get(),
            "temporalStorms": self.var_storms.get(),
            "tempstormDurationMul": self.var_storm_duration.get(),
            "temporalRifts": self.var_rifts.get(),
            "temporalGearRespawnUses": self.var_gear_respawns.get(),
            "temporalStormSleeping": 1 if self.var_sleep_storms.get() else 0,
        }

        if self.txt_extra_json:
            raw_json = self.txt_extra_json.get("1.0", "end").strip()
            if raw_json:
                try:
                    extra = json.loads(raw_json)
                    new_settings["ExtraConfig"] = extra
                except json.JSONDecodeError as e:
                    raise ValidationError(f"Advanced Config JSON is invalid:\n{e}")
        return new_settings

    def _save_settings_to_controller(self, new_settings):
        if hasattr(self.controller, "update_world_settings"):
            try:
                self.controller.update_world_settings(new_settings)
            except ValidationError as e:
                messagebox.showerror("Validation Error", str(e))
                return False
            except Exception as e:
                messagebox.showerror("Save Failed", str(e))
                return False

            messagebox.showinfo(
                "Saved",
                "World config saved.\n\n"
                "Use Generate Map for a server with no active map. "
                "For an existing map, use Reset Map or Delete Map in the Server tab first.",
            )
            return True
        else:
            self.log("[ERROR] Controller missing update_world_settings")
            return False

    def _generate_map(self):
        try:
            new_settings = self._collect_settings()
            info = self.controller.generate_map(new_settings)
        except ValidationError as e:
            messagebox.showerror("Generate Map", str(e))
            return
        except Exception as e:
            messagebox.showerror("Generate Map", str(e))
            return

        if info.get("start_requested"):
            message = (
                f"Map generation prepared for:\n{info['data_path']}\n\n"
                "Server start requested. Watch the console for generation progress."
            )
        else:
            reason = info.get("start_blocked_reason") or "Server start was not requested."
            message = (
                f"Server data root prepared for:\n{info['data_path']}\n\n"
                f"Start was blocked: {reason}\n\n"
                "Set the server executable in the Server tab, then start this server to generate the map."
            )

        messagebox.showinfo("Generate Map", message)
        self._refresh_server_list()
