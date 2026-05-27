"""Full DWG entity dump for the standalone 3D HTML viewer.

Reads the DXF (converted from data/SE Manisa Ambar Rafları.dwg via
libredwg's dwg2dxf) and writes a layer-keyed JSON with every entity's
raw geometry. Coordinates remain in centimetres — the HTML converts to
metres at render time. READ-ONLY: does not touch config/layout.json.

Usage:
    dwg2dxf "data/SE Manisa Ambar Rafları.dwg" -o /tmp/manisa_full.dxf
    python -m scripts.dwg_full_extract
"""
from __future__ import annotations

import json
import os
import sys

import ezdxf


DEFAULT_DXF = "/tmp/manisa_full.dxf"
DEFAULT_OUT = "/tmp/manisa_full_extract.json"


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _entity_to_dict(e) -> dict | None:
    t = e.dxftype()
    layer = str(e.dxf.layer) if hasattr(e.dxf, "layer") else "?"
    base = {"type": t, "layer": layer}

    if t == "LWPOLYLINE":
        pts = [[_safe_float(p[0]), _safe_float(p[1])] for p in e.get_points("xy")]
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        base.update({
            "points": pts,
            "closed": bool(e.closed),
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
        })
        return base

    if t == "POLYLINE":
        pts = []
        for v in e.vertices:
            loc = v.dxf.location
            pts.append([_safe_float(loc.x), _safe_float(loc.y)])
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        base.update({"points": pts, "bbox": [min(xs), min(ys), max(xs), max(ys)]})
        return base

    if t == "LINE":
        s = e.dxf.start
        en = e.dxf.end
        base.update({
            "start": [_safe_float(s.x), _safe_float(s.y)],
            "end":   [_safe_float(en.x), _safe_float(en.y)],
        })
        return base

    if t == "CIRCLE":
        c = e.dxf.center
        base.update({
            "center": [_safe_float(c.x), _safe_float(c.y)],
            "radius": _safe_float(e.dxf.radius),
        })
        return base

    if t == "ARC":
        c = e.dxf.center
        base.update({
            "center": [_safe_float(c.x), _safe_float(c.y)],
            "radius": _safe_float(e.dxf.radius),
            "start_angle": _safe_float(e.dxf.start_angle),
            "end_angle":   _safe_float(e.dxf.end_angle),
        })
        return base

    if t in ("TEXT", "MTEXT"):
        if t == "TEXT":
            txt = (e.dxf.text or "").strip()
        else:
            txt = e.plain_text().strip() if hasattr(e, "plain_text") else ""
        if not txt:
            return None
        ins = e.dxf.insert
        base.update({
            "text": txt,
            "x": _safe_float(ins.x),
            "y": _safe_float(ins.y),
            "height": _safe_float(getattr(e.dxf, "height", 0)),
            "rotation": _safe_float(getattr(e.dxf, "rotation", 0)),
        })
        return base

    if t == "INSERT":
        ins = e.dxf.insert
        base.update({
            "block": str(e.dxf.name),
            "insert": [_safe_float(ins.x), _safe_float(ins.y)],
            "x_scale": _safe_float(getattr(e.dxf, "xscale", 1)),
            "y_scale": _safe_float(getattr(e.dxf, "yscale", 1)),
            "rotation": _safe_float(getattr(e.dxf, "rotation", 0)),
        })
        return base

    if t == "HATCH":
        xs: list[float] = []
        ys: list[float] = []
        for p in e.paths:
            if hasattr(p, "vertices"):
                for pt in p.vertices:
                    xs.append(_safe_float(pt[0]))
                    ys.append(_safe_float(pt[1]))
            if hasattr(p, "edges"):
                for edge in p.edges:
                    if hasattr(edge, "start") and edge.start is not None:
                        xs.append(_safe_float(edge.start[0]))
                        ys.append(_safe_float(edge.start[1]))
                    if hasattr(edge, "end") and edge.end is not None:
                        xs.append(_safe_float(edge.end[0]))
                        ys.append(_safe_float(edge.end[1]))
        if not xs:
            return None
        base.update({"bbox": [min(xs), min(ys), max(xs), max(ys)]})
        return base

    if t == "SOLID":
        pts = []
        for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
            if hasattr(e.dxf, attr):
                v = getattr(e.dxf, attr)
                pts.append([_safe_float(v.x), _safe_float(v.y)])
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        base.update({"points": pts, "bbox": [min(xs), min(ys), max(xs), max(ys)]})
        return base

    # Unknown type — skip, but log
    return None


def main(dxf_path: str = DEFAULT_DXF, out_path: str = DEFAULT_OUT) -> dict:
    if not os.path.exists(dxf_path):
        print(f"ERROR: DXF not found at {dxf_path}.", file=sys.stderr)
        print("Run: dwg2dxf 'data/SE Manisa Ambar Rafları.dwg' -o /tmp/manisa_full.dxf",
              file=sys.stderr)
        sys.exit(1)

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    layers: dict[str, list[dict]] = {}
    type_counts: dict[str, int] = {}
    skipped_types: dict[str, int] = {}
    all_x: list[float] = []
    all_y: list[float] = []

    for e in msp:
        d = _entity_to_dict(e)
        t = e.dxftype()
        type_counts[t] = type_counts.get(t, 0) + 1
        if d is None:
            skipped_types[t] = skipped_types.get(t, 0) + 1
            continue
        layers.setdefault(d["layer"], []).append(d)

        # Track floor bbox
        if "bbox" in d:
            all_x.extend([d["bbox"][0], d["bbox"][2]])
            all_y.extend([d["bbox"][1], d["bbox"][3]])
        elif "start" in d and "end" in d:
            all_x.extend([d["start"][0], d["end"][0]])
            all_y.extend([d["start"][1], d["end"][1]])
        elif "x" in d and "y" in d:
            all_x.append(d["x"])
            all_y.append(d["y"])

    floor = {
        "x_min": min(all_x) if all_x else 0,
        "y_min": min(all_y) if all_y else 0,
        "x_max": max(all_x) if all_x else 0,
        "y_max": max(all_y) if all_y else 0,
    }
    floor["width_cm"]  = floor["x_max"] - floor["x_min"]
    floor["height_cm"] = floor["y_max"] - floor["y_min"]

    layer_counts = {k: len(v) for k, v in layers.items()}

    result = {
        "_source_dxf": dxf_path,
        "_units": "centimetres",
        "floor": floor,
        "layer_counts": layer_counts,
        "type_counts": type_counts,
        "skipped_types": skipped_types,
        "layers": layers,
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, separators=(",", ":"))

    print(f"Wrote {out_path}")
    print(f"  floor: {floor['width_cm']:.0f} x {floor['height_cm']:.0f} cm")
    print(f"  layers: {len(layers)}")
    for k, n in sorted(layer_counts.items(), key=lambda x: -x[1]):
        print(f"    {k:20s} {n:5d} entities")
    print(f"  type counts: {type_counts}")
    if skipped_types:
        print(f"  skipped (unsupported): {skipped_types}")

    return result


if __name__ == "__main__":
    main()
