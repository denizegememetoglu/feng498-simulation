"""Generate the simulation flow-chart PNG used by the V&V report.

A discrete-event flow diagram of one order's lifecycle through the
ZWM92-driven Arena-style simulation. Hand-laid layout (no graphviz dep).
Run: python scripts/build_flowchart.py → output/sim_flowchart.png
"""
from __future__ import annotations

import os

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon


OUT = "output/sim_flowchart.png"


def _box(ax, x, y, w, h, text, *, fc="#E8F0FE", ec="#1F4E79", fs=9, bold=False):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02",
                       facecolor=fc, edgecolor=ec, linewidth=1.4)
    ax.add_patch(p)
    ax.text(x + w/2, y + h/2, text, ha="center", va="center",
            fontsize=fs, fontweight="bold" if bold else "normal", wrap=True)


def _diamond(ax, x, y, w, h, text, *, fc="#FFF4D6", ec="#9A6700", fs=9):
    pts = [(x + w/2, y), (x + w, y + h/2), (x + w/2, y + h), (x, y + h/2)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor=ec, linewidth=1.4))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs)


def _arrow(ax, x1, y1, x2, y2, *, label=None, color="#333"):
    a = FancyArrowPatch((x1, y1), (x2, y2),
                        arrowstyle="-|>", mutation_scale=14,
                        color=color, linewidth=1.2)
    ax.add_patch(a)
    if label:
        ax.text((x1 + x2)/2 + 0.05, (y1 + y2)/2, label,
                fontsize=8, color=color, ha="left", va="center")


def build():
    fig, ax = plt.subplots(figsize=(11, 14))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis("off")

    # Title
    ax.text(5, 13.6, "Order lifecycle — one pass through the simulation",
            ha="center", fontsize=13, fontweight="bold")
    ax.text(5, 13.2,
            "(ZWM92-fitted Arena-style driver, fixed seed, SimPy resources)",
            ha="center", fontsize=9, style="italic", color="#555")

    # Source / sampling block
    _box(ax, 0.3, 11.5, 9.4, 1.3,
         "ZWM92DistributionDriver.next_order()\n"
         "  line ~ Categorical(line_weights)   ·   "
         "items per order ~ Empirical(BOM sizes)\n"
         "  material ~ Categorical(per-line weights)   ·   "
         "IAT ~ Exponential(mean=4.8 min)",
         fc="#FCE7E5", ec="#A12017", bold=True)

    _arrow(ax, 5, 11.5, 5, 11.0)
    _box(ax, 3.5, 10.3, 3.0, 0.6, "env.timeout(IAT)", fc="#F0F0F0")
    _arrow(ax, 5, 10.3, 5, 9.9)

    # Per-item loop start
    _box(ax, 1.5, 9.1, 7.0, 0.7,
         "For each item in the order  →  resolve target bin from slotting policy",
         bold=True)
    _arrow(ax, 5, 9.1, 5, 8.7)

    # Decision: Kardex?
    _diamond(ax, 3.2, 7.5, 3.6, 1.2, "Material lives in\nKardex pool?")
    _arrow(ax, 6.8, 8.1, 8.4, 8.1, label="yes")
    _box(ax, 8.4, 7.8, 1.4, 0.6, "request Kardex\n(capacity 4)",
         fc="#E3F4E8", ec="#1F7A3B")
    _arrow(ax, 9.1, 7.8, 9.1, 6.4)
    _box(ax, 7.8, 5.8, 2.0, 0.6,
         "wait(carousel+pick)\nLognormal", fc="#E3F4E8", ec="#1F7A3B")
    _arrow(ax, 8.8, 5.8, 8.8, 4.5, label="join")

    _arrow(ax, 5.0, 7.5, 5.0, 7.1, label="no")

    # Decision: lower level + kit corridor?
    _diamond(ax, 3.0, 5.8, 4.0, 1.3,
             "level < FAST and\nkit corridor side?")
    _arrow(ax, 5.0, 5.8, 5.0, 5.4, label="yes (operator only)")
    _arrow(ax, 3.0, 6.45, 1.4, 6.45, label="no")

    # Operator-only path
    _box(ax, 3.2, 4.6, 3.6, 0.7,
         "request Operator (cap 8)\nwalk → pick", fc="#E8F0FE", ec="#1F4E79")
    _arrow(ax, 5.0, 4.6, 5.0, 4.0)

    # Decision: manual or RT?
    _diamond(ax, 0.0, 5.5, 2.8, 1.3,
             "level ≤\nMANUAL_PICK_MAX?")
    _arrow(ax, 1.4, 5.5, 1.4, 5.0, label="yes (penalty)")
    _box(ax, 0.0, 4.2, 2.8, 0.7,
         "Operator manually\nclimbs lower beam\n+penalty Lognormal",
         fc="#E8F0FE", ec="#1F4E79", fs=8)
    _arrow(ax, 1.4, 4.2, 1.4, 3.4)

    _arrow(ax, 0.0, 6.0, -0.0, 6.0)  # filler
    _box(ax, -0.05, 6.85, 1.65, 0.0, "")  # placeholder
    # RT branch (when level too high for manual)
    _box(ax, 0.0, 7.4, 2.8, 0.6,
         "request RT (cap 7)\n+ depot→bin travel",
         fc="#FFF1E5", ec="#A85811")
    _arrow(ax, 1.4, 7.4, 1.4, 6.8, label="no")
    _box(ax, 0.0, 6.4, 2.8, 0.6,
         "RT lift + pick/place\nLognormal", fc="#FFF1E5", ec="#A85811")
    _arrow(ax, 1.4, 6.4, 1.4, 4.9)

    # Common rejoin
    _box(ax, 3.5, 3.4, 3.0, 0.7,
         "release position lock\n(per-pallet 1-cap)", fc="#F0F0F0")
    _arrow(ax, 5.0, 3.4, 5.0, 3.0)

    # End-of-order
    _box(ax, 3.0, 2.3, 4.0, 0.7,
         "walk back to kitting point\nfor that line", bold=True)
    _arrow(ax, 5.0, 2.3, 5.0, 1.9)
    _box(ax, 2.5, 1.2, 5.0, 0.7,
         "KPICollector.record_order(prep, lead, walk, op_wait, RT_wait)",
         fc="#E8F0FE", ec="#1F4E79")
    _arrow(ax, 5.0, 1.2, 5.0, 0.7)
    _box(ax, 3.2, 0.0, 3.6, 0.65,
         "next order ↺ (until duration over)",
         fc="#E0E0E0", ec="#444", fs=9, bold=True)

    # Right-side legend
    leg_x, leg_y = 8.0, 4.0
    ax.text(leg_x, leg_y + 0.6, "Legend", fontsize=10, fontweight="bold")
    legend = [
        ("#FCE7E5", "Stochastic input (RNG)"),
        ("#E8F0FE", "Operator process"),
        ("#FFF1E5", "Reach-truck process"),
        ("#E3F4E8", "Kardex process"),
        ("#FFF4D6", "Decision"),
        ("#F0F0F0", "Bookkeeping"),
    ]
    for i, (fc, label) in enumerate(legend):
        y = leg_y - i*0.45
        ax.add_patch(FancyBboxPatch((leg_x, y), 0.35, 0.3,
                                    boxstyle="round,pad=0.02",
                                    facecolor=fc, edgecolor="#333"))
        ax.text(leg_x + 0.5, y + 0.15, label, fontsize=8, va="center")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
