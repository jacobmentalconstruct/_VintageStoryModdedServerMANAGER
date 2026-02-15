# src/ui_core/tabs/mods_tab.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from .base_tab import BaseTab

class ModsTab(BaseTab):
    TAB_ID = "mods"
    TAB_TITLE = "Mods"
    ORDER = 18

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)
        
        # UI State
        self.var_profile_name = tk.StringVar()
        self.var_filter = tk.StringVar()
        
        # Data
        self._mod_rows = {}  # map iid -> filename
        self._tree = None

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Layout: 2 Columns
        # Col 0: Active Mod List (The "Deck")
        # Col 1: Profiles & Distribution
        self.frame.columnconfigure(0, weight=2)
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(0, weight=1)

        # ============================================
        # COLUMN 0: The Mod List
        # ============================================
        list_pnl = ttk.LabelFrame(self.frame, text="Installed Mods (Local)")
        list_pnl.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        list_pnl.columnconfigure(0, weight=1)
        list_pnl.rowconfigure(1, weight=1)

        # Filter Bar
        flt = ttk.Frame(list_pnl)
        flt.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ttk.Label(flt, text="Search:").pack(side="left")
        ttk.Entry(flt, textvariable=self.var_filter).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(flt, text="Clear", command=lambda: self.var_filter.set("")).pack(side="left")
        
        # Trigger filter on typing
        self.var_filter.trace_add("write", self._on_filter_change)

        # Treeview
        columns = ("name", "size", "status")
        self._tree = ttk.Treeview(list_pnl, columns=columns, show="headings", selectmode="extended")
        
        self._tree.heading("name", text="Filename")
        self._tree.heading("size", text="Size")
        self._tree.heading("status", text="State")
        
        self._tree.column("name", width=250)
        self._tree.column("size", width=80, anchor="e")
        self._tree.column("status", width=80, anchor="center")

        sb = ttk.Scrollbar(list_pnl, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        
        self._tree.grid(row=1, column=0, sticky="nsew", padx=(10,0), pady=5)
        sb.grid(row=1, column=1, sticky="ns", padx=(0,10), pady=5)
        
        # List Actions
        acts = ttk.Frame(list_pnl)
        acts.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        
        ttk.Button(acts, text="Open Mods Folder", command=self._open_folder).pack(side="left")
        ttk.Button(acts, text="Refresh List", command=self._refresh_list).pack(side="right")

        # ============================================
        # COLUMN 1: Profiles & Bundling
        # ============================================
        sidebar = ttk.Frame(self.frame)
        sidebar.grid(row=0, column=1, sticky="nsew", padx=(0,12), pady=12)
        sidebar.columnconfigure(0, weight=1)

        # --- Panel: Profiles ---
        prof = ttk.LabelFrame(sidebar, text="Mod Profiles")
        prof.pack(fill="x", pady=(0, 15))
        
        ttk.Label(prof, text="Current Profile:").pack(anchor="w", padx=10, pady=(10,2))
        self.cmb_profiles = ttk.Combobox(prof, textvariable=self.var_profile_name)
        self.cmb_profiles.pack(fill="x", padx=10, pady=5)
        
        btn_row = ttk.Frame(prof)
        btn_row.pack(fill="x", padx=10, pady=10)
        ttk.Button(btn_row, text="Save", command=self._save_profile).pack(side="left", fill="x", expand=True, padx=(0,2))
        ttk.Button(btn_row, text="Load", command=self._load_profile).pack(side="left", fill="x", expand=True, padx=(2,0))

        # --- Panel: Distribution ---
        dist = ttk.LabelFrame(sidebar, text="Distribution")
        dist.pack(fill="x", pady=(0, 15))
        
        lbl = ttk.Label(dist, text="Create a .zip bundle of all enabled mods for your players.", wraplength=140, foreground="#B8AF9F")
        lbl.pack(anchor="w", padx=10, pady=10)
        
        ttk.Button(dist, text="📦 Bundle for Clients", command=self._bundle_mods).pack(fill="x", padx=10, pady=(0, 10))

        # --- Panel: Online (Prototype 3 Placeholder) ---
        web = ttk.LabelFrame(sidebar, text="ModDB (Online)")
        web.pack(fill="x")
        
        ttk.Button(web, text="Check for Updates", state="disabled").pack(fill="x", padx=10, pady=10)
        ttk.Label(web, text="(Coming in v1.1)", font=("Segoe UI", 8), foreground="#7B7468").pack(anchor="c", pady=(0,10))

        return self.frame

    # -------------------------
    # Logic
    # -------------------------

    def on_show(self):
        self._refresh_list()
        self._refresh_profiles()

    def _refresh_list(self):
        # 1. Clear UI
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        self._mod_rows.clear()

        # 2. Get Data
        if not hasattr(self.controller, "list_mods"):
            return

        mods = self.controller.list_mods() # Returns list of ModInfo objects
        filter_txt = self.var_filter.get().lower()

        for i, m in enumerate(mods):
            # Filter
            if filter_txt and filter_txt not in m.filename.lower():
                continue
                
            # Formatting
            size_mb = m.size_bytes / (1024 * 1024)
            status = "Active" # We assume all zips in /Mods are active for now
            
            iid = f"mod_{i}"
            self._tree.insert("", "end", iid=iid, values=(m.filename, f"{size_mb:.2f} MB", status))
            self._mod_rows[iid] = m.filename

    def _on_filter_change(self, *args):
        self._refresh_list()

    def _open_folder(self):
        # reuse the controller's helper if available, or just open data path
        state = self.controller.get_state()
        if state.data_path:
            p = Path(state.data_path) / "Mods"
            if not p.exists():
                p.mkdir(parents=True)
            
            import os
            if os.name == "nt":
                os.startfile(str(p))

    # --- Profiles (Basic Implementation) ---

    def _refresh_profiles(self):
        state = self.controller.get_state()
        profiles = list(state.mod_profiles.keys())
        self.cmb_profiles['values'] = profiles

    def _save_profile(self):
        name = self.var_profile_name.get().strip()
        if not name:
            messagebox.showwarning("Save Profile", "Enter a name for this profile.")
            return
        
        # For now, a profile is just a list of ALL currently seen filenames
        # In a real app, we'd only save the *enabled* ones.
        current_mods = list(self._mod_rows.values())
        
        def update_fn(s):
            s.mod_profiles[name] = current_mods
            return s
            
        self.controller.update_state(update_fn)
        self.controller.save_state()
        self._refresh_profiles()
        messagebox.showinfo("Profile Saved", f"Saved {len(current_mods)} mods to profile '{name}'.")

    def _load_profile(self):
        name = self.var_profile_name.get().strip()
        state = self.controller.get_state()
        if name not in state.mod_profiles:
            messagebox.showerror("Load Profile", "Profile not found.")
            return
            
        # Loading logic: In Proto 2, we just show what's IN the profile
        # In Proto 3, we would actually move files in/out of the folder.
        mods_in_profile = state.mod_profiles[name]
        messagebox.showinfo("Load Profile", f"Profile '{name}' contains {len(mods_in_profile)} mods.\n(File syncing not enabled in Prototype 2)")

    # --- Bundling ---

    def _bundle_mods(self):
        try:
            name = self.var_profile_name.get().strip() or "Custom"
            path = self.controller.bundle_mods_for_players(name)
            if path:
                messagebox.showinfo("Bundle Created", f"Client zip created at:\n{path}")
                self.log(f"[OK] Bundle created: {path}")
            else:
                messagebox.showerror("Error", "Failed to create bundle. Check logs.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
