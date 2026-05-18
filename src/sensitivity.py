"""One-at-a-time (OAT) sensitivity analysis on the placeholder constants.

For each input below, we re-run the Heuristic policy with the input set
to its low and high value (±20% from the baseline) while everything else
stays at the default, then compare to the baseline KPI mean. The output
is a tornado plot per KPI showing which inputs swing it the most.

Why this matters for the report: the timing constants in src/config.py
are educated guesses pending the May-20 time-study. Sensitivity tells us
which ones to measure precisely (high-impact) vs which can stay rough
(low-impact). Result feeds Section C priorities in the site-visit doc.

Run:
    python -m src.sensitivity

Output:
    output/sensitivity.json
    output/sensitivity_tornado_<kpi>.png  (one per tracked KPI)
"""

import copy
import json
import os
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src import config
from src.data_loader import preprocess
from src.main import run_policy
from src.slotting import HeuristicBaselinePolicy


# --- What to vary ------------------------------------------------------------
# Each entry: (attr_name, baseline, low, high, human_label).
# ±20% by default; manual override where ±20% is uninformative.
INPUTS = [
    ("OPERATOR_WALK_SPEED_M_PER_MIN",   50.0,  40.0, 60.0, "Operator walk speed"),
    ("REACH_TRUCK_SPEED_M_PER_MIN",     100.0, 80.0, 120.0, "Reach-truck speed"),
    ("REACH_TRUCK_LIFT_TIME_PER_LEVEL", 0.25,  0.20, 0.30, "RT lift time / level"),
    ("REACH_TRUCK_PICK_PLACE_TIME",     0.5,   0.4,  0.6,  "RT pick+place time"),
    ("OPERATOR_PICK_TIME",              0.3,   0.24, 0.36, "Operator pick time"),
    ("KARDEX_PICK_TIME",                0.5,   0.4,  0.6,  "Kardex pick time"),
    ("KARDEX_CAROUSEL_TIME",            0.4,   0.32, 0.48, "Kardex carousel time"),
    ("ORDERS_PER_DAY",                  300,   240,  360,  "Orders / day"),
]

# Which KPIs to track in the tornado. Reading from main._aggregate_summaries
# output names.
KPI_KEYS = [
    ("avg_lead_time",     "Avg lead time (min/order)", "lower"),
    ("avg_walk_distance", "Avg walk distance (m/order)", "lower"),
    ("orders_completed",  "Orders completed",          "higher"),
    ("reach_truck_utilization", "RT utilization",     "higher"),
]

# Reps per sensitivity run. Lower than the headline N=30 to stay tractable
# (we run 1 + 2*len(INPUTS) configs = 17 configs).
N_SENS_REPS = 5


def _capture_baseline():
    return {attr: getattr(config, attr) for (attr, *_rest) in INPUTS}


def _restore(baseline_snapshot):
    for k, v in baseline_snapshot.items():
        setattr(config, k, v)


def _run_one(data, label):
    """One full Heuristic run with the current config attributes."""
    aggregate, _kpi, _wh, _reps = run_policy(
        f"  [sens] {label}",
        HeuristicBaselinePolicy,
        data,
        n_reps=N_SENS_REPS,
    )
    return {k: aggregate.get(k) for (k, *_rest) in KPI_KEYS}


def collect_sensitivity():
    print(f"Sensitivity: preprocessing...")
    data = preprocess()
    snapshot = _capture_baseline()

    print(f"Sensitivity: running BASELINE (default config) "
          f"with {N_SENS_REPS} reps...")
    _restore(snapshot)
    baseline = _run_one(data, "baseline")

    results = {"baseline": baseline, "perturbations": {}}
    for (attr, base_val, lo, hi, label) in INPUTS:
        print(f"\nSensitivity: varying {label} ({attr})")
        runs = {}
        for level_name, level_val in [("low", lo), ("high", hi)]:
            _restore(snapshot)
            setattr(config, attr, level_val)
            print(f"  {level_name}: {attr}={level_val}")
            runs[level_name] = {
                "value": level_val,
                "kpis": _run_one(data, f"{label}={level_val}"),
            }
        runs["low"]["delta_pct"] = {
            k: _delta_pct(runs["low"]["kpis"].get(k), baseline.get(k))
            for (k, *_rest) in KPI_KEYS
        }
        runs["high"]["delta_pct"] = {
            k: _delta_pct(runs["high"]["kpis"].get(k), baseline.get(k))
            for (k, *_rest) in KPI_KEYS
        }
        results["perturbations"][attr] = {
            "label": label,
            "baseline_value": base_val,
            "low_value": lo,
            "high_value": hi,
            "runs": runs,
        }

    _restore(snapshot)
    return results


