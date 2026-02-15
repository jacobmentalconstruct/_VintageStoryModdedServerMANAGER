# src/ui_core/tabs/mods_tab.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import threading
import math

from .base_tab import BaseTab

class ModsTab(BaseTab):
    TAB_ID = "mods"
    TAB_TITLE = "Mods"
    ORDER = 18
    PAGE_SIZE = 50

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)
        
        # UI State
        self.var_profile_name = tk.StringVar()
        self.var_local_filter = tk.StringVar()
        
        # Online Filters
        self.var_online_search = tk.StringVar()
        self.var_online_category = tk.StringVar(value="All Categories")
        self.var_online_side = tk.StringVar(value="Any Side")
        
        self.var_status = tk.StringVar(value="Ready")
        self.var_page_info = tk.StringVar(value="Page 1 of 1")
        
        # Data
        self._local_rows = {}   
        self._online_rows = {}  
        
        self._all_online_mods = []      
        self._filtered_online_mods = [] 
        self._current_page = 0          
        
        self._known_tags = ["All Categories"] # Will populate dynamically

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # TAB 1: LOCAL
        self.tab_local = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_local, text="Installed (Local)")
        self._build_local_tab(self.tab_local)
        
        # TAB 2: ONLINE
        self.tab_online = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_online, text="Browse (Online)")
        self._build_online_tab(self.tab_online)

        # Status Bar
        stat = ttk.Frame(self.frame, relief="sunken")
        stat.pack(fill="x", side="bottom")
        ttk.Label(stat, textvariable=self.var_status, font=("Segoe UI", 9)).pack(anchor="w", padx=5)

        return self.frame

    def _build_local_tab(self, parent):
        # ... (Identical to previous version, omitted for brevity but structure maintained) ...
        # For safety/completeness, using simplified rebuild here:
        parent.columnconfigure(0, weight=2)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        pnl_list = ttk.LabelFrame(parent, text="Library")
        pnl_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        pnl_list.columnconfigure(0, weight=1)
        pnl_list.rowconfigure(1, weight=1)

        flt = ttk.Frame(pnl_list)
        flt.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(flt, text="Filter:").pack(side="left")
        ttk.Entry(flt, textvariable=self.var_local_filter).pack(side="left", fill="x", expand=True, padx=5)
        self.var_local_filter.trace_add("write", lambda *args: self._refresh_local_list())

        cols = ("name", "size", "side")
        self._tree_local = ttk.Treeview(pnl_list, columns=cols, show="headings")
        self._tree_local.heading("name", text="Filename")
        self._tree_local.heading("size", text="Size")
        self._tree_local.heading("side", text="Side")
        self._tree_local.column("name", width=200)
        self._tree_local.grid(row=1, column=0, sticky="nsew", padx=5)
        
        sb = ttk.Scrollbar(pnl_list, orient="vertical", command=self._tree_local.yview)
        self._tree_local.configure(yscrollcommand=sb.set)
        sb.grid(row=1, column=1, sticky="ns", pady=5)
        
        ttk.Button(pnl_list, text="Refresh", command=self._refresh_local_list).grid(row=2, column=0, sticky="e", padx=5, pady=5)

        sidebar = ttk.Frame(parent)
        sidebar.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        prof = ttk.LabelFrame(sidebar, text="Mod Profiles")
        prof.pack(fill="x", pady=(0, 15))
        ttk.Label(prof, text="Profile Name:").pack(anchor="w", padx=10, pady=(5,0))
        self.cmb_profiles = ttk.Combobox(prof, textvariable=self.var_profile_name)
        self.cmb_profiles.pack(fill="x", padx=10, pady=5)
        btn_row = ttk.Frame(prof)
        btn_row.pack(fill="x", padx=10, pady=5)
        ttk.Button(btn_row, text="Save", command=self._save_profile).pack(side="left", fill="x", expand=True)
        ttk.Button(btn_row, text="Load", command=self._load_profile).pack(side="left", fill="x", expand=True)

        dist = ttk.LabelFrame(sidebar, text="Distribution")
        dist.pack(fill="x")
        ttk.Button(dist, text="📦 Create Bundle", command=self._bundle_mods).pack(fill="x", padx=10, pady=10)

    def _build_online_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # --- Filter Bar (Advanced) ---
        top = ttk.LabelFrame(parent, text="Advanced Filters")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        # Row 1: Search & Fetch
        r1 = ttk.Frame(top)
        r1.pack(fill="x", padx=5, pady=5)
        ttk.Button(r1, text="☁️ Fetch Catalog", command=self._start_fetch_online).pack(side="left")
        ttk.Label(r1, text="Search Name:").pack(side="left", padx=(15, 5))
        ttk.Entry(r1, textvariable=self.var_online_search).pack(side="left", fill="x", expand=True)

        # Row 2: Categories & Sides
        r2 = ttk.Frame(top)
        r2.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(r2, text="Category:").pack(side="left")
        self.cmb_categories = ttk.Combobox(r2, textvariable=self.var_online_category, state="readonly", width=25)
        self.cmb_categories.pack(side="left", padx=(5, 15))
        self.cmb_categories['values'] = ["All Categories"]
        
        ttk.Label(r2, text="Side:").pack(side="left")
        self.cmb_sides = ttk.Combobox(r2, textvariable=self.var_online_side, state="readonly", width=15)
        self.cmb_sides.pack(side="left", padx=(5, 15))
        self.cmb_sides['values'] = ["Any Side", "Client", "Server", "Both"]
        
        ttk.Button(r2, text="Apply Filters", command=self._apply_online_filter).pack(side="right")

        # Triggers
        self.var_online_search.trace_add("write", lambda *args: self._apply_online_filter())
        self.cmb_categories.bind("<<ComboboxSelected>>", lambda e: self._apply_online_filter())
        self.cmb_sides.bind("<<ComboboxSelected>>", lambda e: self._apply_online_filter())

        # --- Tree ---
        cols = ("name", "side", "tags") # Added Tags column
        self._tree_online = ttk.Treeview(parent, columns=cols, show="headings")
        self._tree_online.heading("name", text="Mod Name")
        self._tree_online.heading("side", text="Side")
        self._tree_online.heading("tags", text="Tags")
        
        self._tree_online.column("name", width=250)
        self._tree_online.column("side", width=60, anchor="center")
        self._tree_online.column("tags", width=200, anchor="w")
        
        sb = ttk.Scrollbar(parent, orient="vertical", command=self._tree_online.yview)
        self._tree_online.configure(yscrollcommand=sb.set)
        
        self._tree_online.grid(row=1, column=0, sticky="nsew", padx=10)
        sb.grid(row=1, column=1, sticky="ns", padx=(0,10), pady=10)

        # --- Pagination ---
        pag = ttk.Frame(parent)
        pag.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        ttk.Button(pag, text="< Prev", command=self._prev_page).pack(side="left")
        ttk.Label(pag, textvariable=self.var_page_info).pack(side="left", padx=15)
        ttk.Button(pag, text="Next >", command=self._next_page).pack(side="left")
        ttk.Button(pag, text="⬇️ Download Selected", command=self._start_download).pack(side="right")

    # ============================================
    # LOGIC
    # ============================================

    def on_show(self):
        self._refresh_local_list()
        self._refresh_profiles()

    def _refresh_local_list(self):
        for iid in self._tree_local.get_children():
            self._tree_local.delete(iid)
        self._local_rows.clear()
        if not hasattr(self.controller, "list_mods"): return
        
        mods = self.controller.list_mods()
        flt = self.var_local_filter.get().lower()
        for i, m in enumerate(mods):
            if flt and flt not in m.filename.lower(): continue
            size_mb = f"{m.size_bytes / (1024*1024):.2f} MB"
            iid = f"loc_{i}"
            self._tree_local.insert("", "end", iid=iid, values=(m.filename, size_mb, m.side))
            self._local_rows[iid] = m.filename

    def _refresh_profiles(self):
        state = self.controller.get_state()
        self.cmb_profiles['values'] = list(state.mod_profiles.keys())

    def _save_profile(self):
        name = self.var_profile_name.get().strip()
        if name:
            current_mods = list(self._local_rows.values())
            self.controller.update_state(lambda s: s.mod_profiles.update({name: current_mods}) or s)
            self.controller.save_state()
            self._refresh_profiles()

    def _load_profile(self):
        name = self.var_profile_name.get().strip()
        state = self.controller.get_state()
        if name in state.mod_profiles:
            messagebox.showinfo("Profile", f"Profile '{name}' has {len(state.mod_profiles[name])} mods.")

    def _bundle_mods(self):
        name = self.var_profile_name.get().strip() or "Custom"
        self.controller.bundle_mods_for_players(name)

    # --- ONLINE LOGIC ---

    def _start_fetch_online(self):
        self.var_status.set("Fetching ModDB...")
        t = threading.Thread(target=self._thread_fetch, daemon=True)
        t.start()

    def _thread_fetch(self):
        try:
            results = self.controller.fetch_online_mods()
            self.frame.after(0, self._on_fetch_complete, results)
        except Exception as e:
            self.frame.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _on_fetch_complete(self, results):
        self._all_online_mods = results
        self.var_status.set(f"Catalog loaded: {len(results)} mods.")
        
        # Dynamic Tag Extraction
        unique_tags = set()
        for m in results:
            for t in m.tags:
                unique_tags.add(t)
        
        sorted_tags = sorted(list(unique_tags))
        self.cmb_categories['values'] = ["All Categories"] + sorted_tags
        
        self._apply_online_filter()

    def _apply_online_filter(self):
        search = self.var_online_search.get().lower()
        cat = self.var_online_category.get()
        side = self.var_online_side.get()

        filtered = []
        for m in self._all_online_mods:
            # 1. Search Check
            if search and search not in m.filename.lower():
                continue
            
            # 2. Category Check
            if cat != "All Categories":
                if cat not in m.tags:
                    continue
            
            # 3. Side Check
            if side != "Any Side":
                # API sides are "Both", "Client", "Server"
                # If mod is "Both", it matches Client AND Server requests usually
                # But strict matching:
                if m.side.lower() != side.lower() and m.side.lower() != "both":
                    continue

            filtered.append(m)

        self._filtered_online_mods = filtered
        self._current_page = 0
        self._render_online_page()

    def _render_online_page(self):
        for iid in self._tree_online.get_children():
            self._tree_online.delete(iid)
        self._online_rows.clear()

        total = len(self._filtered_online_mods)
        if total == 0:
            self.var_page_info.set("No results")
            return

        start = self._current_page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_items = self._filtered_online_mods[start:end]

        for i, m in enumerate(page_items):
            tags_str = ", ".join(m.tags[:3]) # Show first 3 tags
            iid = f"onl_{start + i}"
            self._tree_online.insert("", "end", iid=iid, values=(m.filename, m.side, tags_str))
            self._online_rows[iid] = m

        total_pages = math.ceil(total / self.PAGE_SIZE)
        self.var_page_info.set(f"Page {self._current_page + 1} of {total_pages} ({total} mods)")

    def _next_page(self):
        total = len(self._filtered_online_mods)
        max_page = math.ceil(total / self.PAGE_SIZE) - 1
        if self._current_page < max_page:
            self._current_page += 1
            self._render_online_page()

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_online_page()

    def _start_download(self):
        sel = self._tree_online.selection()
        if not sel: return
        item_id = sel[0]
        mod_info = self._online_rows.get(item_id)
        if not mod_info or not mod_info.download_url:
            messagebox.showerror("Unavailable", "No download URL.")
            return

        if messagebox.askyesno("Download", f"Download '{mod_info.filename}'?"):
            self.var_status.set(f"Downloading {mod_info.filename}...")
            t = threading.Thread(target=self._thread_download, args=(mod_info,), daemon=True)
            t.start()

    def _thread_download(self, mod_info):
        try:
            fname = f"{mod_info.filename.replace(' ', '_')}.zip"
            self.controller.install_mod_from_url(mod_info.download_url, fname)
            self.frame.after(0, lambda: self.var_status.set(f"Installed: {mod_info.filename}"))
            self.frame.after(0, self._refresh_local_list)
        except Exception as e:
            self.frame.after(0, lambda: messagebox.showerror("Download Failed", str(e)))