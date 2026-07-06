from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class LogView(ttk.Frame):
    def __init__(self, parent, *, max_lines: int = 2000):
        super().__init__(parent)
        self._max_lines = max_lines
        self._line_count = 0

        self.text = tk.Text(self, height=12, wrap="none")
        self.text.configure(state="disabled")

        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def append_lines(self, lines: list[str]) -> None:
        if not lines:
            return

        self.text.configure(state="normal")
        for line in lines:
            self.text.insert("end", line + "\n")
            self._line_count += 1

        # Trim oldest lines if too many
        if self._line_count > self._max_lines:
            trim = self._line_count - self._max_lines
            # delete first N lines
            self.text.delete("1.0", f"{trim + 1}.0")
            self._line_count = self._max_lines

        self.text.see("end")
        self.text.configure(state="disabled")

