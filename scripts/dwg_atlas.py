#!/usr/bin/env python3
"""DWG Atlas — maximum-detail visualization of the warehouse DWG + rack PDFs.

Produces ``output/dwg_atlas/`` with:
  - layers/                10 per-layer high-DPI PNGs + all-layers composite
  - dwg_annotated_grid.png 50x40-inch annotated render with coordinate grid,
                           TRAVERS row labels (R##), vertical-column labels (V##)
  - racks/                 11 rack PDFs rasterised at -r 300 (one PNG each)
  - index.html             single-page atlas with pan/zoom DWG + clickable
                           rack PDF + layer grid

Run: ``python scripts/dwg_atlas.py``
Open: ``xdg-open output/dwg_atlas/index.html``
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

import ezdxf  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DXF = Path("/tmp/manisa.dxf")
OUT = REPO_ROOT / "output" / "dwg_atlas"
RACKS_PDF_DIR = REPO_ROOT / "data" / "rack-drawings"


# ---------- helpers ----------

def _size(p: Path) -> str:
    s = p.stat().st_size
    return f"{s/1e6:.1f}MB" if s > 1e6 else f"{s/1e3:.0f}KB"


def _set_layer_visibility(doc, target_layers: list[str]) -> dict[str, tuple[bool, bool]]:
    """Freeze every layer not in target_layers; thaw the targets.

    Returns the prior (is_frozen, is_off) state so the caller can restore it.
    """
    saved: dict[str, tuple[bool, bool]] = {}
    targets = set(target_layers)
    for layer in doc.layers:
        n = layer.dxf.name
        saved[n] = (layer.is_frozen, layer.is_off)
        if n in targets:
            layer.thaw()
            layer.on()
        else:
            layer.freeze()
    return saved


def _restore_layer_state(doc, saved: dict[str, tuple[bool, bool]]) -> None:
    for n, (was_frozen, was_off) in saved.items():
        layer = doc.layers.get(n)
        if was_frozen:
            layer.freeze()
        else:
            layer.thaw()
        if was_off:
            layer.off()
        else:
            layer.on()


_DWG_BOUNDS_CACHE: tuple[float, float, float, float] | None = None


def _dwg_bounds(doc) -> tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax) of all renderable entities (cached)."""
    global _DWG_BOUNDS_CACHE
    if _DWG_BOUNDS_CACHE is not None:
        return _DWG_BOUNDS_CACHE
    xs: list[float] = []
    ys: list[float] = []
    for e in doc.modelspace():
        if e.dxftype() == "LWPOLYLINE":
            for p in e.get_points("xy"):
                xs.append(float(p[0]))
                ys.append(float(p[1]))
        elif e.dxftype() == "LINE":
            xs.extend([float(e.dxf.start.x), float(e.dxf.end.x)])
            ys.extend([float(e.dxf.start.y), float(e.dxf.end.y)])
        elif e.dxftype() in ("TEXT", "MTEXT"):
            xs.append(float(e.dxf.insert.x))
            ys.append(float(e.dxf.insert.y))
    pad = 200.0
    _DWG_BOUNDS_CACHE = (min(xs) - pad, min(ys) - pad,
                         max(xs) + pad, max(ys) + pad)
    return _DWG_BOUNDS_CACHE


def _render_layers(doc, target_layers: list[str], out_path: Path,
                   title: str = "", figsize=(40, 30), dpi: int = 200) -> None:
    saved = _set_layer_visibility(doc, target_layers)
    try:
        fig, ax = plt.subplots(figsize=figsize)
        ctx = RenderContext(doc)
        Frontend(ctx, MatplotlibBackend(ax)).draw_layout(
            doc.modelspace(), finalize=True
        )
        # Frontend.draw_layout(finalize=True) shrinks fig to ~4.8x4.8 — restore.
        fig.set_size_inches(*figsize)
        xmin, ymin, xmax, ymax = _dwg_bounds(doc)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal")
        if title:
            ax.set_title(title, fontsize=22)
        fig.savefig(out_path, dpi=dpi, facecolor="white")
        plt.close(fig)
    finally:
        _restore_layer_state(doc, saved)
    print(f"  + {out_path.relative_to(REPO_ROOT)}  ({_size(out_path)})")


