"""Generate the simulation flow-chart PNGs used by the final report and V&V suite.

Two renderings of the same model:
  output/sim_flowchart_simple.png   — jury-friendly overview (~8 plain-language
                                      boxes, large fonts, generous spacing); goes
                                      in the report body / presentation.
  output/sim_flowchart_detailed.png — full order lifecycle with resources,
                                      decisions and sampling steps, phrased in
                                      plain language (no code identifiers);
                                      goes in the report appendix.
  output/sim_flowchart.png          — copy of the detailed one (kept for the
                                      existing V&V report pipeline).

Hand-laid matplotlib layout (no graphviz dependency).
Run: python scripts/build_flowchart.py
"""
from __future__ import annotations

import os
import shutil

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon

OUT_SIMPLE = "output/sim_flowchart_simple.png"
OUT_DETAIL = "output/sim_flowchart_detailed.png"
OUT_LEGACY = "output/sim_flowchart.png"

# Palette shared by both charts
C_INPUT = ("#FCE7E5", "#A12017")   # stochastic input
C_OP = ("#E8F0FE", "#1F4E79")      # operator process
C_RT = ("#FFF1E5", "#A85811")      # reach-truck process
C_KDX = ("#E3F4E8", "#1F7A3B")     # Kardex process
C_DEC = ("#FFF4D6", "#9A6700")     # decision
C_BOOK = ("#F0F0F0", "#555555")    # bookkeeping / terminal


def _box(ax, x, y, w, h, text, *, c=C_OP, fs=10, bold=False, lw=1.5):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.03",
                       facecolor=c[0], edgecolor=c[1], linewidth=lw)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, fontweight="bold" if bold else "normal",
            linespacing=1.35)


def _diamond(ax, x, y, w, h, text, *, fs=10):
    pts = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=C_DEC[0],
                         edgecolor=C_DEC[1], linewidth=1.5))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, linespacing=1.3)


def _arrow(ax, x1, y1, x2, y2, *, label=None, fs=9, dx=0.08):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                        mutation_scale=16, color="#333", linewidth=1.4)
    ax.add_patch(a)
    if label:
        ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2, label,
                fontsize=fs, color="#333", ha="left", va="center")


def _legend(ax, x, y, fs=9):
    ax.text(x, y + 0.55, "Legend", fontsize=fs + 1, fontweight="bold")
    entries = [
        (C_INPUT, "Sampled from real data"),
        (C_OP, "Operator activity"),
        (C_RT, "Reach-truck activity"),
        (C_KDX, "Kardex activity"),
        (C_DEC, "Decision"),
        (C_BOOK, "Bookkeeping"),
    ]
    for i, (c, label) in enumerate(entries):
        yy = y - i * 0.42
        ax.add_patch(FancyBboxPatch((x, yy), 0.35, 0.28,
                                    boxstyle="round,pad=0.02",
                                    facecolor=c[0], edgecolor=c[1]))
        ax.text(x + 0.5, yy + 0.14, label, fontsize=fs, va="center")


