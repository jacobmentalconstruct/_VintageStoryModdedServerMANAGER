# src/ui_core/tabs/mods_tab.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import threading

from .base_tab import BaseTab

class ModsTab(BaseTab):
    TAB_ID = "mods"
    TAB_TITLE = "Mods"
    ORDER = 18

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)
        
        # UI State
        self.var_profile_name = tk.StringVar()
        self.var_local_filter = tk.StringVar()
        self.var_online_filter = tk.StringVar()
        self.var_status = tk.StringVar(value="Ready")
        
        # Data
        self._local_rows = {}   # map iid -> filename
        self._online_rows = {}  # map iid -> ModInfo object
        self._online_cache = [] # Cache the API list

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Master Layout: Notebook for separation
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- TAB 1: INSTALLED (LOCAL) ---
        self.tab_local = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_local, text="Installed (Local)")
        self._build_local_tab(self.tab_local)
        
        # --- TAB 2: BROWSE (ONLINE) ---
        self.tab_online = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_online, text="Browse (Online)")
        self._build_online_tab(self.tab_online)

        # Status Bar at bottom of main frame
        stat = ttk.Frame(self.frame, relief="sunken")
        stat.pack(fill="x", side="bottom")
        ttk.Label(stat, textvariable=self.var_status, font=("Segoe UI", 9)).pack(anchor="w", padx=5)

        return self.frame

    # ============================================
    # BUILDERS
    # ============================================

    def _build_local_tab(self, parent):
        parent.columnconfigure(0, weight=2)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        # Left: Local List
        pnl_list = ttk.LabelFrame(parent, text="Library")
        pnl_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        pnl_list.columnconfigure(0, weight=1)
        pnl_list.rowconfigure(1, weight=1)

        # Filter
        flt = ttk.Frame(pnl_list)
        flt.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(flt, text="Filter:").pack(side="left")
        ttk.Entry(flt, textvariable=self.var_local_filter).pack(side="left", fill="x", expand=True, padx=5)
        self.var_local_filter.trace_add("write", lambda *args: self._refresh_local_list())

        # Tree
        cols = ("name", "size", "side")
        self._tree_local = ttk.Treeview(pnl_list, columns=cols, show="headings")
        self._tree_local.heading("name", text="Filename")
        self._tree_local.heading("size", text="Size")
        self._tree_local.heading("side", text="Side")
        self._tree_local.column("name", width=200)
        self._tree_local.column("size", width=70, anchor="e")
        self._tree_local.column("side", width=70, anchor="center")

        sb = ttk.Scrollbar(pnl_list, orient="vertical", command=self._tree_local.yview)
        self._tree_local.configure(yscrollcommand=sb.set)
        
        self._tree_local.grid(row=1, column=0, sticky="nsew", padx=5)
        sb.grid(row=1, column=1, sticky="ns", pady=5)
        
        ttk.Button(pnl_list, text="Refresh", command=self._refresh_local_list).grid(row=2, column=0, sticky="e", padx=5, pady=5)

        # Right: Profiles & Bundle
        sidebar = ttk.Frame(parent)
        sidebar.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        # Profiles
        prof = ttk.LabelFrame(sidebar, text="Mod Profiles")
        prof.pack(fill="x", pady=(0, 15))
        
        ttk.Label(prof, text="Profile Name:").pack(anchor="w", padx=10, pady=(5,0))
        self.cmb_profiles = ttk.Combobox(prof, textvariable=self.var_profile_name)
        self.cmb_profiles.pack(fill="x", padx=10, pady=5)
        
        btn_row = ttk.Frame(prof)
        btn_row.pack(fill="x", padx=10, pady=5)
        ttk.Button(btn_row, text="Save", command=self._save_profile).pack(side="left", fill="x", expand=True)
        ttk.Button(btn_row, text="Load", command=self._load_profile).pack(side="left", fill="x", expand=True, padx=(5,0))

        # Bundle
        dist = ttk.LabelFrame(sidebar, text="Client Distribution")
        dist.pack(fill="x")
        lbl = ttk.Label(dist, text="Create a .zip for players.", foreground="#B8AF9F")
        lbl.pack(anchor="w", padx=10, pady=5)
        ttk.Button(dist, text="📦 Create Bundle", command=self._bundle_mods).pack(fill="x", padx=10, pady=10)


    def _build_online_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Top Bar
        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ttk.Button(top, text="☁️ Fetch Catalog", command=self._start_fetch_online).pack(side="left")
        
        ttk.Label(top, text="Search:").pack(side="left", padx=(20, 5))
        ttk.Entry(top, textvariable=self.var_online_filter).pack(side="left", fill="x", expand=True)
        self.var_online_filter.trace_add("write", lambda *args: self._filter_online_view())

        # Tree
        cols = ("name", "side", "modid")
        self._tree_online = ttk.Treeview(parent, columns=cols, show="headings")
        self._tree_online.heading("name", text="Mod Name")
        self._tree_online.heading("side", text="Side")
        self._tree_online.heading("modid", text="ID")
        
        self._tree_online.column("name", width=300)
        self._tree_online.column("side", width=80, anchor="center")
        self._tree_online.column("modid", width=50, anchor="e")
        
        sb = ttk.Scrollbar(parent, orient="vertical", command=self._tree_online.yview)
        self._tree_online.configure(yscrollcommand=sb.set)
        
        self._tree_online.grid(row=1, column=0, sticky="nsew", padx=10)
        sb.grid(row=1, column=1, sticky="ns", padx=(0,10), pady=10)

        # Bottom Action
        act = ttk.Frame(parent)
        act.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        ttk.Button(act, text="⬇️ Download Selected", command=self._start_download).pack(side="right")


    # ============================================
    # LOGIC: LOCAL
    # ============================================

    def on_show(self):
        self._refresh_local_list()
        self._refresh_profiles()

    def _refresh_local_list(self):
        # Clear
        for iid in self._tree_local.get_children():
            self._tree_local.delete(iid)
        self._local_rows.clear()

        if not hasattr(self.controller, "list_mods"): return

        mods = self.controller.list_mods()
        flt = self.var_local_filter.get().lower()

        for i, m in enumerate(mods):
            if flt and flt not in m.filename.lower():
                continue
            
            size_mb = f"{m.size_bytes / (1024*1024):.2f} MB"
            iid = f"loc_{i}"
            self._tree_local.insert("", "end", iid=iid, values=(m.filename, size_mb, m.side))
            self._local_rows[iid] = m.filename

    def _refresh_profiles(self):
        state = self.controller.get_state()
        self.cmb_profiles['values'] = list(state.mod_profiles.keys())

    def _save_profile(self):
        name = self.var_profile_name.get().strip()
        if not name: return
        
        # Save current list
        current_mods = list(self._local_rows.values())
        self.controller.update_state(lambda s: s.mod_profiles.update({name: current_mods}) or s)
        self.controller.save_state()
        self._refresh_profiles()
        messagebox.showinfo("Saved", f"Profile '{name}' saved.")

    def _load_profile(self):
        # Just info for now
        name = self.var_profile_name.get().strip()
        state = self.controller.get_state()
        if name in state.mod_profiles:
            count = len(state.mod_profiles[name])
            messagebox.showinfo("Profile", f"Profile '{name}' has {count} mods.\n(Sync logic coming in Wave 3.2)")

    def _bundle_mods(self):
        name = self.var_profile_name.get().strip() or "Custom"
        path = self.controller.bundle_mods_for_players(name)
        if path:
            messagebox.showinfo("Bundle Ready", f"Saved to:\n{path}")
        else:
            messagebox.showerror("Error", "Bundle creation failed.")

    # ============================================
    # LOGIC: ONLINE (THREADED)
    # ============================================

    def _start_fetch_online(self):
        self.var_status.set("Fetching ModDB...")
        # Run in thread
        t = threading.Thread(target=self._thread_fetch, daemon=True)
        t.start()

    def _thread_fetch(self):
        try:
            # Calls the network client via controller
            results = self.controller.fetch_online_mods()
            # UI Update on main thread
            self.frame.after(0, self._on_fetch_complete, results)
        except Exception as e:
            self.frame.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _on_fetch_complete(self, results):
        self._online_cache = results
        self.var_status.set(f"Catalog loaded: {len(results)} mods found.")
        self._filter_online_view()

    def _filter_online_view(self):
        # clear
        for iid in self._tree_online.get_children():
            self._tree_online.delete(iid)
        self._online_rows.clear()

        flt = self.var_online_filter.get().lower()
        
        count = 0
        for i, m in enumerate(self._online_cache):
            if flt and flt not in m.filename.lower():
                continue
            
            # Limit display count for performance if empty filter
            if not flt and count > 100:
                break
                
            iid = f"onl_{i}"
            self._tree_online.insert("", "end", iid=iid, values=(m.filename, m.side, m.modid))
            self._online_rows[iid] = m
            count += 1

    def _start_download(self):
        sel = self._tree_online.selection()
        if not sel:
            return
        
        item_id = sel[0]
        mod_info = self._online_rows.get(item_id)
        
        if not mod_info or not mod_info.download_url:
            messagebox.showerror("Unavailable", "This mod does not have a direct download URL.")
            return

        confirm = messagebox.askyesno("Download", f"Download '{mod_info.filename}'?")
        if not confirm:
            return

        self.var_status.set(f"Downloading {mod_info.filename}...")
        t = threading.Thread(target=self._thread_download, args=(mod_info,), daemon=True)
        t.start()

    def _thread_download(self, mod_info):
        try:
            # Generate a filename if the URL doesn't have one clearly
            fname = f"{mod_info.filename.replace(' ', '_')}.zip"
            
            self.controller.install_mod_from_url(mod_info.download_url, fname)
            
            self.frame.after(0, lambda: self.var_status.set(f"Installed: {mod_info.filename}"))
            self.frame.after(0, self._refresh_local_list)
            self.frame.after(0, lambda: messagebox.showinfo("Success", f"Installed {mod_info.filename}"))
        except Exception as e:
            self.frame.after(0, lambda: messagebox.showerror("Download Failed", str(e)))
            self.frame.after(0, lambda: self.var_status.set("Download failed."))