# ---------- Phase A: per-layer renders ----------

def phase_a_per_layer() -> None:
    print("=== Phase A: per-layer renders ===")
    (OUT / "layers").mkdir(parents=True, exist_ok=True)
    doc = ezdxf.readfile(str(DXF))

    all_layers = [l.dxf.name for l in doc.layers
                  if l.dxf.name not in ("Defpoints",)]

    _render_layers(doc, all_layers, OUT / "layers" / "all_layers.png",
                   title="All layers — full DWG")

    per_layer = [
        ("TRAVERS",          "TRAVERS — rack cross-beams (LWPOLYLINE+LINE, 542 entities)"),
        ("RAFLAR",           "RAFLAR — pallet slots + beam markers (494 LWPOLYLINE)"),
        ("H",                "H — KITTING / PUTAWAY / line tag labels (33 TEXT/MTEXT)"),
        ("OLCU",             "OLCU — dimension lines (60)"),
        ("ince çizgi",       "ince çizgi — thin lines + DIM + HATCH (29)"),
        ("cu_yol_cizgileri", "cu_yol_cizgileri — corridor (1)"),
        ("kolon",            "kolon — column (1)"),
        ("AM_8",             "AM_8 — staging hatch (1)"),
        ("Hat_Sınır",        "Hat_Sınır — line boundary (4)"),
        ("0",                "Layer 0 — misc (52, LINE+MTEXT)"),
    ]
    for name, title in per_layer:
        safe = name.replace(" ", "_").replace("ı", "i").replace("ç", "c")
        out = OUT / "layers" / f"{safe}_only.png"
        _render_layers(doc, [name], out, title=title)


# ---------- Phase B: annotated grid ----------

