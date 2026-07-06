# tools/repair_imports.py
from __future__ import annotations

import os
import re
from pathlib import Path


# ----------------------------
# .gitignore handling (simple)
# ----------------------------
def load_gitignore(root: Path) -> list[str]:
    p = root / ".gitignore"
    if not p.exists():
        return []
    rules: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        rules.append(s)
    return rules


def is_ignored(rel_posix: str, rules: list[str]) -> bool:
    """
    Minimal .gitignore-ish matcher:
    - supports directory rules like "dist/" or ".venv/"
    - supports suffix globs like "*.pyc"
    - supports simple prefix rules like "build"
    Not a full gitignore engine, but works for typical repos.
    """
    for r in rules:
        # normalize
        r_posix = r.replace("\\", "/")

        # directory rule
        if r_posix.endswith("/"):
            if rel_posix.startswith(r_posix) or f"/{r_posix}" in rel_posix:
                return True
            continue

        # glob-ish suffix
        if r_posix.startswith("*") and r_posix.count("*") == 1:
            suffix = r_posix[1:]
            if rel_posix.endswith(suffix):
                return True
            continue

        # exact-ish prefix
        if rel_posix == r_posix or rel_posix.startswith(r_posix + "/"):
            return True

    return False


# ----------------------------
# Rewrite rules
# ----------------------------
REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    # Fix known registry typo: backups_tab -> backup_tab
    (re.compile(r"from\s+\.(backups_tab)\s+import\b"), "from .backup_tab import"),

    # Optional: make imports package-safe for `python -m src.app`
    (re.compile(r"(^|\n)from\s+orchestration_core(\b)"), r"\1from src.orchestration_core\2"),
    (re.compile(r"(^|\n)import\s+orchestration_core(\b)"), r"\1import src.orchestration_core\2"),

    (re.compile(r"(^|\n)from\s+server_manager_core(\b)"), r"\1from src.server_manager_core\2"),
    (re.compile(r"(^|\n)import\s+server_manager_core(\b)"), r"\1import src.server_manager_core\2"),

    (re.compile(r"(^|\n)from\s+ui_core(\b)"), r"\1from src.ui_core\2"),
    (re.compile(r"(^|\n)import\s+ui_core(\b)"), r"\1import src.ui_core\2"),
]


def rewrite_text(text: str, enable_src_prefix: bool) -> tuple[str, bool]:
    changed = False
    new = text

    for pat, rep in REPLACEMENTS:
        # If src-prefix rewrite is disabled, skip those (but still do the typo fix).
        if not enable_src_prefix:
            if "from src." in rep or "import src." in rep:
                continue

        newer = pat.sub(rep, new)
        if newer != new:
            changed = True
            new = newer

    return new, changed


def ensure_src_package(root: Path) -> bool:
    init = root / "src" / "__init__.py"
    if init.exists():
        return False
    init.parent.mkdir(parents=True, exist_ok=True)
    init.write_text("# src package marker\n", encoding="utf-8")
    return True


def main() -> None:
    root = Path(__file__).resolve().parents[1]  # assumes tools/ under project root
    rules = load_gitignore(root)

    # Toggle this:
    # - False: only fixes obvious typos like backups_tab->backup_tab
    # - True: rewrites imports to src.* so `python -m src.app` works
    ENABLE_SRC_PREFIX = True

    if ENABLE_SRC_PREFIX:
        created = ensure_src_package(root)
        if created:
            print("Created: src/__init__.py")

    changed_files: list[str] = []

    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()

        if is_ignored(rel, rules):
            continue

        # Usually you only want to touch code under src/
        # Comment this out if you want it to apply repo-wide.
        if not rel.startswith("src/"):
            continue

        original = path.read_text(encoding="utf-8", errors="ignore")
        updated, changed = rewrite_text(original, enable_src_prefix=ENABLE_SRC_PREFIX)
        if changed:
            path.write_text(updated, encoding="utf-8")
            changed_files.append(rel)

    if changed_files:
        print("Updated files:")
        for f in changed_files:
            print(" -", f)
    else:
        print("No changes needed.")


if __name__ == "__main__":
    main()
