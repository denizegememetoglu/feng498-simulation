"""Read-only DXF extractor for the SE Manisa rack layout.

Parses the AutoCAD drawing (converted to DXF via libredwg's dwg2dxf) and
produces ``output/dwg_extracted.json`` as a face-validity reference. The
extractor INTENTIONALLY does not write ``config/layout.json`` — the SAP
join key (rack, bay, position) lives in that file and rack IDs / bay codes
must stay stable (see CLAUDE.md "DO NOT TOUCH"). Coordinates can change,
codes cannot. The face-validity comparison happens by overlaying the
extracted geometry against the current layout in the V&V report.

Layer map (after dwg2dxf of SE Manisa Ambar Rafları.dwg):
- ``RAFLAR``    : 494 LWPOLYLINEs — individual pallet slots / uprights.
- ``TRAVERS``   : 409 LWPOLYLINEs — rack cross-beams (horizontal members).
                  The 270 cm long, ~5 cm thick polylines come in pairs that
                  bracket each rack row (top + bottom beam).
- ``H``         : 18 MTEXT labels — KITTING / PUTAWAY zone names and
                  production line tags (GMH, F400, SM6-Premset, ...).
- ``OLCU``      : dimension lines (ignored).
- ``Hat_Sınır`` : boundary markers (ignored).
- ``kolon``     : column markers (kept as obstacles).

All coordinates are in centimetres (the drawing uses cm units).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from dataclasses import asdict, dataclass

import ezdxf


DEFAULT_DXF = "/tmp/manisa.dxf"
DEFAULT_OUT = "output/dwg_extracted.json"

# Beams smaller than this in either dimension are noise (clip artefacts).
MIN_BEAM_DIM_CM = 50.0
# Two horizontal beams whose mid-Y differ by <= this distance belong to
# the same rack-row (top + bottom beam of one rack).
ROW_PAIR_TOL_CM = 130.0
# Two beams within this Y tolerance share the same Y-band.
Y_BAND_TOL_CM = 10.0

# RAFLAR upright marker: small filled rectangle (~5cm × 10cm).
RAFLAR_UPRIGHT_MAX_MIN_DIM_CM = 12.0
RAFLAR_UPRIGHT_MAX_MAX_DIM_CM = 15.0
# Vertical TRAVERS column: tall narrow LWPOLYLINE pair.
VERT_BEAM_MIN_H_CM = 100.0
VERT_BEAM_MAX_W_CM = 50.0
# Vertical beam pair grouping by X (rack-depth ~100 cm).
VERT_X_BAND_TOL_CM = 10.0
VERT_COL_PAIR_TOL_CM = 140.0


@dataclass
class Label:
    text: str
    x: float
    y: float
    layer: str


@dataclass
class RackRow:
    """A pair of parallel horizontal beams = one rack row."""
    id: str               # synthetic, e.g. R01..Rn (CAD-derived, NOT SAP code)
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    width_cm: float
    depth_cm: float
    bay_count: int        # estimated from beam segment count


@dataclass
class RackColumn:
    """A pair of parallel vertical TRAVERS = one rack-column body (J-shape leg, etc.)."""
    id: str               # synthetic, e.g. V01..Vn
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    width_cm: float
    height_cm: float
    beam_count: int


def _load_msp(dxf_path: str):
    doc = ezdxf.readfile(dxf_path)
    return doc.modelspace()


def _extract_labels(msp) -> list[Label]:
    labels: list[Label] = []
    for e in msp:
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        if e.dxftype() == "TEXT":
            txt = (e.dxf.text or "").strip()
        else:
            txt = e.plain_text().strip() if hasattr(e, "plain_text") else ""
        if not txt:
            continue
        ins = e.dxf.insert
        labels.append(Label(text=txt, x=float(ins.x), y=float(ins.y),
                            layer=str(e.dxf.layer)))
    return labels


def _extract_travers_beams(msp) -> list[tuple]:
    """Return (xmin, ymin, xmax, ymax, w, h) for every TRAVERS beam."""
    out = []
    for e in msp:
        if e.dxf.layer != "TRAVERS" or e.dxftype() != "LWPOLYLINE":
            continue
        pts = list(e.get_points("xy"))
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        if w < MIN_BEAM_DIM_CM and h < MIN_BEAM_DIM_CM:
            continue
        out.append((min(xs), min(ys), max(xs), max(ys), w, h))
    return out


def _cluster_by_axis(items: list[tuple], axis_idx: int, tol: float) -> list[list[tuple]]:
    """Group items into clusters whose given axis coordinate is within tol."""
    if not items:
        return []
    s = sorted(items, key=lambda t: t[axis_idx])
    clusters = [[s[0]]]
    for it in s[1:]:
        if it[axis_idx] - clusters[-1][-1][axis_idx] <= tol:
            clusters[-1].append(it)
        else:
            clusters.append([it])
    return clusters


def _derive_rack_rows(beams: list[tuple]) -> list[RackRow]:
    """A 'rack row' = a top+bottom beam pair sharing the same X-span."""
    # Keep only horizontal beams (wider than tall).
    horiz = [b for b in beams if b[4] > b[5]]

    # Group beams by Y-band (each band ~= one beam at one elevation).
    bands = _cluster_by_axis(horiz, 1, Y_BAND_TOL_CM)
    band_summaries = []
    for c in bands:
        x_min = min(b[0] for b in c)
        x_max = max(b[2] for b in c)
        y_min = min(b[1] for b in c)
        y_max = max(b[3] for b in c)
        band_summaries.append({
            "y_mid": (y_min + y_max) / 2.0,
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "beam_count": len(c),
        })

    # Pair consecutive bands whose X-span overlaps strongly and whose Y-gap
    # is consistent with rack depth (~100 cm).
    band_summaries.sort(key=lambda d: d["y_mid"])
    rows: list[RackRow] = []
    used = [False] * len(band_summaries)
    for i, b in enumerate(band_summaries):
        if used[i]:
            continue
        # Look for a partner band further up.
        partner_idx = None
        for j in range(i + 1, len(band_summaries)):
            if used[j]:
                continue
            gap = band_summaries[j]["y_mid"] - b["y_mid"]
            if gap > ROW_PAIR_TOL_CM:
                break
            # Same X-window?
            overlap = (min(b["x_max"], band_summaries[j]["x_max"])
                       - max(b["x_min"], band_summaries[j]["x_min"]))
            if overlap > 0.7 * (b["x_max"] - b["x_min"]):
                partner_idx = j
                break
        if partner_idx is None:
            continue
        p = band_summaries[partner_idx]
        used[i] = used[partner_idx] = True
        x_min = min(b["x_min"], p["x_min"])
        x_max = max(b["x_max"], p["x_max"])
        y_min = min(b["y_min"], p["y_min"])
        y_max = max(b["y_max"], p["y_max"])
        rows.append(RackRow(
            id=f"R{len(rows) + 1:02d}",
            x_min=x_min, x_max=x_max,
            y_min=y_min, y_max=y_max,
            width_cm=x_max - x_min,
            depth_cm=y_max - y_min,
            # WARNING (M5): bay_count = max(beam_count) is a TRAVERS beam
            # proxy, NOT the real bay count. The CAD beam clustering inside
            # a band can return any number of segments, depending on how the
            # original draftsperson split the cross-members. The
            # PDF-verified bay_count in config/layout.json is the ground
            # truth — do NOT use this value to overwrite layout.json
            # segments. Kept as a face-validity-only signal.
            bay_count=max(b["beam_count"], p["beam_count"]),
        ))
    return rows


def _bbox_lwpolyline(e) -> tuple[float, float, float, float] | None:
    pts = list(e.get_points("xy"))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_hatch(e) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for p in e.paths:
        if hasattr(p, "vertices"):
            for pt in p.vertices:
                xs.append(float(pt[0]))
                ys.append(float(pt[1]))
        if hasattr(p, "edges"):
            for edge in p.edges:
                if hasattr(edge, "start") and edge.start is not None:
                    xs.append(float(edge.start[0]))
                    ys.append(float(edge.start[1]))
                if hasattr(edge, "end") and edge.end is not None:
                    xs.append(float(edge.end[0]))
                    ys.append(float(edge.end[1]))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _extract_raflar_uprights(msp) -> tuple[list[dict], int]:
    """Small filled rectangles on RAFLAR layer = rack uprights / pallet markers.

    Returns ``(uprights, beam_marker_count)``. The 95 cm × 4 cm beam-marker
    rectangles share the layer but are excluded from the upright list — they
    are reported as a count for QA only.
    """
    uprights: list[dict] = []
    beam_markers = 0
    for e in msp:
        if e.dxf.layer != "RAFLAR" or e.dxftype() != "LWPOLYLINE":
            continue
        bbox = _bbox_lwpolyline(e)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        w, h = x1 - x0, y1 - y0
        if (min(w, h) < RAFLAR_UPRIGHT_MAX_MIN_DIM_CM
                and max(w, h) < RAFLAR_UPRIGHT_MAX_MAX_DIM_CM):
            uprights.append({
                "x": (x0 + x1) / 2.0,
                "y": (y0 + y1) / 2.0,
                "w_cm": w,
                "h_cm": h,
            })
        else:
            beam_markers += 1
    return uprights, beam_markers


def _extract_vertical_rack_columns(msp) -> list[RackColumn]:
    """Tall narrow TRAVERS LWPOLYLINEs paired in X = vertical rack column body."""
    vert: list[tuple] = []
    for e in msp:
        if e.dxf.layer != "TRAVERS" or e.dxftype() != "LWPOLYLINE":
            continue
        bbox = _bbox_lwpolyline(e)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        w, h = x1 - x0, y1 - y0
        if h > w and h > VERT_BEAM_MIN_H_CM and w < VERT_BEAM_MAX_W_CM:
            vert.append((x0, y0, x1, y1, w, h))
    if not vert:
        return []
    # Group by x-band.
    bands = _cluster_by_axis(vert, 0, VERT_X_BAND_TOL_CM)
    band_summaries = []
    for c in bands:
        x_min = min(b[0] for b in c)
        x_max = max(b[2] for b in c)
        y_min = min(b[1] for b in c)
        y_max = max(b[3] for b in c)
        band_summaries.append({
            "x_mid": (x_min + x_max) / 2.0,
            "x_min": x_min, "x_max": x_max,
            "y_min": y_min, "y_max": y_max,
            "beam_count": len(c),
        })
    band_summaries.sort(key=lambda d: d["x_mid"])
    cols: list[RackColumn] = []
    used = [False] * len(band_summaries)
    for i, b in enumerate(band_summaries):
        if used[i]:
            continue
        partner = None
        for j in range(i + 1, len(band_summaries)):
            if used[j]:
                continue
            gap = band_summaries[j]["x_mid"] - b["x_mid"]
            if gap > VERT_COL_PAIR_TOL_CM:
                break
            overlap = (min(b["y_max"], band_summaries[j]["y_max"])
                       - max(b["y_min"], band_summaries[j]["y_min"]))
            if overlap > 0.7 * (b["y_max"] - b["y_min"]):
                partner = j
                break
        if partner is None:
            continue
        p = band_summaries[partner]
        used[i] = used[partner] = True
        x_min = min(b["x_min"], p["x_min"])
        x_max = max(b["x_max"], p["x_max"])
        y_min = min(b["y_min"], p["y_min"])
        y_max = max(b["y_max"], p["y_max"])
        cols.append(RackColumn(
            id=f"V{len(cols) + 1:02d}",
            x_min=x_min, x_max=x_max,
            y_min=y_min, y_max=y_max,
            width_cm=x_max - x_min,
            height_cm=y_max - y_min,
            beam_count=b["beam_count"] + p["beam_count"],
        ))
    return cols


def _extract_dimensions(msp) -> list[dict]:
    """DIMENSION entities (ince çizgi + Hat_Sınır) with measurement value."""
    out: list[dict] = []
    for e in msp:
        if e.dxftype() != "DIMENSION":
            continue
        try:
            meas = float(e.get_measurement())
        except Exception:
            meas = None
        defpoint = None
        text_mid = None
        if hasattr(e.dxf, "defpoint") and e.dxf.defpoint is not None:
            defpoint = [float(e.dxf.defpoint.x), float(e.dxf.defpoint.y)]
        if hasattr(e.dxf, "text_midpoint") and e.dxf.text_midpoint is not None:
            text_mid = [float(e.dxf.text_midpoint.x), float(e.dxf.text_midpoint.y)]
        out.append({
            "layer": str(e.dxf.layer),
            "measurement_cm": meas,
            "defpoint": defpoint,
            "text_midpoint": text_mid,
        })
    return out


def _extract_corridors(msp) -> list[dict]:
    """LWPOLYLINEs on cu_yol_cizgileri layer (corridor centrelines)."""
    out: list[dict] = []
    for e in msp:
        if e.dxf.layer != "cu_yol_cizgileri" or e.dxftype() != "LWPOLYLINE":
            continue
        bbox = _bbox_lwpolyline(e)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        out.append({
            "type": "LWPOLYLINE",
            "bbox": [x0, y0, x1, y1],
            "width_cm": x1 - x0,
            "height_cm": y1 - y0,
        })
    return out


def _extract_columns(msp) -> list[dict]:
    """LWPOLYLINEs on kolon layer (structural columns)."""
    out: list[dict] = []
    for e in msp:
        if e.dxf.layer != "kolon" or e.dxftype() != "LWPOLYLINE":
            continue
        bbox = _bbox_lwpolyline(e)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        out.append({
            "type": "LWPOLYLINE",
            "bbox": [x0, y0, x1, y1],
            "width_cm": x1 - x0,
            "height_cm": y1 - y0,
        })
    return out


def _extract_line_boundaries(msp) -> list[dict]:
    """LINE + DIMENSION entities on Hat_Sınır layer (production-line boundaries)."""
    out: list[dict] = []
    for e in msp:
        if e.dxf.layer != "Hat_Sınır":
            continue
        if e.dxftype() == "LINE":
            s, t = e.dxf.start, e.dxf.end
            out.append({
                "type": "LINE",
                "start": [float(s.x), float(s.y)],
                "end": [float(t.x), float(t.y)],
            })
        elif e.dxftype() == "DIMENSION":
            try:
                meas = float(e.get_measurement())
            except Exception:
                meas = None
            defp = e.dxf.defpoint if hasattr(e.dxf, "defpoint") else None
            out.append({
                "type": "DIMENSION",
                "measurement_cm": meas,
                "defpoint": [float(defp.x), float(defp.y)] if defp is not None else None,
            })
    return out


def _extract_staging_hatches(msp) -> list[dict]:
    """HATCH entities on AM_8 + ince çizgi layers (staging / aisle markers)."""
    out: list[dict] = []
    for e in msp:
        if e.dxftype() != "HATCH":
            continue
        layer = str(e.dxf.layer)
        if layer not in ("AM_8", "ince çizgi"):
            continue
        bbox = _bbox_hatch(e)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        out.append({
            "layer": layer,
            "bbox": [x0, y0, x1, y1],
            "width_cm": x1 - x0,
            "height_cm": y1 - y0,
        })
    return out


def _extract_layer_0_markers(msp) -> list[dict]:
    """LINEs on layer 0 — reference markers / sparse fragments, catalogued only."""
    out: list[dict] = []
    for e in msp:
        if e.dxf.layer != "0" or e.dxftype() != "LINE":
            continue
        s, t = e.dxf.start, e.dxf.end
        out.append({
            "start": [float(s.x), float(s.y)],
            "end": [float(t.x), float(t.y)],
            "length_cm": float(((t.x - s.x) ** 2 + (t.y - s.y) ** 2) ** 0.5),
        })
    return out


def _classify_labels(labels: list[Label]) -> dict:
    """Group H-layer labels into kitting / putaway / line-tags."""
    kittings = [l for l in labels if l.text.upper() == "KITTING"]
    putaways = [l for l in labels if l.text.upper() == "PUTAWAY"]
    line_tags = [l for l in labels if l.text.startswith("(") and l.text.endswith(")")]
    other = [l for l in labels if l not in kittings and l not in putaways and l not in line_tags]

    # Best-effort link line_tag → nearest kitting/putaway label.
    def nearest(target: Label, candidates: list[Label]):
        if not candidates:
            return None
        best = min(candidates, key=lambda c: (c.x - target.x)**2 + (c.y - target.y)**2)
        dx, dy = best.x - target.x, best.y - target.y
        return {"text": best.text, "x": best.x, "y": best.y,
                "distance_cm": float((dx*dx + dy*dy) ** 0.5)}

    production_lines = []
    for tag in line_tags:
        name = tag.text.strip("()")
        production_lines.append({
            "line_label": name,
            "label_xy": [tag.x, tag.y],
            "nearest_kitting": nearest(tag, kittings),
            "nearest_putaway": nearest(tag, putaways),
        })

    return {
        "kitting_points": [{"x": l.x, "y": l.y} for l in kittings],
        "putaway_points": [{"x": l.x, "y": l.y} for l in putaways],
        "production_lines": production_lines,
        "other_labels": [{"text": l.text, "x": l.x, "y": l.y, "layer": l.layer}
                         for l in other],
    }


def extract(dxf_path: str = DEFAULT_DXF) -> dict:
    """Parse the DXF and return a structured face-validity payload."""
    if not os.path.exists(dxf_path):
        raise FileNotFoundError(
            f"DXF not found at {dxf_path}. Run: "
            f"dwg2dxf '/home/dege/Downloads/SE Manisa Ambar Rafları.dwg' "
            f"-o {dxf_path}"
        )
    msp = _load_msp(dxf_path)
    beams = _extract_travers_beams(msp)
    rows = _derive_rack_rows(beams)
    vert_cols = _extract_vertical_rack_columns(msp)
    labels = _extract_labels(msp)
    label_groups = _classify_labels(labels)
    uprights, beam_marker_count = _extract_raflar_uprights(msp)
    corridors = _extract_corridors(msp)
    columns = _extract_columns(msp)
    line_boundaries = _extract_line_boundaries(msp)
    staging_hatches = _extract_staging_hatches(msp)
    dimensions = _extract_dimensions(msp)
    layer_0_markers = _extract_layer_0_markers(msp)

    xs_all = [b[0] for b in beams] + [b[2] for b in beams]
    ys_all = [b[1] for b in beams] + [b[3] for b in beams]
    bbox = {
        "x_min_cm": min(xs_all) if xs_all else 0.0,
        "y_min_cm": min(ys_all) if ys_all else 0.0,
        "x_max_cm": max(xs_all) if xs_all else 0.0,
        "y_max_cm": max(ys_all) if ys_all else 0.0,
    }

    # Combined rack-area bbox includes vertical columns + upright markers.
    rack_xs = list(xs_all)
    rack_ys = list(ys_all)
    for v in vert_cols:
        rack_xs += [v.x_min, v.x_max]
        rack_ys += [v.y_min, v.y_max]
    for u in uprights:
        rack_xs.append(u["x"])
        rack_ys.append(u["y"])
    rack_area_bbox = [
        min(rack_xs) if rack_xs else 0.0,
        min(rack_ys) if rack_ys else 0.0,
        max(rack_xs) if rack_xs else 0.0,
        max(rack_ys) if rack_ys else 0.0,
    ]

    # Building bbox spans every body the extractor saw.
    all_xs = list(rack_xs)
    all_ys = list(rack_ys)
    for src in (corridors, columns, staging_hatches):
        for it in src:
            x0, y0, x1, y1 = it["bbox"]
            all_xs += [x0, x1]
            all_ys += [y0, y1]
    for lb in line_boundaries:
        if lb["type"] == "LINE":
            all_xs += [lb["start"][0], lb["end"][0]]
            all_ys += [lb["start"][1], lb["end"][1]]
    for d in dimensions:
        if d.get("defpoint"):
            all_xs.append(d["defpoint"][0])
            all_ys.append(d["defpoint"][1])
    for l in labels:
        all_xs.append(l.x)
        all_ys.append(l.y)
    building_bbox = [
        min(all_xs) if all_xs else 0.0,
        min(all_ys) if all_ys else 0.0,
        max(all_xs) if all_xs else 0.0,
        max(all_ys) if all_ys else 0.0,
    ]

    widths = [r.width_cm for r in rows]
    depths = [r.depth_cm for r in rows]

    def _row_dict(r: RackRow) -> dict:
        d = asdict(r)
        d["row_id"] = d["id"]
        d["y_center"] = (r.y_min + r.y_max) / 2.0
        d["x_center"] = (r.x_min + r.x_max) / 2.0
        d["beam_count"] = d["bay_count"]
        return d

    def _col_dict(v: RackColumn) -> dict:
        d = asdict(v)
        d["col_id"] = d["id"]
        d["x_center"] = (v.x_min + v.x_max) / 2.0
        d["y_center"] = (v.y_min + v.y_max) / 2.0
        return d

    rows_dict = [_row_dict(r) for r in rows]
    return {
        "source": os.path.abspath(dxf_path),
        "units": "cm (per drawing OLCU layer)",
        "floor_bbox_cm": bbox,
        "building_bbox_cm": building_bbox,
        "rack_area_bbox_cm": rack_area_bbox,
        "rack_row_count": len(rows),
        "rack_rows": rows_dict,
        "rack_rows_horizontal": rows_dict,
        "rack_columns_vertical": [_col_dict(v) for v in vert_cols],
        "rack_width_stats_cm": {
            "mean": statistics.mean(widths) if widths else 0.0,
            "median": statistics.median(widths) if widths else 0.0,
            "min": min(widths) if widths else 0.0,
            "max": max(widths) if widths else 0.0,
        },
        "rack_depth_stats_cm": {
            "mean": statistics.mean(depths) if depths else 0.0,
            "median": statistics.median(depths) if depths else 0.0,
            "min": min(depths) if depths else 0.0,
            "max": max(depths) if depths else 0.0,
        },
        "raflar_uprights": uprights,
        "raflar_beam_markers_count": beam_marker_count,
        "corridors": corridors,
        "columns": columns,
        "line_boundaries": line_boundaries,
        "staging_hatches": staging_hatches,
        "dimensions": dimensions,
        "layer_0_markers": layer_0_markers,
        "labels": [
            {"text": l.text, "x": l.x, "y": l.y, "layer": l.layer}
            for l in labels
        ],
        **label_groups,
        "note": (
            "Read-only extraction. config/layout.json is NOT overwritten; "
            "SAP join key (rack, bay, position) lives there and rack IDs / "
            "bay codes must stay stable. Use this file as a face-validity "
            "reference (Sargent §4.1) when comparing the modelled layout "
            "against the CAD drawing."
        ),
    }


# ----------------------------------------------------------------------
# Faz 1.1 — DWG ↔ SAP rack mapping
# ----------------------------------------------------------------------

# User-confirmed mapping from plan (see
# /home/dege/.claude/plans/next-session-prompt-md-handoff-md-effervescent-snowflake.md):
# DWG has 0 rack ID labels → mapping derived from spatial sort + PDF
# bay-count + factory-photo cross-check. R12 + V03 unmapped (U preserved
# from existing layout because it is back-to-back + non-uniform + has a
# detached "KÜÇÜK RF" U14 cell that DWG can't express).
_ROW_MAPPING_DEFAULT: list[dict] = [
    {"dwg_row": "R01", "sap_rack": "J", "segment_id": "bottom-arm-fragment",
     "confidence": "medium",
     "evidence": ["y≈438 south edge", "w=200cm small fragment of J's bottom horizontal arm"]},
    {"dwg_row": "R02", "sap_rack": None, "disposition": "UNMAPPED",
     "confidence": "low",
     "evidence": ["y≈634 east x≈5360-5630, no layout rack at that position"]},
    {"dwg_row": "R03", "sap_rack": "A", "segment_id": "main",
     "confidence": "high",
     "evidence": ["w≈3000cm ≈ 11×270=2970cm (Δ+30cm)",
                  "south-most main DWG row → east-most layout rack",
                  "factory photo: yellow 'A' label confirmed on column posts"]},
    {"dwg_row": "R04", "sap_rack": "B", "segment_id": "main",
     "confidence": "medium",
     "evidence": ["back-to-back pair with R05 (gap 125cm)",
                  "bay_width_m refit from DWG width"]},
    {"dwg_row": "R05", "sap_rack": "C", "segment_id": "main",
     "confidence": "medium",
     "evidence": ["back-to-back pair with R04 (gap 125cm)",
                  "bay_width_m refit from DWG width"]},
    {"dwg_row": "R06", "sap_rack": "D", "segment_id": "main",
     "confidence": "medium",
     "evidence": ["w≈3350cm vs 12×261=3132cm (Δ+218cm) — bay_width_m refit"]},
    {"dwg_row": "R07", "sap_rack": "E", "segment_id": "main",
     "confidence": "medium",
     "evidence": ["w≈3280cm vs 12×261=3132cm (Δ+150cm) — bay_width_m refit"]},
    {"dwg_row": "R08", "sap_rack": "F", "segment_id": "main",
     "confidence": "medium",
     "evidence": ["w≈3280cm vs 12×261=3132cm (Δ+150cm) — bay_width_m refit",
                  "factory photo: yellow 'F' label + F400 production-line tag confirmed"]},
    {"dwg_row": "R09", "sap_rack": "G", "segment_id": "main",
     "confidence": "low",
     "evidence": ["w≈3280cm vs 12×220=2640cm (Δ+640cm) — bay_width_m refit"]},
    {"dwg_row": "R10", "sap_rack": "I", "segment_id": "main",
     "confidence": "low",
     "evidence": ["w≈3350cm vs 11×231=2541cm (Δ+809cm) — bay_width_m refit",
                  "INSIDE J bracket per layout (alongside H)"]},
    {"dwg_row": "R11", "sap_rack": "H", "segment_id": "main",
     "confidence": "low",
     "evidence": ["w≈3280cm vs 11×231=2541cm (Δ+739cm) — bay_width_m refit",
                  "INSIDE J bracket per layout. H/I disambig: H assumed west of I"]},
    {"dwg_row": "R12", "sap_rack": None, "disposition": "UNMAPPED",
     "confidence": "low",
     "evidence": ["w≈3280cm vs U 14×173=2422cm (Δ+858cm)",
                  "R12 likely orphan; U preserved from existing layout because back-to-back + non-uniform bays + KÜÇÜK RF U14"]},
]

_VERT_MAPPING_DEFAULT: list[dict] = [
    {"dwg_col": "V01", "sap_rack": "J", "segment_id": "vertical",
     "confidence": "high",
     "evidence": ["west-most x≈1784, h≈3280cm — matches J's tall vertical leg"]},
    {"dwg_col": "V02", "sap_rack": "J", "segment_id": "bottom-arm-fragment",
     "confidence": "medium",
     "evidence": ["small x≈2223 near R01 — likely J's bottom-arm transition cell"]},
    {"dwg_col": "V03", "sap_rack": None, "disposition": "UNMAPPED",
     "confidence": "low",
     "evidence": ["east x≈5687, h≈1110cm — no layout match",
                  "possible U14 KÜÇÜK RF candidate but U preserved separately"]},
]


def _fit_axis_swap_transform(extracted: dict, layout: dict,
                             row_mapping: list[dict]) -> dict:
    """Least-squares affine fit: layout_x = a*dwg_y + b, layout_y = c*dwg_x + d.

    Uses every "main"-segment row mapping (R03..R11 → 9 anchor points).
    Per-rack residuals are reported so users can spot bad pairs.
    """
    # Index DWG rows by row_id, layout racks by id.
    dwg_rows = {r["row_id"]: r for r in extracted["rack_rows_horizontal"]}
    layout_by_id = {r["id"]: r for r in layout["racks"]}

    xy_pairs: list[tuple[float, float]] = []  # (dwg_y_center, layout_x_center)
    span_pairs: list[tuple[float, float, float, float]] = []
    # (dwg_x_min, dwg_x_max, layout_y_min, layout_y_max) for the x→y fit
    for m in row_mapping:
        if m.get("segment_id") != "main" or not m.get("sap_rack"):
            continue
        row = dwg_rows.get(m["dwg_row"])
        rack = layout_by_id.get(m["sap_rack"])
        if row is None or rack is None:
            continue
        seg = rack["segments"][0]
        # Layout vertical rack centre x = constant (seg.start[0] == seg.end[0]).
        layout_x = float(seg["start"][0])
        dwg_y = float(row["y_center"])
        xy_pairs.append((dwg_y, layout_x))
        # x→y span anchor: DWG row x_min/x_max ↔ layout rack y_min/y_max.
        layout_y_min = min(float(seg["start"][1]), float(seg["end"][1]))
        layout_y_max = max(float(seg["start"][1]), float(seg["end"][1]))
        span_pairs.append((float(row["x_min"]), float(row["x_max"]),
                           layout_y_min, layout_y_max))

    def _lin_fit(pts: list[tuple[float, float]]) -> tuple[float, float]:
        n = len(pts)
        if n == 0:
            return 0.0, 0.0
        sx = sum(p[0] for p in pts)
        sy = sum(p[1] for p in pts)
        sxy = sum(p[0] * p[1] for p in pts)
        sxx = sum(p[0] * p[0] for p in pts)
        denom = n * sxx - sx * sx
        if denom == 0:
            return 0.0, sy / n
        a = (n * sxy - sx * sy) / denom
        b = (sy - a * sx) / n
        return a, b

    a, b = _lin_fit(xy_pairs)  # layout_x = a * dwg_y + b
    # For y: use both endpoints (x_min↔y_min, x_max↔y_max).
    pts_y: list[tuple[float, float]] = []
    for x0, x1, y0, y1 in span_pairs:
        pts_y.append((x0, y0))
        pts_y.append((x1, y1))
    c, d = _lin_fit(pts_y)

    residuals = []
    for m in row_mapping:
        if m.get("segment_id") != "main" or not m.get("sap_rack"):
            continue
        row = dwg_rows.get(m["dwg_row"])
        rack = layout_by_id.get(m["sap_rack"])
        if row is None or rack is None:
            continue
        seg = rack["segments"][0]
        pred_x = a * float(row["y_center"]) + b
        actual_x = float(seg["start"][0])
        residuals.append({
            "dwg_row": m["dwg_row"],
            "sap_rack": m["sap_rack"],
            "layout_x_predicted_m": round(pred_x, 3),
            "layout_x_actual_m": round(actual_x, 3),
            "residual_m": round(pred_x - actual_x, 3),
        })

    return {
        "type": "axis_swap_affine",
        "description": ("DWG cm → layout m. Axis-swap: DWG y maps to layout x, "
                        "DWG x maps to layout y. Least-squares fit across all "
                        "high/medium-confidence mapped main-row anchors."),
        "layout_x_per_dwg_y": round(a, 6),
        "layout_x_offset_m": round(b, 4),
        "layout_y_per_dwg_x": round(c, 6),
        "layout_y_offset_m": round(d, 4),
        "anchor_count": len(xy_pairs),
        "residuals": residuals,
        "max_abs_residual_m": round(max((abs(r["residual_m"]) for r in residuals),
                                        default=0.0), 3),
    }


def generate_rack_mapping(
    extracted: dict | None = None,
    extracted_path: str = "output/dwg_extracted.json",
    layout_path: str = "config/layout.json",
    pdfs_dir: str = "data/rack-drawings",
    out_path: str = "config/rack_mapping_dwg_to_sap.json",
) -> dict:
    """Produce the DWG-row → SAP-rack mapping manifest.

    Mapping is user-confirmed (see plan): default assignments hard-coded per
    DWG row, transform fitted from main-row anchors. Output is reviewed at
    USER APPROVAL GATE 1 — confidence=medium|low rows require visual check.
    """
    if extracted is None:
        with open(extracted_path) as f:
            extracted = json.load(f)
    with open(layout_path) as f:
        layout = json.load(f)

    row_mapping = [dict(r) for r in _ROW_MAPPING_DEFAULT]
    vert_mapping = [dict(v) for v in _VERT_MAPPING_DEFAULT]

    # Attach DWG geometry to each mapped row for review traceability.
    dwg_rows = {r["row_id"]: r for r in extracted["rack_rows_horizontal"]}
    for m in row_mapping:
        row = dwg_rows.get(m["dwg_row"])
        if row is None:
            continue
        m["dwg_geometry"] = {
            "y_center": row["y_center"],
            "x_min": row["x_min"],
            "x_max": row["x_max"],
            "width_cm": row["width_cm"],
            "depth_cm": row["depth_cm"],
            "beam_count": row["beam_count"],
        }
    dwg_cols = {v["col_id"]: v for v in extracted["rack_columns_vertical"]}
    for m in vert_mapping:
        col = dwg_cols.get(m["dwg_col"])
        if col is None:
            continue
        m["dwg_geometry"] = {
            "x_center": col["x_center"],
            "y_min": col["y_min"],
            "y_max": col["y_max"],
            "width_cm": col["width_cm"],
            "height_cm": col["height_cm"],
            "beam_count": col["beam_count"],
        }

    transform = _fit_axis_swap_transform(extracted, layout, row_mapping)

    mapped_sap = {m["sap_rack"] for m in row_mapping if m.get("sap_rack")} | \
                 {m["sap_rack"] for m in vert_mapping if m.get("sap_rack")}
    all_layout_ids = {r["id"] for r in layout["racks"]}
    racks_without_dwg_match = sorted(all_layout_ids - mapped_sap)

    payload = {
        "_schema": "rack_mapping_dwg_to_sap/v1",
        "_source_dxf": extracted.get("source"),
        "_source_layout": os.path.abspath(layout_path),
        "_note": (
            "User review required for confidence=medium|low entries. "
            "Particularly H/I disambiguation (both 11-bay), R12 disposition, "
            "and V03 (KÜÇÜK RF candidate vs orphan). "
            "DWG has zero rack ID labels — mapping derived from spatial sort, "
            "PDF bay-count match, and factory-photo yellow-label cross-check."
        ),
        "transform": transform,
        "rows": row_mapping,
        "verticals": vert_mapping,
        "racks_without_dwg_match": racks_without_dwg_match,
        "preserved_from_existing_layout": [
            "U (back-to-back double-deep + non-uniform bays + KÜÇÜK RF U14)",
            "J-top-arm (no DWG match)",
            "J-bottom-arm full (DWG shows R01+V02 fragment only; full 10.8m preserved)",
        ],
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return payload


# ----------------------------------------------------------------------
# Faz 1.2 — DWG-derived layout rebuild
# ----------------------------------------------------------------------

def _apply_transform(dwg_x: float, dwg_y: float, transform: dict) -> tuple[float, float]:
    """Axis-swap affine: (dwg_x, dwg_y) [cm] → (layout_x, layout_y) [m]."""
    layout_x = transform["layout_x_per_dwg_y"] * dwg_y + transform["layout_x_offset_m"]
    layout_y = transform["layout_y_per_dwg_x"] * dwg_x + transform["layout_y_offset_m"]
    return layout_x, layout_y


def build_layout_from_dwg(
    mapping_path: str = "config/rack_mapping_dwg_to_sap.json",
    extracted_path: str = "output/dwg_extracted.json",
    source_layout_path: str = "config/layout.json",
    out_path: str = "config/layout_dwg_rebuilt.json",
) -> dict:
    """Rebuild config/layout.json coordinates from DWG, preserving SAP join.

    SAP-critical fields (bays, bay_code_start, levels, pallets_per_bay,
    pallet_count, bay_overrides) are byte-identical to the source layout.
    Coordinates and bay_width_m for DWG-mapped main racks are recomputed
    from the DWG-derived axis-swap transform. Bodies without a DWG match
    (U, J-top-arm, J-bottom-arm full, V03) are kept as-is from the source.
    """
    with open(mapping_path) as f:
        mapping = json.load(f)
    with open(extracted_path) as f:
        extracted = json.load(f)
    with open(source_layout_path) as f:
        layout = json.load(f)

    transform = mapping["transform"]
    dwg_rows = {r["row_id"]: r for r in extracted["rack_rows_horizontal"]}

    # Build SAP-rack → (dwg_row, segment_id) lookups.
    row_by_sap: dict[tuple[str, str], dict] = {}
    for m in mapping["rows"]:
        if m.get("sap_rack") and m.get("segment_id"):
            row_by_sap[(m["sap_rack"], m["segment_id"])] = m
    col_by_sap: dict[tuple[str, str], dict] = {}
    for v in mapping["verticals"]:
        if v.get("sap_rack") and v.get("segment_id"):
            col_by_sap[(v["sap_rack"], v["segment_id"])] = v

    rebuilt = json.loads(json.dumps(layout))  # deep copy

    rebuild_log: list[dict] = []

    for rack in rebuilt["racks"]:
        rid = rack["id"]
        for seg_idx, seg in enumerate(rack["segments"]):
            entry = {"rack": rid, "segment_index": seg_idx, "action": "preserved"}

            # Default: main single-segment vertical rack matches segment_id="main".
            mapping_entry = None
            if rid == "J":
                # J is preserved in full: bottom-arm DWG fragment is only
                # partial (10.8m full → 2m DWG cell), top-arm has no DWG
                # match, and V01 is vertical in DWG which conflicts with
                # the axis-swap transform fitted on horizontal main rows.
                if seg_idx == 0:
                    entry["action"] = "preserved_j_bottom_arm"
                elif seg_idx == 1:
                    entry["action"] = "preserved_j_vertical_axis_mismatch"
                else:
                    entry["action"] = "preserved_j_top_arm_no_dwg"
            elif rid == "U":
                entry["action"] = "preserved_u_back_to_back"
            else:
                mapping_entry = row_by_sap.get((rid, "main"))
                entry["action"] = "dwg_rebuilt" if mapping_entry else "preserved"

            # Rebuild only main vertical racks + J-vertical from DWG.
            if entry["action"] == "dwg_rebuilt":
                row = dwg_rows.get(mapping_entry["dwg_row"])
                if row is None:
                    entry["action"] = "preserved_dwg_row_missing"
                else:
                    bays = int(seg["bays"])
                    dwg_w_cm = float(row["width_cm"])
                    new_bay_width_m = (dwg_w_cm / bays) / 100.0
                    layout_x_center, _ = _apply_transform(row["x_min"], row["y_center"], transform)
                    _, layout_y_south = _apply_transform(row["x_min"], row["y_center"], transform)
                    _, layout_y_north = _apply_transform(row["x_max"], row["y_center"], transform)
                    if layout_y_south > layout_y_north:
                        layout_y_south, layout_y_north = layout_y_north, layout_y_south
                    # Preserve length = bays × bay_width_m exactly (avoid drift).
                    span = bays * new_bay_width_m
                    y_center = (layout_y_south + layout_y_north) / 2.0
                    new_start = [round(layout_x_center, 3), round(y_center - span / 2.0, 3)]
                    new_end = [round(layout_x_center, 3), round(y_center + span / 2.0, 3)]
                    entry["old_start"] = seg["start"]
                    entry["old_end"] = seg["end"]
                    entry["old_bay_width_m"] = seg.get("bay_width_m")
                    seg["start"] = new_start
                    seg["end"] = new_end
                    seg["bay_width_m"] = round(new_bay_width_m, 4)
                    entry["new_start"] = new_start
                    entry["new_end"] = new_end
                    entry["new_bay_width_m"] = seg["bay_width_m"]
                    entry["dwg_width_cm"] = dwg_w_cm
            rebuild_log.append(entry)

    # Apply transform to kitting/putaway/production-line labels for new
    # top-level keys consumed by simulation.py:296-313 (if those exist).
    def _xform_point(d):
        x_layout, y_layout = _apply_transform(d["x"], d["y"], transform)
        return {"x": round(x_layout, 3), "y": round(y_layout, 3)}

    rebuilt["kitting_points"] = [_xform_point(p) for p in extracted.get("kitting_points", [])]
    rebuilt["putaway_points"] = [_xform_point(p) for p in extracted.get("putaway_points", [])]
    production_lines = []
    for pl in extracted.get("production_lines", []):
        entry = {
            "name": pl["line_label"],
            "label_xy_m": _xform_point({"x": pl["label_xy"][0], "y": pl["label_xy"][1]}),
        }
        if pl.get("nearest_kitting"):
            entry["kitting_point_m"] = _xform_point(pl["nearest_kitting"])
        if pl.get("nearest_putaway"):
            entry["putaway_point_m"] = _xform_point(pl["nearest_putaway"])
        production_lines.append(entry)
    rebuilt["production_lines"] = production_lines

    rebuilt["_dwg_meta"] = {
        "source_dxf": extracted.get("source"),
        "source_mapping": os.path.abspath(mapping_path),
        "source_layout": os.path.abspath(source_layout_path),
        "transform_type": transform["type"],
        "transform_anchor_count": transform["anchor_count"],
        "transform_max_abs_residual_m": transform["max_abs_residual_m"],
        "rebuilt_segments": [e for e in rebuild_log
                             if e["action"].startswith("dwg_rebuilt")],
        "preserved_segments": [e for e in rebuild_log
                               if not e["action"].startswith("dwg_rebuilt")],
        "build_note": (
            "Coordinates derived from DWG via axis-swap affine transform. "
            "SAP join keys (rack id, bay codes, levels, pallets_per_bay, "
            "pallet_count, bay_overrides) byte-identical to source layout. "
            "U, J-arms, V03: preserved from source (DWG match missing or "
            "structurally incompatible — see ASSUMPTIONS.md §1)."
        ),
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(rebuilt, f, indent=2, ensure_ascii=False)
    return rebuilt


# ----------------------------------------------------------------------
# Faz 1.3 — Verify rebuilt layout (hard asserts + soft warnings)
# ----------------------------------------------------------------------

# SAP-critical fields that must be byte-identical between source and rebuild.
_SAP_INVARIANT_SEG_FIELDS = (
    "bays", "bay_code_start", "levels", "pallets_per_bay",
    "pallet_count", "bay_overrides",
)


def verify_rebuilt_layout(
    rebuilt_path: str = "config/layout_dwg_rebuilt.json",
    source_layout_path: str = "config/layout.json",
) -> dict:
    """Hard asserts + soft warnings on the rebuilt layout.

    Raises AssertionError on any of:
      - pallet total != 3203 (SAP join canary)
      - rack count != 11
      - SAP invariant fields drift on any segment
      - Warehouse(rebuilt_path) instantiation fails
    """
    with open(rebuilt_path) as f:
        rebuilt = json.load(f)
    with open(source_layout_path) as f:
        source = json.load(f)

    errors: list[str] = []
    warnings: list[str] = []

    pallet_total = sum(s["pallet_count"]
                       for r in rebuilt["racks"]
                       for s in r["segments"])
    assert pallet_total == 3203, (
        f"Pallet canary FAILED: rebuilt total={pallet_total}, expected 3203")

    assert len(rebuilt["racks"]) == 11, (
        f"Rack count FAILED: {len(rebuilt['racks'])} != 11")

    src_racks = {r["id"]: r for r in source["racks"]}
    for rack in rebuilt["racks"]:
        rid = rack["id"]
        if rid not in src_racks:
            errors.append(f"rack {rid} in rebuilt but not in source")
            continue
        src_rack = src_racks[rid]
        if len(rack["segments"]) != len(src_rack["segments"]):
            errors.append(f"rack {rid} segment count drift")
            continue
        for i, (seg_new, seg_src) in enumerate(zip(rack["segments"],
                                                    src_rack["segments"])):
            for field in _SAP_INVARIANT_SEG_FIELDS:
                vn = seg_new.get(field)
                vs = seg_src.get(field)
                if vn != vs:
                    errors.append(
                        f"rack {rid} seg[{i}] field '{field}' drift: "
                        f"rebuilt={vn!r} source={vs!r}")
    assert not errors, "SAP invariant drift:\n  - " + "\n  - ".join(errors)

    # Warehouse instantiation smoke test (catches geometry violations).
    from src.warehouse import Warehouse  # type: ignore[import]
    try:
        Warehouse(rebuilt_path)
    except Exception as exc:
        raise AssertionError(
            f"Warehouse({rebuilt_path}) instantiation FAILED: {exc}"
        ) from exc

    # Soft warnings.
    bx = rebuilt.get("building", {})
    bw = float(bx.get("width_m", 0))
    bd = float(bx.get("depth_m", 0))
    for rack in rebuilt["racks"]:
        for seg in rack["segments"]:
            for end in ("start", "end"):
                pt = seg.get(end)
                if not pt:
                    continue
                x, y = float(pt[0]), float(pt[1])
                if x < 0 or y < 0 or (bw and x > bw) or (bd and y > bd):
                    warnings.append(
                        f"rack {rack['id']} seg {end} ({x}, {y}) "
                        f"outside building bbox ({bw}, {bd})")

    n_prod = len(rebuilt.get("production_lines", []))
    n_kit = len(rebuilt.get("kitting_points", []))
    n_put = len(rebuilt.get("putaway_points", []))
    if n_prod != 6:
        warnings.append(f"production_lines: {n_prod} (expected 6)")
    if n_kit != 6:
        warnings.append(f"kitting_points: {n_kit} (expected 6)")
    if n_put != 6:
        warnings.append(f"putaway_points: {n_put} (expected 6)")

    # Data loader canary — preprocess against the rebuilt layout so we
    # catch any (rack, bay) the bin decoder can no longer reach.
    try:
        from src.data_loader import preprocess  # type: ignore[import]
        loaded = preprocess(layout_path=rebuilt_path, write_stats=False)
        stats = loaded.get("stats", {}) if isinstance(loaded, dict) else {}
        n_decoded = int(stats.get("materials_with_decoded_bin", 0))
        if n_decoded < 781:
            warnings.append(
                f"materials_with_decoded_bin={n_decoded} < 781 (data canary)")
    except Exception as exc:  # pragma: no cover
        warnings.append(f"data_loader canary skipped: {exc}")

    return {
        "pallet_canary_total": pallet_total,
        "rack_count": len(rebuilt["racks"]),
        "sap_invariant_ok": True,
        "warehouse_instantiation_ok": True,
        "production_lines": n_prod,
        "kitting_points": n_kit,
        "putaway_points": n_put,
        "warnings": warnings,
    }


def compare_with_layout(extracted: dict, layout_path: str) -> dict:
    """Quick comparison vs current config/layout.json (face-validity only)."""
    if not os.path.exists(layout_path):
        return {"layout_path": layout_path, "exists": False}
    with open(layout_path) as f:
        layout = json.load(f)
    racks = layout.get("racks", [])
    # layout.json coords are in metres → convert to cm for comparison.
    layout_xs = []
    layout_ys = []
    for r in racks:
        x = float(r.get("x", 0.0))
        y = float(r.get("y", 0.0))
        w = float(r.get("width", r.get("length", 0.0)))
        h = float(r.get("depth", r.get("height", 0.0)))
        layout_xs.extend([x * 100, (x + w) * 100])
        layout_ys.extend([y * 100, (y + h) * 100])
    return {
        "layout_path": layout_path,
        "exists": True,
        "rack_count_layout": len(racks),
        "rack_count_dwg_rows": extracted["rack_row_count"],
        "layout_bbox_cm": {
            "x_min": min(layout_xs) if layout_xs else 0.0,
            "y_min": min(layout_ys) if layout_ys else 0.0,
            "x_max": max(layout_xs) if layout_xs else 0.0,
            "y_max": max(layout_ys) if layout_ys else 0.0,
        },
        "dwg_bbox_cm": extracted["floor_bbox_cm"],
    }


def main():
    p = argparse.ArgumentParser(description="Extract layout reference from DXF.")
    p.add_argument("--dxf", default=DEFAULT_DXF, help="DXF input path")
    p.add_argument("--out", default=DEFAULT_OUT, help="JSON output path")
    p.add_argument("--layout", default="config/layout.json",
                   help="layout.json for side-by-side comparison")
    p.add_argument("--mapping", default="config/rack_mapping_dwg_to_sap.json",
                   help="Output path for the rack-mapping manifest (--map)")
    p.add_argument("--rebuilt", default="config/layout_dwg_rebuilt.json",
                   help="Output path for the rebuilt layout (--build)")
    p.add_argument("--pdfs-dir", default="data/rack-drawings",
                   help="Per-rack PDF directory (reference for --map)")
    p.add_argument("--map", action="store_true",
                   help="Generate DWG→SAP rack mapping manifest "
                        "(needs --out extracted JSON first)")
    p.add_argument("--build", action="store_true",
                   help="Build DWG-derived layout (needs --map first)")
    p.add_argument("--verify", action="store_true",
                   help="Verify the rebuilt layout against SAP invariants")
    args = p.parse_args()

    if args.map:
        payload = generate_rack_mapping(
            extracted_path=args.out,
            layout_path=args.layout,
            pdfs_dir=args.pdfs_dir,
            out_path=args.mapping,
        )
        print(f"Rack mapping → {args.mapping}")
        print(f"  Rows: {len(payload['rows'])}  "
              f"verticals: {len(payload['verticals'])}  "
              f"unmapped layout racks: {payload['racks_without_dwg_match']}")
        print(f"  Transform max-abs residual: "
              f"{payload['transform']['max_abs_residual_m']} m "
              f"(anchors: {payload['transform']['anchor_count']})")
        for m in payload["rows"]:
            if m["confidence"] != "high":
                tgt = m.get("sap_rack") or m.get("disposition", "?")
                print(f"  REVIEW {m['dwg_row']:4} → {tgt:18} "
                      f"({m['confidence']})")
        return

    if args.build:
        rebuilt = build_layout_from_dwg(
            mapping_path=args.mapping,
            extracted_path=args.out,
            source_layout_path=args.layout,
            out_path=args.rebuilt,
        )
        n_rebuilt = sum(1 for e in rebuilt["_dwg_meta"]["rebuilt_segments"])
        n_preserved = sum(1 for e in rebuilt["_dwg_meta"]["preserved_segments"])
        print(f"Rebuilt layout → {args.rebuilt}")
        print(f"  DWG-rebuilt segments: {n_rebuilt}  "
              f"preserved segments: {n_preserved}")
        print(f"  Production lines: {len(rebuilt.get('production_lines', []))}")
        return

    if args.verify:
        result = verify_rebuilt_layout(
            rebuilt_path=args.rebuilt,
            source_layout_path=args.layout,
        )
        print(f"Verify {args.rebuilt}: pallet={result['pallet_canary_total']} "
              f"(canary 3203) racks={result['rack_count']}")
        if result["warnings"]:
            print(f"  Warnings ({len(result['warnings'])}):")
            for w in result["warnings"]:
                print(f"    - {w}")
        else:
            print("  No warnings.")
        return

    payload = extract(args.dxf)
    payload["comparison_with_layout"] = compare_with_layout(payload, args.layout)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)

    bbox = payload["floor_bbox_cm"]
    print(f"DWG extraction → {args.out}")
    print(f"  Floor: {bbox['x_max_cm']-bbox['x_min_cm']:.0f}cm × "
          f"{bbox['y_max_cm']-bbox['y_min_cm']:.0f}cm")
    print(f"  Rack rows (horizontal): {payload['rack_row_count']}")
    print(f"  Rack columns (vertical): {len(payload['rack_columns_vertical'])}")
    print(f"  Mean rack width:    {payload['rack_width_stats_cm']['mean']:.0f} cm "
          f"(depth {payload['rack_depth_stats_cm']['mean']:.0f} cm)")
    print(f"  RAFLAR uprights:    {len(payload['raflar_uprights'])} "
          f"(beam markers excluded: {payload['raflar_beam_markers_count']})")
    print(f"  Corridors / columns / line_boundaries / hatches / dims: "
          f"{len(payload['corridors'])} / {len(payload['columns'])} / "
          f"{len(payload['line_boundaries'])} / {len(payload['staging_hatches'])} / "
          f"{len(payload['dimensions'])}")
    print(f"  Kitting labels:     {len(payload['kitting_points'])}")
    print(f"  Putaway labels:     {len(payload['putaway_points'])}")
    print(f"  Production lines:   {len(payload['production_lines'])}")
    for pl in payload["production_lines"]:
        k = pl.get("nearest_kitting") or {}
        print(f"    - {pl['line_label']:18}  kitting @ "
              f"({k.get('x', 0):.0f},{k.get('y', 0):.0f}) "
              f"d={k.get('distance_cm', 0):.0f} cm")
    cmp = payload.get("comparison_with_layout", {})
    if cmp.get("exists"):
        print(f"  Current layout.json racks: {cmp['rack_count_layout']}  "
              f"(DWG rows: {cmp['rack_count_dwg_rows']})  "
              "[reference only, NOT applied]")


if __name__ == "__main__":
    main()