def phase_b_annotated_grid() -> None:
    print("=== Phase B: annotated coordinate-grid render ===")
    from src.dwg_to_layout import (  # type: ignore[import-not-found]
        _derive_rack_rows,
        _extract_labels,
        _extract_travers_beams,
        _load_msp,
    )

    msp = _load_msp(str(DXF))
    labels = _extract_labels(msp)
    beams = _extract_travers_beams(msp)
    rows = _derive_rack_rows(beams)
    vcols = _derive_vertical_columns(beams)

    fig, ax = plt.subplots(figsize=(50, 40))

    # TRAVERS beams (blue outlines)
    for (xmin, ymin, xmax, ymax, w, h) in beams:
        ax.add_patch(Rectangle((xmin, ymin), w, h,
                               fill=False, edgecolor="blue", linewidth=0.4))

    # RAFLAR (orange fills)
    doc = ezdxf.readfile(str(DXF))
    for e in doc.modelspace().query('LWPOLYLINE[layer=="RAFLAR"]'):
        pts = list(e.get_points("xy"))
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.add_patch(Rectangle((min(xs), min(ys)), max(xs) - min(xs),
                               max(ys) - min(ys), fill=True,
                               facecolor="orange", edgecolor="orange",
                               linewidth=0.2, alpha=0.55))

    # Detected horizontal rack rows
    for r in rows:
        yc = (r.y_min + r.y_max) / 2
        ax.add_patch(Rectangle((r.x_min - 30, r.y_min - 30),
                               r.width_cm + 60, r.depth_cm + 60,
                               fill=False, edgecolor="red",
                               linewidth=2.5, linestyle="--"))
        ax.text(r.x_max + 80, yc,
                f"{r.id}\n  y={yc:.0f}\n  x=[{r.x_min:.0f}..{r.x_max:.0f}]\n"
                f"  w={r.width_cm:.0f}cm  bays~{r.bay_count}",
                fontsize=16, color="red", fontweight="bold", va="center")

    # Detected vertical rack columns
    for v in vcols:
        xc = (v["x_min"] + v["x_max"]) / 2
        h_cm = v["y_max"] - v["y_min"]
        ax.add_patch(Rectangle((v["x_min"] - 30, v["y_min"] - 30),
                               v["x_max"] - v["x_min"] + 60,
                               v["y_max"] - v["y_min"] + 60,
                               fill=False, edgecolor="green",
                               linewidth=2.5, linestyle="--"))
        ax.text(xc, v["y_max"] + 80,
                f"{v['id']}  x={xc:.0f}\nh={h_cm:.0f}cm  beams={v['beams']}",
                fontsize=14, color="green", fontweight="bold", ha="center")

    # Text labels
    for lab in labels:
        ax.plot(lab.x, lab.y, "*", color="purple", markersize=12)
        ax.text(lab.x + 10, lab.y + 10, lab.text, fontsize=11,
                color="purple", alpha=0.9, fontweight="bold")

    # Coordinate grid (every 500cm major, 100cm minor)
    ax.set_aspect("equal")
    ax.grid(True, which="major", alpha=0.35, linestyle="-", linewidth=0.6)
    ax.grid(True, which="minor", alpha=0.12, linestyle=":", linewidth=0.3)

    xmin = min(b[0] for b in beams) - 200
    xmax = max(b[2] for b in beams) + 800
    ymin = min(b[1] for b in beams) - 200
    ymax = max(b[3] for b in beams) + 800
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_xticks(np.arange(0, xmax + 500, 500))
    ax.set_xticks(np.arange(0, xmax + 100, 100), minor=True)
    ax.set_yticks(np.arange(0, ymax + 500, 500))
    ax.set_yticks(np.arange(0, ymax + 100, 100), minor=True)
    ax.set_xlabel("DWG X (cm) — west ←→ east", fontsize=18)
    ax.set_ylabel("DWG Y (cm) — south ↓↑ north", fontsize=18)
    ax.set_title("DWG annotated grid — "
                 "Blue: TRAVERS  Orange: RAFLAR  "
                 "Red: derived horizontal rows  Green: derived vertical cols  "
                 "Purple: labels", fontsize=20)

    out = OUT / "dwg_annotated_grid.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  + {out.relative_to(REPO_ROOT)}  ({_size(out)})")


def _derive_vertical_columns(beams: list[tuple]) -> list[dict]:
    """Cluster vertical TRAVERS beams by X to identify J-leg / east column candidates."""
    verts = [b for b in beams if b[5] > b[4] and b[5] > 100 and b[4] < 50]
    verts.sort(key=lambda b: (b[0] + b[2]) / 2)
    clusters: list[list] = []
    cur: list = []
    last_x: float | None = None
    for v in verts:
        cx = (v[0] + v[2]) / 2
        if last_x is None or cx - last_x < 140:
            cur.append(v)
        else:
            if cur:
                clusters.append(cur)
            cur = [v]
        last_x = cx
    if cur:
        clusters.append(cur)
    out: list[dict] = []
    for i, c in enumerate(clusters):
        out.append({
            "id": f"V{i+1:02d}",
            "x_min": min(b[0] for b in c),
            "x_max": max(b[2] for b in c),
            "y_min": min(b[1] for b in c),
            "y_max": max(b[3] for b in c),
            "beams": len(c),
        })
    return out


# ---------- Phase C: rack PDF gallery ----------

def phase_c_pdf_gallery() -> None:
    print("=== Phase C: rack PDF gallery (pdftoppm -r 300) ===")
    racks_dir = OUT / "racks"
    racks_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(RACKS_PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"  ! No PDFs in {RACKS_PDF_DIR}")
        return
    for pdf in pdfs:
        prefix = racks_dir / pdf.stem
        subprocess.run(
            ["pdftoppm", "-r", "300", "-png", str(pdf), str(prefix)],
            check=True,
        )
        # pdftoppm names single-page output as <prefix>-1.png
        out_png = racks_dir / f"{pdf.stem}-1.png"
        if out_png.exists():
            print(f"  + {out_png.relative_to(REPO_ROOT)}  ({_size(out_png)})")


