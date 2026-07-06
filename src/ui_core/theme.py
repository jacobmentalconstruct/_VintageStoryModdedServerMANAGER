# src/ui_core/theme.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


# ============================================================
# THEME CONTROL PANEL
# ============================================================
# All colors live here so you can tweak quickly or modularize later.
PALETTE = {
    # Core surfaces (stone/soil)
    "bg":            "#141311",  # main window background (deep soot)
    "panel":         "#1B1916",  # panels / frames
    "panel_2":       "#211E1A",  # slightly lifted panels
    "border":        "#2E2A24",  # subtle separators

    # Text
    "text":          "#E8E2D6",  # warm parchment
    "text_dim":      "#B8AF9F",  # muted parchment
    "text_disabled": "#7B7468",

    # Inputs
    "input_bg":      "#171614",
    "input_border":  "#3A342C",
    "caret":         "#E8E2D6",

    # Accent (bronze/ember)
    "accent":        "#C58B3A",  # bronze
    "accent_2":      "#A36A2C",  # deeper bronze
    "ember":         "#D96D2B",  # warm ember (warnings / highlights)
    "danger":        "#D24C3F",  # danger
    "ok":            "#78B26E",  # ok (mossy green)

    # Selection / focus
    "select_bg":     "#2C241B",
    "select_fg":     "#F2EADB",
    "focus":         "#C58B3A",

    # Notebook tabs
    "tab_bg":        "#1B1916",
    "tab_active_bg": "#24211D",
    "tab_hover_bg":  "#201D19",
}

FONTS = {
    "base": ("Segoe UI", 10),
    "mono": ("Consolas", 10),
    "heading": ("Segoe UI Semibold", 10),
}

SIZES = {
    "pad_x": 10,
    "pad_y": 8,
    "border": 1,
    "focus_thickness": 1,
    "entry_pad_y": 6,
    "button_pad_y": 7,
}

# ============================================================
# THEME IMPLEMENTATION
# ============================================================

