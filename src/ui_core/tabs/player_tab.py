# src/ui_core/tabs/player_tab.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from .base_tab import BaseTab

class PlayerTab(BaseTab):
    TAB_ID = "players"
    TAB_TITLE = "Player Mgmt"
    ORDER = 12  # Right after Server, before World

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)
        
        # Player Data
        self._tree = None
        self.var_manual_player = tk.StringVar()

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        
        # Layout: Left (List) vs Right (Actions)
        self.frame.columnconfigure(0, weight=3) # List takes more space
        self.frame.columnconfigure(1, weight=1) # Actions
        self.frame.rowconfigure(0, weight=1)

        # ============================================
        # COLUMN 0: Online Players List
        # ============================================
        list_frame = ttk.LabelFrame(self.frame, text="Online Players")
        list_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ("name", "role", "duration")
        self._tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        
        self._tree.heading("name", text="Player Name")
        self._tree.heading("role", text="Role")
        self._tree.heading("duration", text="Session Time")
        
        self._tree.column("name", width=150, anchor="w")
        self._tree.column("role", width=80, anchor="center")
        self._tree.column("duration", width=100, anchor="e")

        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        
        self._tree.grid(row=0, column=0, sticky="nsew", padx=(10,0), pady=10)
        sb.grid(row=0, column=1, sticky="ns", padx=(0,10), pady=10)

        # Refresh Button (Explicit)
        btn_refresh = ttk.Button(list_frame, text="Refresh List", command=self._refresh_list)
        btn_refresh.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0,10))

        # ============================================
        # COLUMN 1: Administration
        # ============================================
        admin = ttk.LabelFrame(self.frame, text="Administration")
        admin.grid(row=0, column=1, sticky="nsew", padx=(0,12), pady=12)
        admin.columnconfigure(0, weight=1)

        # -- Target Selection --
        ttk.Label(admin, text="Target Player:").pack(anchor="w", padx=10, pady=(15, 5))
        
        # This entry updates when you click the tree, or you can type manually
        self.entry_target = ttk.Entry(admin, textvariable=self.var_manual_player)
        self.entry_target.pack(fill="x", padx=10, pady=5)
        
        # Bind tree selection to the entry box
        self._tree.bind("<<TreeviewSelect>>", self._on_select_player)

        ttk.Separator(admin, orient="horizontal").pack(fill="x", padx=10, pady=15)

        # -- Moderation Buttons --
        # These call the standard VS commands: /kick, /ban, /op
        ttk.Button(admin, text="Kick Player", command=self._do_kick).pack(fill="x", padx=10, pady=5)
        ttk.Button(admin, text="Ban Player", command=self._do_ban).pack(fill="x", padx=10, pady=5)
        
        ttk.Separator(admin, orient="horizontal").pack(fill="x", padx=10, pady=15)
        
        ttk.Button(admin, text="Grant Admin (OP)", command=self._do_op).pack(fill="x", padx=10, pady=5)
        ttk.Button(admin, text="Revoke Admin", command=self._do_deop).pack(fill="x", padx=10, pady=5)
        
        ttk.Separator(admin, orient="horizontal").pack(fill="x", padx=10, pady=15)

        ttk.Button(admin, text="Whitelist Add...", command=self._do_whitelist).pack(fill="x", padx=10, pady=5)

        return self.frame

    # -------------------------
    # Logic
    # -------------------------

    def on_show(self):
        self._refresh_list()

    def _on_select_player(self, event):
        selection = self._tree.selection()
        if selection:
            item = self._tree.item(selection[0])
            name = item['values'][0]
            self.var_manual_player.set(name)

    def _refresh_list(self):
        # Clear current
        for iid in self._tree.get_children():
            self._tree.delete(iid)
            
        # 1. Ask Controller for data (We will implement the log parser later)
        # For now, we handle the case where the method might be missing safely
        if not hasattr(self.controller, "get_online_players"):
            # Placeholder for prototype
            return

        players = self.controller.get_online_players() 
        for p in players:
            self._tree.insert("", "end", values=(p.name, p.role, p.duration))

    # --- Command Helpers ---

    def _get_target(self):
        t = self.var_manual_player.get().strip()
        if not t:
            messagebox.showwarning("No Target", "Select a player or type a name first.")
            return None
        return t

    def _send_cmd(self, cmd_str):
        try:
            self.controller.send_server_command(cmd_str)
            self.log(f"[ADMIN] Sent: {cmd_str}")
        except Exception as e:
            messagebox.showerror("Command Failed", str(e))

    # --- Actions ---

    def _do_kick(self):
        target = self._get_target()
        if target:
            reason = simpledialog.askstring("Kick", f"Reason for kicking {target}?", parent=self.frame)
            cmd = f"/kick {target} {reason}" if reason else f"/kick {target}"
            self._send_cmd(cmd)

    def _do_ban(self):
        target = self._get_target()
        if target:
            if messagebox.askyesno("Confirm Ban", f"Are you sure you want to BAN {target}?"):
                reason = simpledialog.askstring("Ban", f"Reason for banning {target}?", parent=self.frame)
                cmd = f"/ban {target} {reason}" if reason else f"/ban {target}"
                self._send_cmd(cmd)

    def _do_op(self):
        target = self._get_target()
        if target:
            if messagebox.askyesno("Confirm OP", f"Give FULL ADMIN rights to {target}?"):
                self._send_cmd(f"/op {target}")

    def _do_deop(self):
        target = self._get_target()
        if target:
            self._send_cmd(f"/op remove {target}") # VS syntax for de-op

    def _do_whitelist(self):
        target = simpledialog.askstring("Whitelist", "Enter username to whitelist:", parent=self.frame)
        if target:
            self._send_cmd(f"/whitelist add {target}")