def _legend_strip(ax, y, fs=9):
    """Horizontal legend: two rows of three swatches along the bottom."""
    entries = [
        (C_INPUT, "Sampled from real data"),
        (C_OP, "Operator activity"),
        (C_RT, "Reach-truck activity"),
        (C_KDX, "Kardex activity"),
        (C_DEC, "Decision"),
        (C_BOOK, "Bookkeeping"),
    ]
    xs = [0.6, 4.0, 7.1]
    for i, (c, label) in enumerate(entries):
        xx = xs[i % 3]
        yy = y - (i // 3) * 0.5
        ax.add_patch(FancyBboxPatch((xx, yy), 0.35, 0.28,
                                    boxstyle="round,pad=0.02",
                                    facecolor=c[0], edgecolor=c[1]))
        ax.text(xx + 0.5, yy + 0.14, label, fontsize=fs, va="center")


def build_simple():
    fig, ax = plt.subplots(figsize=(10, 12.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.6, 12)
    ax.axis("off")

    ax.text(5, 11.7, "How the simulation handles one kit order",
            ha="center", fontsize=15, fontweight="bold")

    # 1 — arrivals
    _box(ax, 1.6, 10.0, 6.8, 1.0,
         "Kit orders arrive in batches\n"
         "(arrival times, kit contents and target line are sampled\n"
         "from four months of real SAP dispatch records)",
         c=C_INPUT, fs=11, bold=True)
    _arrow(ax, 5, 10.0, 5, 9.45)

    # 2 — lookup
    _box(ax, 2.1, 8.6, 5.8, 0.85,
         "For every material in the kit,\nfind its storage location"
         " (set by the slotting policy)", fs=11)
    _arrow(ax, 5, 8.6, 5, 7.95)

    # 3 — decision
    _diamond(ax, 3.1, 6.3, 3.8, 1.65, "Where is the\nmaterial stored?", fs=11)

    # branches
    bx_y, bx_h = 4.35, 1.3
    _arrow(ax, 3.1, 7.12, 1.7, 7.12, dx=-1.15)
    ax.text(2.6, 7.3, "Kardex unit", fontsize=9.5)
    _arrow(ax, 1.7, 7.12, 1.7, bx_y + bx_h)
    _box(ax, 0.35, bx_y, 2.7, bx_h,
         "Automated carousel\nbrings the tray;\noperator picks the item",
         c=C_KDX, fs=10)

    _arrow(ax, 5, 6.3, 5, bx_y + bx_h, label="low level,\nhand reach", fs=9.5)
    _box(ax, 3.65, bx_y, 2.7, bx_h,
         "Operator walks to the\nshelf and picks by hand", c=C_OP, fs=10)

    _arrow(ax, 6.9, 7.12, 8.3, 7.12)
    ax.text(7.0, 7.3, "high level", fontsize=9.5)
    _arrow(ax, 8.3, 7.12, 8.3, bx_y + bx_h)
    _box(ax, 6.95, bx_y, 2.7, bx_h,
         "Reach truck drives over,\nlifts and lowers the pallet;\n"
         "operator may have to wait", c=C_RT, fs=10)

    # join
    for xx in (1.7, 5.0, 8.3):
        _arrow(ax, xx, bx_y, xx, 3.7)
    ax.plot([1.7, 8.3], [3.7, 3.7], color="#333", linewidth=1.4)
    _arrow(ax, 5, 3.7, 5, 3.35)

    # 4 — deliver
    _box(ax, 2.35, 2.5, 5.3, 0.85,
         "Operator completes the kit and delivers it\n"
         "to the production line's kitting point", fs=11)
    _arrow(ax, 5, 2.5, 5, 1.95)

    # 5 — record
    _box(ax, 2.35, 1.1, 5.3, 0.85,
         "Lead time, waiting times, walking distance\n"
         "and equipment utilisation are recorded", c=C_BOOK, fs=11)
    _arrow(ax, 5, 1.1, 5, 0.65)

    # 6 — loop
    _box(ax, 2.85, 0.0, 4.3, 0.65,
         "Next order, five working days,\nrepeated over 20 independent runs",
         c=C_BOOK, fs=10, bold=True)

    # horizontal strip below the loop box — keeps the diagram body clear
    _legend_strip(ax, -0.85, fs=9)

    fig.savefig(OUT_SIMPLE, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {OUT_SIMPLE}")


def build_detailed():
    fig, ax = plt.subplots(figsize=(12, 16))
    ax.set_xlim(-0.4, 11)
    ax.set_ylim(-0.4, 16)
    ax.axis("off")

    ax.text(5.3, 15.6, "Order lifecycle, one pass through the simulation",
            ha="center", fontsize=14, fontweight="bold")
    ax.text(5.3, 15.15,
            "(order stream fitted to the ZWM92 dispatch log; "
            "operators, reach trucks and Kardex units are limited resources)",
            ha="center", fontsize=10, style="italic", color="#555")

    # Source / sampling block
    _box(ax, 0.6, 13.3, 9.4, 1.45,
         "Order generator: every quantity sampled from fitted distributions:\n"
         "production line (categorical)  ·  materials in the kit (per-line categorical)\n"
         "kit size (empirical BOM sizes)  ·  time between batches (empirical, mean 5.36 min)\n"
         "orders per batch (empirical, mean 4.68)",
         c=C_INPUT, fs=10, bold=True)
    _arrow(ax, 5.3, 13.3, 5.3, 12.75)
    _box(ax, 3.55, 12.1, 3.5, 0.65, "Wait until the next batch arrives", c=C_BOOK)
    _arrow(ax, 5.3, 12.1, 5.3, 11.6)

    # Per-item loop start
    _box(ax, 1.8, 10.8, 7.0, 0.8,
         "For each material in the kit:\nlook up the bin assigned by the slotting policy",
         bold=True)
    _arrow(ax, 5.3, 10.8, 5.3, 10.25)

    # Decision: Kardex?
    _diamond(ax, 3.4, 8.85, 3.8, 1.4, "Material stored in\nthe Kardex system?")
    _arrow(ax, 7.2, 9.55, 8.7, 9.55, label="yes", dx=-0.9)
    _box(ax, 8.7, 9.2, 2.0, 0.7, "Wait for one of the\n4 Kardex units", c=C_KDX)
    _arrow(ax, 9.7, 9.2, 9.7, 8.2)
    _box(ax, 8.7, 7.5, 2.0, 0.7, "Carousel turns,\noperator picks\n(lognormal time)",
         c=C_KDX, fs=9)
    _arrow(ax, 9.7, 7.5, 9.7, 4.3)
    ax.text(9.8, 5.8, "rejoin", fontsize=9, color="#333")

    _arrow(ax, 5.3, 8.85, 5.3, 8.35, label="no")

    # Decision: hand-reachable & corridor side?
    _diamond(ax, 3.2, 6.7, 4.2, 1.5,
             "Low level, reachable\nfrom the kit corridor?")
    _arrow(ax, 5.3, 6.7, 5.3, 6.2, label="yes, operator only")
    _arrow(ax, 3.2, 7.45, 2.0, 7.45, label="no", dx=-0.55)

    # Operator-only path
    _box(ax, 3.55, 5.35, 3.5, 0.8,
         "Wait for one of the 8 operators;\nwalk to the bin and pick", c=C_OP)
    _arrow(ax, 5.3, 5.35, 5.3, 4.3)

    # RT branch
    _box(ax, 0.35, 6.0, 3.0, 0.75,
         "Wait for one of the 7 reach\ntrucks; truck drives from depot", c=C_RT)
    _arrow(ax, 1.85, 7.45, 1.85, 6.75)
    _arrow(ax, 1.85, 6.0, 1.85, 5.35)
    _box(ax, 0.35, 4.6, 3.0, 0.75,
         "Truck lifts to the level and\nhands the pallet down (lognormal)", c=C_RT)
    ax.text(0.35, 4.32,
            "after the drop the truck drives back to the depot\n"
            "(it stays busy and unavailable on the way home)",
            fontsize=8, color="#A85811", va="top")
    _arrow(ax, 1.85, 4.6, 1.85, 3.6)
    _arrow(ax, 1.85, 3.6, 4.1, 3.6)

    # Common rejoin
    _arrow(ax, 5.3, 4.3, 5.3, 3.95)
    _box(ax, 4.1, 3.25, 2.4, 0.7,
         "Free the pallet position\n(one picker at a time)", c=C_BOOK, fs=9)
    _arrow(ax, 9.7, 4.3, 9.7, 3.6)
    _arrow(ax, 9.7, 3.6, 6.5, 3.6)
    _arrow(ax, 5.3, 3.25, 5.3, 2.85)

    # End-of-order
    _box(ax, 3.3, 2.1, 4.0, 0.75,
         "Walk the finished kit to the\nproduction line's kitting point", bold=True)
    _arrow(ax, 5.3, 2.1, 5.3, 1.7)
    _box(ax, 2.8, 0.95, 5.0, 0.75,
         "Record the order's KPIs: preparation time, lead time,\n"
         "walking distance, operator and truck waiting times", c=C_BOOK, fs=9.5)
    _arrow(ax, 5.3, 0.95, 5.3, 0.55)
    _box(ax, 3.55, -0.15, 3.5, 0.7,
         "Next batch, until the five-day\nsimulated period ends", c=C_BOOK, bold=True, fs=9.5)

    _legend(ax, 8.6, 1.9, fs=9)

    fig.savefig(OUT_DETAIL, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {OUT_DETAIL}")


if __name__ == "__main__":
    os.makedirs("output", exist_ok=True)
    build_simple()
    build_detailed()
    shutil.copyfile(OUT_DETAIL, OUT_LEGACY)
    print(f"Wrote {OUT_LEGACY} (copy of detailed)")