class Theme:
    """
    Vintage Story-inspired dark theme for ttk.

    Notes:
      - We use 'clam' as a stable base theme across platforms.
      - Many ttk widgets don't support true background setting on all OS themes;
        clam generally respects style configs well.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.style = ttk.Style(root)

    def apply(self) -> None:
        # Pick a base theme that respects custom styling.
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Root / default Tk options
        self.root.configure(background=PALETTE["bg"])
        self.root.option_add("*Font", FONTS["base"])
        self.root.option_add("*Background", PALETTE["bg"])
        self.root.option_add("*Foreground", PALETTE["text"])
        self.root.option_add("*insertBackground", PALETTE["caret"])

        # ---------- Base styles ----------
        self.style.configure(
            ".",
            background=PALETTE["bg"],
            foreground=PALETTE["text"],
            fieldbackground=PALETTE["input_bg"],
            bordercolor=PALETTE["border"],
            lightcolor=PALETTE["border"],
            darkcolor=PALETTE["border"],
            troughcolor=PALETTE["panel"],
            relief="flat",
        )

        self.style.configure(
            "TFrame",
            background=PALETTE["panel"],
        )

        self.style.configure(
            "TLabel",
            background=PALETTE["panel"],
            foreground=PALETTE["text"],
        )

        self.style.configure(
            "Heading.TLabel",
            background=PALETTE["panel"],
            foreground=PALETTE["text"],
            font=FONTS["heading"],
        )

        # LabelFrame: frame background + label text color
        self.style.configure(
            "TLabelframe",
            background=PALETTE["panel"],
            bordercolor=PALETTE["border"],
            lightcolor=PALETTE["border"],
            darkcolor=PALETTE["border"],
            relief="groove",
        )
        self.style.configure(
            "TLabelframe.Label",
            background=PALETTE["panel"],
            foreground=PALETTE["text_dim"],
            font=FONTS["heading"],
        )

        # ---------- Buttons ----------
        self.style.configure(
            "TButton",
            background=PALETTE["panel_2"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            focusthickness=SIZES["focus_thickness"],
            focuscolor=PALETTE["focus"],
            padding=(12, SIZES["button_pad_y"]),
        )
        self.style.map(
            "TButton",
            background=[
                ("disabled", PALETTE["panel"]),
                ("pressed", PALETTE["tab_active_bg"]),
                ("active", PALETTE["tab_hover_bg"]),
            ],
            foreground=[
                ("disabled", PALETTE["text_disabled"]),
            ],
            bordercolor=[
                ("focus", PALETTE["focus"]),
                ("active", PALETTE["accent_2"]),
            ],
        )

        # Accent button (use this style name where you want primary actions)
        self.style.configure(
            "Accent.TButton",
            background=PALETTE["accent_2"],
            foreground="#1A1410",
            bordercolor=PALETTE["accent"],
            focusthickness=SIZES["focus_thickness"],
            focuscolor=PALETTE["focus"],
            padding=(12, SIZES["button_pad_y"]),
        )
        self.style.map(
            "Accent.TButton",
            background=[
                ("disabled", PALETTE["panel"]),
                ("pressed", PALETTE["accent"]),
                ("active", PALETTE["accent"]),
            ],
            foreground=[
                ("disabled", PALETTE["text_disabled"]),
                ("active", "#140F0B"),
            ],
            bordercolor=[
                ("focus", PALETTE["focus"]),
                ("active", PALETTE["ember"]),
            ],
        )

        # Danger button (optional)
        self.style.configure(
            "Danger.TButton",
            background=PALETTE["danger"],
            foreground="#140F0B",
            bordercolor=PALETTE["danger"],
            padding=(12, SIZES["button_pad_y"]),
        )
        self.style.map(
            "Danger.TButton",
            background=[
                ("disabled", PALETTE["panel"]),
                ("pressed", "#B84036"),
                ("active", "#C7463C"),
            ],
            foreground=[("disabled", PALETTE["text_disabled"])],
        )

        # ---------- Entries ----------
        self.style.configure(
            "TEntry",
            fieldbackground=PALETTE["input_bg"],
            background=PALETTE["input_bg"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["input_border"],
            lightcolor=PALETTE["input_border"],
            darkcolor=PALETTE["input_border"],
            padding=(10, SIZES["entry_pad_y"]),
            insertcolor=PALETTE["caret"],
        )
        self.style.map(
            "TEntry",
            bordercolor=[
                ("focus", PALETTE["focus"]),
                ("active", PALETTE["accent_2"]),
            ],
            foreground=[
                ("disabled", PALETTE["text_disabled"]),
            ],
            fieldbackground=[
                ("disabled", PALETTE["panel"]),
            ],
        )

        # ---------- Checkbutton / Radiobutton ----------
        self.style.configure(
            "TCheckbutton",
            background=PALETTE["panel"],
            foreground=PALETTE["text"],
        )
        self.style.map(
            "TCheckbutton",
            foreground=[("disabled", PALETTE["text_disabled"])],
            background=[("active", PALETTE["panel"])],
        )

        self.style.configure(
            "TRadiobutton",
            background=PALETTE["panel"],
            foreground=PALETTE["text"],
        )

        # ---------- Combobox ----------
        self.style.configure(
            "TCombobox",
            fieldbackground=PALETTE["input_bg"],
            background=PALETTE["input_bg"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["input_border"],
            arrowsize=14,
            padding=(10, SIZES["entry_pad_y"]),
        )
        self.style.map(
            "TCombobox",
            bordercolor=[
                ("focus", PALETTE["focus"]),
                ("active", PALETTE["accent_2"]),
            ],
            fieldbackground=[
                ("readonly", PALETTE["input_bg"]),
                ("disabled", PALETTE["panel"]),
            ],
            foreground=[
                ("disabled", PALETTE["text_disabled"]),
            ],
        )

        # ---------- Notebook ----------
        self.style.configure(
            "TNotebook",
            background=PALETTE["bg"],
            bordercolor=PALETTE["border"],
            padding=0,
        )
        self.style.configure(
            "TNotebook.Tab",
            background=PALETTE["tab_bg"],
            foreground=PALETTE["text_dim"],
            padding=(12, 8),
            bordercolor=PALETTE["border"],
        )
        self.style.map(
            "TNotebook.Tab",
            background=[
                ("selected", PALETTE["tab_active_bg"]),
                ("active", PALETTE["tab_hover_bg"]),
            ],
            foreground=[
                ("selected", PALETTE["select_fg"]),
                ("active", PALETTE["text"]),
            ],
        )

        # ---------- Scrollbars ----------
        self.style.configure(
            "Vertical.TScrollbar",
            background=PALETTE["panel"],
            troughcolor=PALETTE["input_bg"],
            bordercolor=PALETTE["border"],
            arrowcolor=PALETTE["text_dim"],
            gripcount=0,
        )
        self.style.configure(
            "Horizontal.TScrollbar",
            background=PALETTE["panel"],
            troughcolor=PALETTE["input_bg"],
            bordercolor=PALETTE["border"],
            arrowcolor=PALETTE["text_dim"],
            gripcount=0,
        )
        self.style.map(
            "Vertical.TScrollbar",
            arrowcolor=[("active", PALETTE["text"]), ("disabled", PALETTE["text_disabled"])],
        )
        self.style.map(
            "Horizontal.TScrollbar",
            arrowcolor=[("active", PALETTE["text"]), ("disabled", PALETTE["text_disabled"])],
        )

        # ---------- Treeview (if you add tables later) ----------
        self.style.configure(
            "Treeview",
            background=PALETTE["input_bg"],
            fieldbackground=PALETTE["input_bg"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            rowheight=24,
        )
        self.style.map(
            "Treeview",
            background=[("selected", PALETTE["select_bg"])],
            foreground=[("selected", PALETTE["select_fg"])],
        )
        self.style.configure(
            "Treeview.Heading",
            background=PALETTE["panel_2"],
            foreground=PALETTE["text_dim"],
            bordercolor=PALETTE["border"],
            relief="flat",
        )
        self.style.map(
            "Treeview.Heading",
            background=[("active", PALETTE["tab_hover_bg"])],
            foreground=[("active", PALETTE["text"])],
        )

        # ---------- Make tk.Text (LogView) match the palette ----------
        # ttk styling won't affect tk.Text; LogView sets this explicitly if you want.
        # We expose these so LogView can use them (optional).
        self.root_set_text_defaults()

    def root_set_text_defaults(self) -> None:
        """
        Optional: set Tk option database keys that help non-ttk widgets pick up colors.
        LogView uses tk.Text directly; this improves visual consistency.
        """
        self.root.option_add("*Text.background", PALETTE["input_bg"])
        self.root.option_add("*Text.foreground", PALETTE["text"])
        self.root.option_add("*Text.insertBackground", PALETTE["caret"])
        self.root.option_add("*Text.selectBackground", PALETTE["select_bg"])
        self.root.option_add("*Text.selectForeground", PALETTE["select_fg"])
