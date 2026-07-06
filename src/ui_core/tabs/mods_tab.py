# src/ui_core/tabs/mods_tab.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import math

try:
    from src.orchestration_core.errors import ValidationError
except ModuleNotFoundError:  # fallback for non -m launch
    from orchestration_core.errors import ValidationError

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
        self.var_repository_path = tk.StringVar()
        
        # Online Filters
        self.var_online_search = tk.StringVar()
        self.var_online_category = tk.StringVar(value="All Categories")
        self.var_online_side = tk.StringVar(value="Any Side")
        
        self.var_status = tk.StringVar(value="Ready")
        self.var_page_info = tk.StringVar(value="Page 1 of 1")
        
        # Data
        self._repo_rows = {}
        self._active_rows = {}
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
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        source = ttk.LabelFrame(parent, text="Repository Source")
        source.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        source.columnconfigure(1, weight=1)

        ttk.Label(source, text="Folder:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(source, textvariable=self.var_repository_path, state="readonly").grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        ttk.Button(source, text="Project /mods", command=self._use_project_repository).grid(row=0, column=2, padx=(0, 6), pady=8)
        ttk.Button(source, text="Server Mods", command=self._use_server_mods_repository).grid(row=0, column=3, padx=(0, 6), pady=8)
        ttk.Button(source, text="Browse...", command=self._browse_repository).grid(row=0, column=4, padx=(0, 6), pady=8)
        ttk.Button(source, text="Refresh", command=self._refresh_local_list).grid(row=0, column=5, padx=(0, 8), pady=8)

        chooser = ttk.Frame(parent)
        chooser.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        chooser.columnconfigure(0, weight=1)
        chooser.columnconfigure(2, weight=1)
        chooser.rowconfigure(0, weight=1)

        repo = ttk.LabelFrame(chooser, text="Mod Repository")
        repo.grid(row=0, column=0, sticky="nsew")
        repo.columnconfigure(0, weight=1)
        repo.rowconfigure(1, weight=1)

        flt = ttk.Frame(repo)
        flt.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(flt, text="Filter:").pack(side="left")
        ttk.Entry(flt, textvariable=self.var_local_filter).pack(side="left", fill="x", expand=True, padx=5)
        self.var_local_filter.trace_add("write", lambda *args: self._refresh_repository_list())

        cols = ("name", "size")
        self._tree_local = ttk.Treeview(repo, columns=cols, show="headings", selectmode="extended")
        self._tree_repo = self._tree_local
        self._tree_repo.heading("name", text="Filename")
        self._tree_repo.heading("size", text="Size")
        self._tree_repo.column("name", width=260)
        self._tree_repo.column("size", width=90, anchor="e")
        self._tree_repo.grid(row=1, column=0, sticky="nsew", padx=(5, 0), pady=(0, 5))

        repo_sb = ttk.Scrollbar(repo, orient="vertical", command=self._tree_repo.yview)
        self._tree_repo.configure(yscrollcommand=repo_sb.set)
        repo_sb.grid(row=1, column=1, sticky="ns", padx=(0, 5), pady=(0, 5))

        moves = ttk.Frame(chooser)
        moves.grid(row=0, column=1, sticky="ns", padx=8)
        moves.rowconfigure(0, weight=1)
        moves.rowconfigure(5, weight=1)
        ttk.Button(moves, text="Add >", command=self._add_selected_mods).grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(moves, text="Add All >", command=self._add_all_visible_mods).grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Button(moves, text="< Remove", command=self._remove_selected_active_mods).grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Button(moves, text="Clear", command=self._clear_active_mods).grid(row=4, column=0, sticky="ew", pady=4)

        active = ttk.LabelFrame(chooser, text="Active For World")
        active.grid(row=0, column=2, sticky="nsew")
        active.columnconfigure(0, weight=1)
        active.rowconfigure(0, weight=1)

        self._tree_active = ttk.Treeview(active, columns=cols, show="headings", selectmode="extended")
        self._tree_active.heading("name", text="Filename")
        self._tree_active.heading("size", text="Size")
        self._tree_active.column("name", width=260)
        self._tree_active.column("size", width=90, anchor="e")
        self._tree_active.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=5)

        active_sb = ttk.Scrollbar(active, orient="vertical", command=self._tree_active.yview)
        self._tree_active.configure(yscrollcommand=active_sb.set)
        active_sb.grid(row=0, column=1, sticky="ns", padx=(0, 5), pady=5)

        bottom = ttk.LabelFrame(parent, text="Profiles & Distribution")
        bottom.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 10))
        bottom.columnconfigure(1, weight=1)

        ttk.Label(bottom, text="Profile:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.cmb_profiles = ttk.Combobox(bottom, textvariable=self.var_profile_name)
        self.cmb_profiles.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        ttk.Button(bottom, text="Save Active", command=self._save_profile).grid(row=0, column=2, padx=(0, 6), pady=8)
        ttk.Button(bottom, text="Load", command=self._load_profile).grid(row=0, column=3, padx=(0, 6), pady=8)
        ttk.Button(bottom, text="Apply Active Mods", command=self._apply_active_mods).grid(row=0, column=4, padx=(0, 6), pady=8)
        ttk.Button(bottom, text="Create Bundle", command=self._bundle_mods).grid(row=0, column=5, padx=(0, 8), pady=8)

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
        self._tree_online = ttk.Treeview(parent, columns=cols, show="headings", selectmode="extended")
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
        self.var_repository_path.set(self.controller.get_mod_repository_path())
        self._refresh_repository_list()
        self._refresh_active_list()

    def _refresh_repository_list(self):
        for iid in self._tree_repo.get_children():
            self._tree_repo.delete(iid)
        self._repo_rows.clear()
        if not hasattr(self.controller, "list_mod_repository"):
            return
        
        try:
            mods = self.controller.list_mod_repository()
        except Exception as e:
            self.log(f"[ERROR] Failed loading mod repository: {e}")
            messagebox.showerror("Repository", str(e))
            return

        flt = self.var_local_filter.get().lower()
        for i, m in enumerate(mods):
            if flt and flt not in m.filename.lower(): continue
            size_mb = f"{m.size_bytes / (1024*1024):.2f} MB"
            iid = f"repo_{i}"
            self._tree_repo.insert("", "end", iid=iid, values=(m.filename, size_mb))
            self._repo_rows[iid] = m.filename

    def _refresh_active_list(self):
        for iid in self._tree_active.get_children():
            self._tree_active.delete(iid)
        self._active_rows.clear()

        active_mods = self.controller.get_active_mod_names()
        repo_by_name = {m.filename: m for m in self.controller.list_mod_repository()}
        for i, filename in enumerate(active_mods):
            mod_info = repo_by_name.get(filename)
            size_mb = f"{mod_info.size_bytes / (1024*1024):.2f} MB" if mod_info else "Missing"
            iid = f"active_{i}"
            self._tree_active.insert("", "end", iid=iid, values=(filename, size_mb))
            self._active_rows[iid] = filename

    def _refresh_profiles(self):
        state = self.controller.get_state()
        self.cmb_profiles['values'] = list(state.mod_profiles.keys())

    def _save_profile(self):
        name = self.var_profile_name.get().strip()
        if not name:
            messagebox.showinfo("Profile", "Enter a profile name first.")
            return

        current_mods = self._active_mod_names()
        if not current_mods:
            messagebox.showinfo("Profile", "Add mods to the active list first.")
            return

        def save_to_state(state):
            state.mod_profiles = dict(state.mod_profiles)
            state.mod_profiles[name] = current_mods
            return state

        self.controller.update_state(save_to_state)
        self.controller.save_state()
        self._refresh_profiles()
        self.var_status.set(f"Saved profile '{name}' with {len(current_mods)} mods.")

    def _load_profile(self):
        name = self.var_profile_name.get().strip()
        state = self.controller.get_state()
        if name in state.mod_profiles:
            profile_mods = list(state.mod_profiles[name])
            self.controller.set_active_mod_names(profile_mods)
            self._refresh_active_list()
            self.var_status.set(f"Loaded profile '{name}' with {len(profile_mods)} mods.")

    def _bundle_mods(self):
        name = self.var_profile_name.get().strip() or "Custom"
        mods_to_bundle = self._active_mod_names()

        if not mods_to_bundle:
            messagebox.showinfo("Create Bundle", "Add mods to the active list first.")
            return

        try:
            bundle_path = self.controller.bundle_mods_for_players(name, mods_to_bundle)
        except ValidationError as e:
            self.log(f"[ERROR] Cannot create mod bundle: {e}")
            messagebox.showerror("Cannot create bundle", str(e))
            return
        except Exception as e:
            self.log(f"[ERROR] Bundle failed: {e}")
            messagebox.showerror("Bundle failed", str(e))
            return

        if not bundle_path:
            messagebox.showerror(
                "Bundle failed",
                "No bundle was created. Check that the selected mods still exist.",
            )
            return

        self.var_status.set(f"Created bundle with {len(mods_to_bundle)} mods: {bundle_path}")
        messagebox.showinfo("Bundle created", f"Created bundle:\n{bundle_path}")

    def _use_project_repository(self):
        try:
            path = self.controller.use_default_mod_repository()
            self.var_repository_path.set(path)
            self._refresh_local_list()
        except Exception as e:
            messagebox.showerror("Repository", str(e))

    def _use_server_mods_repository(self):
        try:
            path = self.controller.use_server_mods_as_repository()
            self.var_repository_path.set(path)
            self._refresh_local_list()
        except ValidationError as e:
            messagebox.showerror("Repository", str(e))
        except Exception as e:
            messagebox.showerror("Repository", str(e))

    def _browse_repository(self):
        initial = self.var_repository_path.get().strip() or self.controller.default_mod_repository_path()
        path = filedialog.askdirectory(title="Select Mod Repository", initialdir=initial)
        if path:
            self.controller.set_mod_repository_path(path)
            self.var_repository_path.set(path)
            self._refresh_local_list()

    def _selected_repository_mod_names(self):
        return [
            self._repo_rows[iid]
            for iid in self._tree_repo.selection()
            if iid in self._repo_rows
        ]

    def _visible_local_mod_names(self):
        return list(self._repo_rows.values())

    def _selected_active_mod_names(self):
        return [
            self._active_rows[iid]
            for iid in self._tree_active.selection()
            if iid in self._active_rows
        ]

    def _active_mod_names(self):
        return self.controller.get_active_mod_names()

    def _add_selected_mods(self):
        selected = self._selected_repository_mod_names()
        if not selected:
            messagebox.showinfo("Active Mods", "Select one or more repository mods to add.")
            return
        self._add_mods_to_active(selected)

    def _add_all_visible_mods(self):
        visible = self._visible_local_mod_names()
        if not visible:
            messagebox.showinfo("Active Mods", "No visible repository mods to add.")
            return
        self._add_mods_to_active(visible)

    def _add_mods_to_active(self, filenames):
        active = self._active_mod_names()
        seen = set(active)
        for filename in filenames:
            if filename not in seen:
                seen.add(filename)
                active.append(filename)
        self.controller.set_active_mod_names(active)
        self._refresh_active_list()
        self.var_status.set(f"Active list has {len(active)} mods.")

    def _remove_selected_active_mods(self):
        selected = set(self._selected_active_mod_names())
        if not selected:
            messagebox.showinfo("Active Mods", "Select one or more active mods to remove.")
            return
        active = [filename for filename in self._active_mod_names() if filename not in selected]
        self.controller.set_active_mod_names(active)
        self._refresh_active_list()
        self.var_status.set(f"Active list has {len(active)} mods.")

    def _clear_active_mods(self):
        if not self._active_mod_names():
            return
        if not messagebox.askyesno("Active Mods", "Clear the active mod list?"):
            return
        self.controller.set_active_mod_names([])
        self._refresh_active_list()
        self.var_status.set("Active list cleared.")

    def _apply_active_mods(self):
        try:
            copied = self.controller.apply_active_mods_to_server()
        except ValidationError as e:
            messagebox.showerror("Apply Active Mods", str(e))
            return
        except Exception as e:
            messagebox.showerror("Apply Active Mods", str(e))
            return

        self.var_status.set(f"Copied {copied} active mod(s) to the server Mods folder.")
        messagebox.showinfo("Apply Active Mods", f"Copied {copied} active mod(s) to the server Mods folder.")

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
            self.frame.after(0, lambda err=e: messagebox.showerror("Error", str(err)))

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
        if not sel:
            messagebox.showinfo("Download", "Select one or more mods to download.")
            return

        mod_infos = [self._online_rows[iid] for iid in sel if iid in self._online_rows]
        downloadable = [mod for mod in mod_infos if mod.download_url]
        missing_count = len(mod_infos) - len(downloadable)

        if not downloadable:
            messagebox.showerror("Unavailable", "No selected mods have a download URL.")
            return

        count_text = f"{len(downloadable)} selected mod" if len(downloadable) == 1 else f"{len(downloadable)} selected mods"
        warning = f"\n\n{missing_count} selected mod(s) will be skipped because they have no download URL." if missing_count else ""
        if messagebox.askyesno("Download", f"Download {count_text}?{warning}"):
            self.var_status.set(f"Downloading {count_text}...")
            t = threading.Thread(target=self._thread_download_many, args=(downloadable,), daemon=True)
            t.start()

    def _thread_download_many(self, mod_infos):
        installed = []
        failures = []

        for mod_info in mod_infos:
            try:
                fname = self._safe_download_filename(mod_info.filename)
                self.controller.install_mod_to_repository_from_url(mod_info.download_url, fname)
                installed.append(mod_info.filename)
            except Exception as e:
                failures.append((mod_info.filename, str(e)))

        self.frame.after(
            0,
            lambda done=installed, failed=failures: self._on_download_complete(done, failed),
        )

    def _on_download_complete(self, installed, failures):
        if installed:
            self._refresh_repository_list()

        if failures:
            failed_names = ", ".join(name for name, _ in failures[:3])
            suffix = "..." if len(failures) > 3 else ""
            first_reason = failures[0][1]
            self.var_status.set(f"Installed {len(installed)} mod(s); {len(failures)} failed.")
            messagebox.showerror(
                "Download Failed",
                f"Failed to download: {failed_names}{suffix}\n\n{first_reason}",
            )
            return

        self.var_status.set(f"Installed {len(installed)} mod(s).")

    def _safe_download_filename(self, filename):
        safe = "".join(
            ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
            for ch in filename.strip()
        ).strip("._")
        if not safe:
            safe = "downloaded_mod"
        if Path(safe).suffix.lower() not in {".zip", ".dll"}:
            safe = f"{safe}.zip"
        return safe
