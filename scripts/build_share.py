#!/usr/bin/env python3
"""Build the self-contained, WhatsApp-shareable presentation_share.html by inlining
all imagery (pre-rendered 3D backdrop stills + report figures) as base64 data URIs
into the #imgdata <script> tag. The result needs no server and no network — a friend
can just open the file (file://) and click through.

Backdrops come from /tmp/bg_*.jpg (rendered from web/sim_v2.html, see the capture step);
figures come from report/figures/. Idempotent: replaces whatever is in #imgdata.
"""
import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARE = ROOT / "web" / "presentation_share.html"
FIG = ROOT / "report" / "figures"
VID = Path("/tmp/vid_mp4")   # transcoded looping backdrop clips

# logical name -> (file, mime). Names match IMG.* keys used in presentation_share.html.
# Backdrops are looping muted mp4s (animated 3D); figures stay as still images.
ASSETS = {
    "cinematic":  (VID / "cinematic.mp4",  "video/mp4"),
    "overview":   (VID / "overview.mp4",   "video/mp4"),
    "top":        (VID / "top.mp4",        "video/mp4"),
    "rt":         (VID / "rt.mp4",         "video/mp4"),
    "worker":     (VID / "worker.mp4",     "video/mp4"),
    "congestion": (VID / "congestion.mp4", "video/mp4"),
    "heatmap":    (VID / "heatmap.mp4",    "video/mp4"),
    "logo":       (FIG / "ieu_logo.png",                       "image/png"),
    "layout":     (FIG / "layout_topdown_with_decorations.png","image/png"),
    "flowchart":  (FIG / "sim_flowchart_simple.png",           "image/png"),
    "boxplot":    (FIG / "prep_time_boxplot.png",              "image/png"),
    "tornado":    (FIG / "sensitivity_tornado_avg_lead_time.png","image/png"),
}


def datauri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> None:
    missing = [n for n, (p, _) in ASSETS.items() if not p.exists()]
    if missing:
        print(f"[build_share] MISSING assets: {missing}", file=sys.stderr)
        print("  (render backdrops first — see the capture step that writes /tmp/bg_*.jpg)", file=sys.stderr)
        sys.exit(1)
    imgs = {n: datauri(p, m) for n, (p, m) in ASSETS.items()}
    payload = json.dumps(imgs)  # base64 alphabet has no '<', safe inside a <script> tag
    html = SHARE.read_text()
    new, n = re.subn(
        r'(<script type="application/json" id="imgdata">).*?(</script>)',
        lambda mt: mt.group(1) + payload + mt.group(2),
        html, count=1, flags=re.S,
    )
    if n != 1:
        print("[build_share] could not find #imgdata script tag", file=sys.stderr)
        sys.exit(1)
    SHARE.write_text(new)
    print(f"[build_share] inlined {len(imgs)} images → {SHARE.relative_to(ROOT)} "
          f"({len(new)/1024:.0f} KB, payload {len(payload)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
