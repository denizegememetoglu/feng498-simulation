"""Export web/index.html's final rendered rack layout to output/viewer_layout_v1.json.

Replicates the JS logic in web/index.html:166-253 in Python so the file is
reproducible from CLI and CI:
  * VIEWER_RACK_MODEL (web/index.html:166-183) — codex_idx -> letter/role/label
  * applyPdfSmallRackFootprint (lines 190-202) — H/I clamped to 11x280cm
  * PDF_BAY_OVERRIDES (lines 207-216) + applyPdfBayOverride (218-241)
  * LEVEL_HEIGHTS_CM (lines 376-384) — per-letter beam heights

Output schema: see plan AD-1. Read-only against config/layout.json.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEOMETRY_PATH = ROOT / "output" / "dwg_codex_geometry.json"
OUTPUT_PATH = ROOT / "output" / "viewer_layout_v1.json"

# web/index.html:166-183 — authoritative idx -> letter/role/label
VIEWER_RACK_MODEL: dict[int, dict] = {
    0:  {"letter": "J",  "label": False, "role": "j-fragment"},
    1:  {"letter": None, "label": False, "role": "unmapped-trash-side-stub"},
    2:  {"letter": "J",  "label": False, "role": "j-south-arm"},
    3:  {"letter": "I",  "label": True,  "role": "small"},
    4:  {"letter": "H",  "label": True,  "role": "small"},
    5:  {"letter": "G",  "label": True,  "role": "normal"},
    6:  {"letter": "F",  "label": True,  "role": "normal"},
    7:  {"letter": "E",  "label": True,  "role": "normal"},
    8:  {"letter": "D",  "label": True,  "role": "normal"},
    9:  {"letter": "C",  "label": True,  "role": "normal"},
    10: {"letter": "B",  "label": True,  "role": "normal"},
    11: {"letter": "A",  "label": True,  "role": "normal"},
    12: {"letter": "U",  "label": True,  "role": "perpendicular"},
    13: {"letter": "J",  "label": False, "role": "j-fragment"},
    14: {"letter": None, "label": False, "role": "unmapped-post"},
    15: {"letter": "J",  "label": False, "role": "j-east-vertical"},
}

# web/index.html:207-216
PDF_BAY_OVERRIDES: dict[int, dict] = {
    5:  {"bays": 12, "anchor": "east"},   # G
    6:  {"bays": 12, "anchor": "east"},   # F
    7:  {"bays": 12, "anchor": "east"},   # E (drop 2 stubs)
    8:  {"bays": 12, "anchor": "east"},   # D
    9:  {"bays": 12, "anchor": "east"},   # C
    10: {"bays": 11, "anchor": "east"},   # B
    11: {"bays": 11, "anchor": "east"},   # A
    12: {"bays": 14, "anchor": "y"},      # U vertical
}

# web/index.html:376-384
LEVEL_HEIGHTS_CM: dict[str, list[int]] = {
    "A": [61, 136, 206, 291, 376, 461, 546, 631, 700],
    "B": [61, 136, 206, 291, 376, 461, 546, 631, 700],
    "C": [61, 136, 206, 291, 376, 461, 546, 631, 700],
    "D": [61, 136, 204, 291, 376, 461, 546, 631, 700],
    "E": [61, 136, 206, 291, 376, 461, 546, 631, 700],
    "F": [61, 136, 206, 291, 376, 461, 546, 631, 700],
    "G": [61, 136, 206, 291, 376, 461, 546],
    "H": [61, 136, 206, 322, 438, 554, 700],
    "I": [61, 136, 206, 322, 438, 554, 670, 700],
    "J": [61, 136, 206, 322, 438, 554, 670, 700],
    "U": [118, 222, 346, 455, 564, 676, 700],
}
LEVEL_HEIGHTS_DEFAULT = [61, 136, 206, 291, 376, 461, 546, 631, 700]

SMALL_PDF_BAYS = 11
SMALL_PDF_SPAN_CM = 3080  # 11 * 280
DEFAULT_BAY_PITCH_CM = 280.0


def apply_small_footprint(row: dict) -> None:
    """Mirror of web/index.html:190-202 applyPdfSmallRackFootprint."""
    if row["dir"] != "x":
        return
    x_end = max(row["x0"], row["x1"])
    x_start = x_end - SMALL_PDF_SPAN_CM
    row["x0"] = x_start
    row["x1"] = x_end
    row["bays"] = SMALL_PDF_BAYS
    pitch = SMALL_PDF_SPAN_CM / SMALL_PDF_BAYS
    row["posts"] = [round(x_start + pitch * i, 2) for i in range(SMALL_PDF_BAYS + 1)]


def apply_bay_override(row: dict, spec: dict) -> None:
    """Mirror of web/index.html:218-241 applyPdfBayOverride."""
    if spec["anchor"] == "y":
        y_start = min(row["y0"], row["y1"])
        y_end = max(row["y0"], row["y1"])
        span = y_end - y_start
        row["bays"] = spec["bays"]
        row["posts"] = [
            round(y_start + (span / spec["bays"]) * i, 2)
            for i in range(spec["bays"] + 1)
        ]
    else:
        # east-anchor horizontal: BAY_PITCH = 280 cm
        x_end = max(row["x0"], row["x1"])
        x_start = x_end - spec["bays"] * DEFAULT_BAY_PITCH_CM
        row["x0"] = x_start
        row["x1"] = x_end
        row["bays"] = spec["bays"]
        row["posts"] = [
            round(x_start + DEFAULT_BAY_PITCH_CM * i, 2)
            for i in range(spec["bays"] + 1)
        ]


def compute_bay_pitch_cm(row: dict) -> float:
    """Derive pitch from posts (or x-span / bays for raw rows)."""
    posts = row.get("posts") or []
    if len(posts) >= 2:
        # Uniform-pitch racks: take the average of consecutive deltas.
        deltas = [posts[i + 1] - posts[i] for i in range(len(posts) - 1)]
        return round(sum(deltas) / len(deltas), 2)
    span_axis = "x" if row["dir"] == "x" else "y"
    span = abs(row[f"{span_axis}1"] - row[f"{span_axis}0"])
    bays = max(row["bays"], 1)
    return round(span / bays, 2)


def main() -> None:
    if not GEOMETRY_PATH.exists():
        raise SystemExit(f"FATAL: {GEOMETRY_PATH} not found")
    with open(GEOMETRY_PATH, encoding="utf-8") as fh:
        geom = json.load(fh)

    racks: list[dict] = []
    for raw in geom["rack_rows"]:
        row = {
            "codex_idx": raw["codex_idx"],
            "dir": raw["dir"],
            "x0": raw["x0"], "x1": raw["x1"],
            "y0": raw["y0"], "y1": raw["y1"],
            "bays": raw["bays"],
            "posts": list(raw.get("posts", [])),
        }
        semantic = VIEWER_RACK_MODEL.get(row["codex_idx"])
        if semantic is None:
            raise SystemExit(f"FATAL: codex_idx {row['codex_idx']} missing from VIEWER_RACK_MODEL")
        letter = semantic["letter"]
        role = semantic["role"]
        label = semantic["label"]
        if role == "small":
            apply_small_footprint(row)
        if row["codex_idx"] in PDF_BAY_OVERRIDES:
            apply_bay_override(row, PDF_BAY_OVERRIDES[row["codex_idx"]])

        rack = {
            "codex_idx": row["codex_idx"],
            "letter": letter,
            "role": role,
            "label": label,
            "skip": letter is None,
            "dir": row["dir"],
            "x0": row["x0"], "x1": row["x1"],
            "y0": row["y0"], "y1": row["y1"],
            "bays": row["bays"],
            "bay_pitch_cm": compute_bay_pitch_cm(row),
            "posts": row["posts"],
            "level_heights_cm": LEVEL_HEIGHTS_CM.get(letter, LEVEL_HEIGHTS_DEFAULT) if letter else [],
        }
        racks.append(rack)

    floor_labels = [dict(lbl) for lbl in geom.get("labels", [])]
    special_objects = [dict(obj) for obj in geom.get("special_objects", [])]

    payload = {
        "schema_version": "1.0",
        "_source": "web/index.html VIEWER_RACK_MODEL + PDF_BAY_OVERRIDES applied to output/dwg_codex_geometry.json",
        "_provenance": "scripts/export_viewer_layout.py — replicates web/index.html:166-253",
        "_unit": "cm",
        "_axes": "codex CAD: x increases east, y increases north",
        "_rack_height_cm": geom.get("_rack_height_cm", 700),
        "_rack_levels_m_default": geom.get("_rack_levels_m"),
        "_bounds": geom.get("_bounds"),
        "_viewer_model": {
            "VIEWER_RACK_MODEL": {str(k): v for k, v in VIEWER_RACK_MODEL.items()},
            "PDF_BAY_OVERRIDES": {str(k): v for k, v in PDF_BAY_OVERRIDES.items()},
            "small_footprint_pdf_bays": SMALL_PDF_BAYS,
            "small_footprint_span_cm": SMALL_PDF_SPAN_CM,
            "default_bay_pitch_cm": DEFAULT_BAY_PITCH_CM,
        },
        "racks": racks,
        "floor_labels": floor_labels,
        "special_objects": special_objects,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size:,} bytes)")
    print(f"  racks={len(racks)}  letter-bearing={sum(1 for r in racks if r['letter'])}")
    print(f"  total bays (letter-bearing)={sum(r['bays'] for r in racks if r['letter'])}")
    for r in racks:
        if not r["letter"]:
            continue
        if len(r["posts"]) != r["bays"] + 1:
            print(f"  WARN idx={r['codex_idx']} letter={r['letter']}: posts={len(r['posts'])} bays+1={r['bays']+1}")


if __name__ == "__main__":
    main()