# ---------- Phase D: HTML atlas ----------

def phase_d_html_atlas() -> None:
    print("=== Phase D: HTML atlas ===")
    racks = sorted((OUT / "racks").glob("*.png"))
    layers = sorted((OUT / "layers").glob("*.png"))

    rack_thumbs = "\n".join(
        f'<div class="thumb" onclick="lightbox(\'racks/{p.name}\', \'{p.stem}\')">'
        f'<img src="racks/{p.name}" loading="lazy"><span>{p.stem}</span></div>'
        for p in racks
    )
    layer_thumbs = "\n".join(
        f'<div class="thumb" onclick="setMain(\'layers/{p.name}\', \'{p.stem}\')">'
        f'<img src="layers/{p.name}" loading="lazy"><span>{p.stem}</span></div>'
        for p in layers
    )

    html = (
        HTML_TEMPLATE
        .replace("__N_LAYERS__", str(len(layers)))
        .replace("__N_RACKS__", str(len(racks)))
        .replace("__LAYER_THUMBS__", layer_thumbs)
        .replace("__RACK_THUMBS__", rack_thumbs)
    )
    out = OUT / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"  + {out.relative_to(REPO_ROOT)}  ({_size(out)})")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8">
<title>DWG Atlas — SE Manisa</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,sans-serif;background:#222;color:#eee;
     display:grid;grid-template-columns:1fr 380px;height:100vh;overflow:hidden}
#main{position:relative;overflow:hidden;background:#fff}
#main img{position:absolute;left:0;top:0;cursor:grab;user-select:none;
          transform-origin:0 0;max-width:none;image-rendering:high-quality}
#main.dragging img{cursor:grabbing}
#sidebar{padding:8px;overflow-y:auto;background:#2a2a2a}
h2{margin:10px 0 4px;font-size:13px;color:#fff;
   text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #444;padding-bottom:3px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.thumb{background:#333;border-radius:4px;overflow:hidden;cursor:pointer;
       text-align:center;border:2px solid transparent}
.thumb:hover{border-color:#4af}
.thumb img{width:100%;height:88px;object-fit:cover;display:block;background:#fff}
.thumb span{display:block;padding:3px 4px;font-size:10.5px;color:#bbb;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#lightbox{display:none;position:fixed;inset:0;background:rgba(0,0,0,.96);
          z-index:100;align-items:center;justify-content:center;flex-direction:column;
          cursor:pointer}
#lightbox.show{display:flex}
#lightbox img{max-width:96vw;max-height:90vh;object-fit:contain;background:#fff}
#lightbox .close{position:absolute;top:10px;right:20px;color:#fff;font-size:28px;
                 background:rgba(0,0,0,.5);padding:4px 14px;border-radius:4px}
#lightbox h3{color:#fff;margin:6px 0 8px}
#controls{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.7);color:#fff;
          padding:6px 10px;border-radius:4px;font-size:12px;z-index:10}
#controls button{margin-left:4px;background:#444;color:#fff;border:0;
                 padding:4px 9px;border-radius:3px;cursor:pointer;font-size:12px}
#controls button:hover{background:#5a5a5a}
#status{position:absolute;bottom:8px;left:8px;background:rgba(0,0,0,.7);color:#fff;
        padding:4px 8px;border-radius:4px;font-size:11px;z-index:10}
</style>
</head><body>