def _delta_pct(val, base):
    if val is None or base is None or base == 0:
        return None
    return 100.0 * (val - base) / base


def _tornado_rows(results, kpi_key):
    """For each input, the |max-min| swing in the KPI as a % of baseline."""
    rows = []
    for attr, pert in results["perturbations"].items():
        lo_d = pert["runs"]["low"]["delta_pct"].get(kpi_key)
        hi_d = pert["runs"]["high"]["delta_pct"].get(kpi_key)
        if lo_d is None or hi_d is None:
            continue
        swing = abs(hi_d - lo_d)
        rows.append({
            "attr": attr,
            "label": pert["label"],
            "low_delta_pct": lo_d,
            "high_delta_pct": hi_d,
            "swing_pct": swing,
        })
    rows.sort(key=lambda r: r["swing_pct"], reverse=True)
    return rows


def plot_tornado(results, kpi_key, kpi_label, out_path):
    rows = _tornado_rows(results, kpi_key)
    if not rows:
        return
    labels = [r["label"] for r in rows]
    lows = [r["low_delta_pct"] for r in rows]
    highs = [r["high_delta_pct"] for r in rows]

    fig, ax = plt.subplots(figsize=(9, 0.55 * len(rows) + 1.2))
    y = list(range(len(rows)))[::-1]  # widest at top
    for i, (lo, hi, yi) in enumerate(zip(lows, highs, y)):
        lo_color = "#ef5350" if lo < 0 else "#66bb6a"
        hi_color = "#ef5350" if hi < 0 else "#66bb6a"
        ax.barh(yi, lo, color=lo_color, alpha=0.75,
                edgecolor="#222", linewidth=0.6)
        ax.barh(yi, hi, color=hi_color, alpha=0.75,
                edgecolor="#222", linewidth=0.6)
        ax.text(lo, yi, f" {lo:+.1f}% ", ha="right" if lo < 0 else "left",
                va="center", fontsize=8, color="#222")
        ax.text(hi, yi, f" {hi:+.1f}% ", ha="right" if hi < 0 else "left",
                va="center", fontsize=8, color="#222")

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.axvline(0, color="#222", linewidth=1.0)
    ax.set_xlabel(f"% change in {kpi_label} from baseline (±20% input swing)")
    ax.set_title(f"Tornado — {kpi_label}\n"
                 f"(OAT sensitivity, Heuristic policy, {N_SENS_REPS} reps per cell)")
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"  wrote {out_path}")


def write_text_report(results, path):
    lines = ["Sensitivity (OAT) report", "=" * 60, ""]
    lines.append(f"Baseline KPI means (Heuristic, {N_SENS_REPS} reps):")
    for (k, label, _dir) in KPI_KEYS:
        v = results["baseline"].get(k)
        if v is not None:
            lines.append(f"  {label:40s} = {v:.3f}")
    lines.append("")
    for (k, label, _dir) in KPI_KEYS:
        lines.append(f"--- {label} — input swings (ranked) ---")
        for r in _tornado_rows(results, k):
            lines.append(
                f"  {r['label']:30s}  low={r['low_delta_pct']:+6.2f}%  "
                f"high={r['high_delta_pct']:+6.2f}%  "
                f"swing={r['swing_pct']:6.2f}%"
            )
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    os.makedirs("output", exist_ok=True)
    results = collect_sensitivity()
    with open("output/sensitivity.json", "w") as f:
        json.dump(results, f, indent=2)
    write_text_report(results, "output/sensitivity.txt")
    for (k, label, _dir) in KPI_KEYS:
        plot_tornado(results, k, label,
                     f"output/sensitivity_tornado_{k}.png")
    print("\nDone. See output/sensitivity.{json,txt} and tornado PNGs.")


if __name__ == "__main__":
    main()
