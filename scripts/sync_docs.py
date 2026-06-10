#!/usr/bin/env python3
"""sync_docs.py — mirror web/ → docs/ for GitHub Pages.

Copies only what index.html / sim_v2.html actually fetch (HTML, root geometry/layout
JSONs, data/*, timeline/*.jsonl). Idempotent: writes only when content differs.
Never copies web/photos/ (real warehouse photos stay local).
"""
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DOCS = ROOT / "docs"

ROOT_FILES = (
    "index.html", "sim_v2.html",
    "dwg_codex_geometry.json", "viewer_layout_v1.json", "layout.json", "route_debug.json",
)


def _sync(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and hashlib.md5(src.read_bytes()).digest() == hashlib.md5(dst.read_bytes()).digest():
        return False
    shutil.copy2(src, dst)
    return True


def main() -> None:
    changed = []
    for name in ROOT_FILES:
        src = WEB / name
        if src.exists() and _sync(src, DOCS / name):
            changed.append(name)
    for sub, exts in (("data", {".json", ".csv", ".txt"}), ("timeline", {".jsonl"})):
        src_dir = WEB / sub
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.iterdir()):
            if src.suffix in exts and _sync(src, DOCS / sub / src.name):
                changed.append(f"{sub}/{src.name}")
    if changed:
        print(f"[sync_docs] {len(changed)} file(s) updated:")
        for f in changed:
            print(f"  {f}")
    else:
        print("[sync_docs] docs/ already up to date")


if __name__ == "__main__":
    main()