<div id="main">
  <img id="cad" src="dwg_annotated_grid.png" alt="DWG">
  <div id="controls">
    <span id="title">dwg_annotated_grid.png</span>
    <button onclick="setMain('dwg_annotated_grid.png','annotated grid')">Grid</button>
    <button onclick="setMain('layers/all_layers.png','all layers')">All</button>
    <button onclick="fit()">Fit</button>
    <button onclick="zoomBy(1.5)">+</button>
    <button onclick="zoomBy(1/1.5)">−</button>
  </div>
  <div id="status">scroll=zoom · drag=pan · doubleclick=fit</div>
</div>

<div id="sidebar">
  <h2>Layers (__N_LAYERS__)</h2>
  <div class="grid">__LAYER_THUMBS__</div>
  <h2>Rack PDFs (__N_RACKS__)</h2>
  <div class="grid">__RACK_THUMBS__</div>
</div>

<div id="lightbox" onclick="closeLb(event)">
  <span class="close" onclick="closeLb(event,true)">×</span>
  <h3 id="lb-title"></h3>
  <img id="lb-img" src="">
</div>

<script>
const cad   = document.getElementById('cad');
const main  = document.getElementById('main');
const title = document.getElementById('title');
let scale=1, tx=0, ty=0, dragging=false, startX=0, startY=0, lastTx=0, lastTy=0;

function applyT(){ cad.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')'; }
function fit(){
  const r = main.getBoundingClientRect();
  const w = cad.naturalWidth, h = cad.naturalHeight;
  if (!w || !h) return;
  scale = Math.min(r.width/w, r.height/h) * 0.95;
  tx = (r.width - w*scale)/2;
  ty = (r.height - h*scale)/2;
  applyT();
}
function zoomBy(f, cx, cy){
  const r = main.getBoundingClientRect();
  cx = cx == null ? r.width/2  : cx;
  cy = cy == null ? r.height/2 : cy;
  const wx = (cx - tx)/scale, wy = (cy - ty)/scale;
  scale *= f;
  tx = cx - wx*scale;
  ty = cy - wy*scale;
  applyT();
}

main.addEventListener('wheel', function(e){
  e.preventDefault();
  const r = main.getBoundingClientRect();
  zoomBy(e.deltaY < 0 ? 1.2 : 1/1.2, e.clientX - r.left, e.clientY - r.top);
}, {passive:false});

main.addEventListener('pointerdown', function(e){
  dragging = true; main.classList.add('dragging');
  startX = e.clientX; startY = e.clientY; lastTx = tx; lastTy = ty;
  main.setPointerCapture(e.pointerId);
});
main.addEventListener('pointermove', function(e){
  if (!dragging) return;
  tx = lastTx + (e.clientX - startX);
  ty = lastTy + (e.clientY - startY);
  applyT();
});
main.addEventListener('pointerup', function(){
  dragging = false; main.classList.remove('dragging');
});
main.addEventListener('dblclick', fit);
cad.addEventListener('load', fit);
window.addEventListener('resize', fit);

function setMain(src, name){
  cad.src = src; title.textContent = name;
  setTimeout(fit, 80);
}
function lightbox(src, name){
  const lb = document.getElementById('lightbox');
  document.getElementById('lb-img').src = src;
  document.getElementById('lb-title').textContent = name;
  lb.classList.add('show');
}
function closeLb(e, force){
  if (force || e.target.id === 'lightbox' || e.target.tagName === 'IMG' || e.target.className === 'close'){
    document.getElementById('lightbox').classList.remove('show');
  }
}
</script>
</body></html>
"""


# ---------- main ----------

def main() -> None:
    if not DXF.exists():
        sys.exit(f"missing DXF: {DXF}  — run `dwg2dxf 'data/SE Manisa Ambar Rafları.dwg' -o /tmp/manisa.dxf` first")
    OUT.mkdir(parents=True, exist_ok=True)
    phase_a_per_layer()
    phase_b_annotated_grid()
    phase_c_pdf_gallery()
    phase_d_html_atlas()
    print(f"\nAtlas ready: file://{OUT.resolve()}/index.html")


if __name__ == "__main__":
    main()
