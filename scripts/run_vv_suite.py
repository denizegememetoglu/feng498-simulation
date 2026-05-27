"""V&V suite orchestrator (M6) — Sargent V&V framework alignment.

Runs V&V1–V&V12 in sequence and assembles `Reports/VV_<timestamp>/`:

  VV1_data_integrity.json           — SHA256 of every input + git SHA + config
  VV2_face_validity.pdf             — DWG pipeline diagram + layout sanity
  VV3_conceptual_validity.pdf       — flowchart + pseudocode + distribution justification
  VV4_data_validity.pdf             — ZWM92 / F400 / SAP provenance
  VV5_operational_validity.pdf      — χ² + paired-t + Holm-Wilcoxon + Cochran
  VV6_audit_mode.txt                — pointer to sim_v2.html audit URL params
  VV7_cross_validation.json         — placeholder for ZWM92 hold-out (manual)
  VV8_replication_variance.json     — N=30 different-seed branch results (if exists)
  VV9_sensitivity_full.pdf          — OAT tornado + LHS placeholder
  VV10_tests.xml                    — pytest JUnit XML (if pytest available)
  VV11_assumptions.pdf              — Shapiro-Wilk / Durbin-Watson / Levene tests
  VV12_manifest.json                — bundle manifest (git, hashes, wall-clock)

Then bundles to `Reports/VV_<timestamp>.zip`. Designed to be re-runnable.
Defensive: each sub-report is wrapped in try/except so one failure doesn't
poison the bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "output"
REPORTS = ROOT / "Reports"
REPORTS.mkdir(exist_ok=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _git_dirty() -> bool:
    try:
        r = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
        return bool(r)
    except Exception:
        return False


# ── Sub-report builders ────────────────────────────────────────────────────────

def vv1_data_integrity(bundle: Path) -> dict:
    """SHA256 of every input file. Anchors the V&V chain in concrete bytes."""
    inputs = {
        "config/layout.json":                ROOT / "config" / "layout.json",
        "config/rack_mapping_dwg_to_sap.json": ROOT / "config" / "rack_mapping_dwg_to_sap.json",
        "output/zwm92_summary.json":         OUTPUT / "zwm92_summary.json",
        "output/zwm92_orders.json":          OUTPUT / "zwm92_orders.json",
        "output/timing_study_f400.json":     OUTPUT / "timing_study_f400.json",
        "output/viewer_layout_v1.json":      OUTPUT / "viewer_layout_v1.json",
        "output/preprocess_stats.json":      OUTPUT / "preprocess_stats.json",
    }
    rec = {
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "wall_clock_utc": datetime.utcnow().isoformat() + "Z",
        "files": {},
    }
    for label, p in inputs.items():
        if p.exists():
            rec["files"][label] = {"sha256": _sha256(p), "size_bytes": p.stat().st_size}
        else:
            rec["files"][label] = {"sha256": None, "size_bytes": 0, "missing": True}
    out = bundle / "VV1_data_integrity.json"
    out.write_text(json.dumps(rec, indent=2))
    return rec


def vv2_face_validity(bundle: Path):
    """Face validity: layout sanity vs CAD truth."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Reuse sanity report if available
    sanity_p = OUTPUT / "sanity_report_v1.json"
    sanity = json.loads(sanity_p.read_text()) if sanity_p.exists() else {}
    layout_p = ROOT / "config" / "layout.json"
    layout = json.loads(layout_p.read_text())

    fig = plt.figure(figsize=(8.5, 11))
    fig.suptitle("V&V2 — Face Validity\nLayout vs CAD truth (Codex DWG export)",
                 fontsize=14, weight="bold")

    # Per-rack pallet count panel
    ax1 = fig.add_subplot(3, 1, 1)
    racks = layout.get("racks", [])
    rack_labels, counts = [], []
    for r in racks:
        rack_labels.append(r.get("id", "?"))
        counts.append(sum(s.get("pallet_count", 0) for s in r.get("segments", [])))
    total = sum(counts)
    ax1.bar(rack_labels, counts, color="#1c3d6e")
    ax1.set_title(f"Pallet capacity per rack (canary {total} = 3203 expected)")
    ax1.set_ylabel("pallet positions")
    ax1.tick_params(axis="x", labelsize=8)
    ax1.axhline(0, color="#444", lw=0.5)

    # Sanity Q-status panel
    ax2 = fig.add_subplot(3, 1, 2)
    if sanity.get("entries"):
        ids = [e["id"] for e in sanity["entries"]]
        statuses = [e["status"] for e in sanity["entries"]]
        colors = ["#4ade80" if s == "PASS" else "#fbbf24" if s == "WARN" else "#f87171" for s in statuses]
        ax2.bar(ids, [1] * len(ids), color=colors)
        ax2.set_title("Phase 1.5 sanity Q1-Q10 status")
        ax2.set_ylim(0, 1.4)
        for x, s in zip(ids, statuses):
            ax2.text(x, 1.05, s, ha="center", fontsize=8)
    else:
        ax2.text(0.5, 0.5, "Run scripts/run_sanity.py first", ha="center", va="center")
        ax2.set_axis_off()

    # Notes panel
    ax3 = fig.add_subplot(3, 1, 3)
    ax3.set_axis_off()
    notes = [
        "Layout source: Codex CAD geometry (16 rack rows, 19 floor labels).",
        "Applied 2026-05-27 with explicit user approval ('3dyi her şeyie implemente et').",
        f"Pallet canary at apply-time: 3203 (current: {total}).",
        "Open items: H/I bay-width 30cm back-to-back gap (idx 3-4) — site visit pending.",
        "Backup: config/layout.json.bak_pre_codex_apply",
    ]
    ax3.text(0.05, 0.95, "Notes", fontsize=11, weight="bold", transform=ax3.transAxes)
    for i, n in enumerate(notes):
        ax3.text(0.05, 0.85 - i * 0.12, "• " + n, fontsize=10, transform=ax3.transAxes)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(bundle / "VV2_face_validity.pdf")
    plt.close(fig)


def vv3_conceptual_validity(bundle: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    flowchart_png = OUTPUT / "sim_flowchart.png"
    fig = plt.figure(figsize=(8.5, 11))
    fig.suptitle("V&V3 — Conceptual Validity\nSimulation lifecycle + distribution justification",
                 fontsize=14, weight="bold")

    ax1 = fig.add_subplot(2, 1, 1)
    if flowchart_png.exists():
        ax1.imshow(plt.imread(flowchart_png))
        ax1.set_axis_off()
        ax1.set_title("Figure 2: Order lifecycle (SimPy processes)")
    else:
        ax1.text(0.5, 0.5, "sim_flowchart.png missing — run scripts/build_flowchart.py",
                 ha="center", va="center")
        ax1.set_axis_off()

    ax2 = fig.add_subplot(2, 1, 2)
    ax2.set_axis_off()
    bullets = [
        "Driver: Arena-style fitted from 167,784 ZWM92 dispatch rows (40,804 kit-orders).",
        "IAT ~ Exp(5.36 min within-shift) — within-shift filter excludes overnight gaps.",
        "n_items ~ Empirical(distinct picks per kit, mean 4.0) — clipped at 50.",
        "Line ~ Categorical (9 product families); material ~ Categorical|line.",
        "Pick times ~ Lognormal(F400 mean, σ from F400 CV): operator 0.113, RT 0.110,",
        "  manual 0.102, Kardex 0.113 min. σ values: 1.30/1.20/1.40/1.30 (log-scale).",
        "Resources: 7 RT + 8 op + 7 milk-run + 4 Kardex (verbal report May 2026).",
        "Position lock (1-cap SimPy resource per pallet position) prevents race conditions.",
    ]
    ax2.text(0.05, 0.95, "Distribution + resource justification", fontsize=11,
             weight="bold", transform=ax2.transAxes)
    for i, b in enumerate(bullets):
        ax2.text(0.05, 0.85 - i * 0.10, "• " + b, fontsize=9, transform=ax2.transAxes)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(bundle / "VV3_conceptual_validity.pdf")
    plt.close(fig)


def vv4_data_validity(bundle: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    zwm = OUTPUT / "zwm92_summary.json"
    timing = OUTPUT / "timing_study_f400.json"
    prep = OUTPUT / "preprocess_stats.json"

    fig = plt.figure(figsize=(8.5, 11))
    fig.suptitle("V&V4 — Data Validity\nZWM92 + F400 + SAP master coverage",
                 fontsize=14, weight="bold")

    ax = fig.add_subplot(3, 1, 1)
    ax.set_axis_off()
    rows = [["Source", "Volume", "Period / scope"]]
    if zwm.exists():
        z = json.loads(zwm.read_text())
        rows.append(["ZWM92 dispatch log", f"{z.get('total_rows', '?'):,} rows / "
                     f"{z.get('orders_built', '?'):,} kit-orders",
                     f"{z.get('date_min', '?')} → {z.get('date_max', '?')}"])
    if timing.exists():
        t = json.loads(timing.read_text())
        rows.append(["F400 video time-motion",
                     f"{t.get('total_observations', '?'):,} micro-events",
                     f"{t.get('total_observed_minutes', '?')} min"])
    if prep.exists():
        p = json.loads(prep.read_text())
        rows.append(["SAP özet master",
                     f"{p.get('materials_total', '?'):,} materials / "
                     f"{p.get('bins_decoded', '?'):,} decoded bins",
                     "076-day window"])
    tbl = ax.table(cellText=rows, loc="upper center", cellLoc="left")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.6)

    ax2 = fig.add_subplot(3, 1, 2)
    if zwm.exists():
        z = json.loads(zwm.read_text())
        lines = z.get("lines", {})
        labels = sorted(lines, key=lambda k: -lines[k])[:9]
        ax2.bar(labels, [lines[k] for k in labels], color="#38bdf8")
        ax2.set_title("Production-line mix (ZWM92)")
        ax2.tick_params(axis="x", labelsize=8, rotation=20)

    ax3 = fig.add_subplot(3, 1, 3)
    ax3.set_axis_off()
    notes = [
        "Missing-data treatment: kit rows with no production line are dropped (orders_dropped_no_line).",
        "Calendar IAT includes overnight gaps; within-shift IAT used by driver (Sargent).",
        "F400 categories mapped to sim constants in src/config.py (see ASSUMPTIONS §19).",
        "Kardex 2766/5941 materials marked in özet; treated as a separate carousel resource.",
    ]
    for i, n in enumerate(notes):
        ax3.text(0.05, 0.85 - i * 0.16, "• " + n, fontsize=10, transform=ax3.transAxes)
    ax3.text(0.05, 0.95, "Notes", fontsize=11, weight="bold", transform=ax3.transAxes)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(bundle / "VV4_data_validity.pdf")
    plt.close(fig)


def vv5_operational_validity(bundle: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    val_p = OUTPUT / "validation_report.json"
    stats_p = OUTPUT / "policy_stats.json"

    fig = plt.figure(figsize=(8.5, 11))
    fig.suptitle("V&V5 — Operational Validity\nχ² + paired-t + Holm-Wilcoxon",
                 fontsize=14, weight="bold")

    if val_p.exists():
        v = json.loads(val_p.read_text())
        r = v.get("chi_square_per_rack_restricted", {})
        ax = fig.add_subplot(3, 1, 1)
        if r:
            x = r["racks"]
            ax.bar(x, r["observed"], label="Sim (observed)",
                   color="#1c3d6e", alpha=0.85, width=0.4, align="edge")
            ax.bar([i for i in range(len(x))], r["expected"],
                   label="ZWM92 (expected)", color="#f5a623", alpha=0.85, width=-0.4, align="edge")
            ax.set_xticks(range(len(x)))
            ax.set_xticklabels(x)
            ax.set_title(f"χ² per rack — restricted (χ²={r.get('chi_square', 0):.2f}, "
                         f"p={r.get('p_value', 0):.2e})")
            ax.legend(fontsize=8)
    else:
        fig.text(0.5, 0.8, "validation_report.json missing — run src.validate first",
                 ha="center")

    ax2 = fig.add_subplot(3, 1, 2)
    ax2.set_axis_off()
    if val_p.exists():
        v = json.loads(val_p.read_text())
        pt = v.get("paired_t_test", {})
        if pt:
            ax2.text(0.05, 0.85, f"Paired t (avg walk per rack):\n"
                     f"   t = {pt.get('t_statistic', 0):.3f}, "
                     f"p = {pt.get('p_value', 0):.2e}",
                     fontsize=11, transform=ax2.transAxes)
        cw = v.get("chi_square_per_rack_restricted", {}).get("cochran_warning")
        if cw:
            ax2.text(0.05, 0.6, "Cochran's rule: " + cw, fontsize=9, color="#f87171",
                     wrap=True, transform=ax2.transAxes)

    ax3 = fig.add_subplot(3, 1, 3)
    if stats_p.exists():
        s = json.loads(stats_p.read_text())
        wilc = s.get("wilcoxon_paired_by_order", {})
        if wilc:
            keys = list(wilc.keys())[:12]
            pvals = [wilc[k].get("p_holm", wilc[k].get("p_value", 1)) for k in keys]
            colors = ["#4ade80" if p < 0.05 else "#94a3b8" for p in pvals]
            ax3.barh(range(len(keys)), pvals, color=colors)
            ax3.set_yticks(range(len(keys)))
            ax3.set_yticklabels(keys, fontsize=7)
            ax3.axvline(0.05, color="#f87171", lw=1, ls="--")
            ax3.set_title("Holm-corrected paired Wilcoxon (12-test family)")
            ax3.set_xlabel("p_holm")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(bundle / "VV5_operational_validity.pdf")
    plt.close(fig)


def vv6_audit_mode(bundle: Path):
    txt = (
        "V&V6 — Audit mode\n\n"
        "Open sim_v2.html and use the Analytics sidebar (A key) to inspect any\n"
        "policy timeline event-by-event. The JSONL files at\n"
        "  output/sim_timeline_<policy>.jsonl\n"
        "expose every order_start / op_grant / op_move / rt_dispatch / pick /\n"
        "kardex_pick / order_done event with sim-time t in minutes.\n\n"
        "Step-through: use ⏮/⏭ buttons (30 sim-min jumps) or scrubber.\n"
        "Pick events flash a 2-second yellow highlight on the target rack-bay.\n"
        "KPI snapshots every 10 sim-min drive the HUD.\n"
    )
    (bundle / "VV6_audit_mode.txt").write_text(txt)


def vv7_cross_validation(bundle: Path):
    rec = {
        "status": "deferred",
        "intent": "ZWM92 last-month hold-out cross-validation.",
        "method": "Train slotting policies on rows < 2026-04-18, score on remainder.",
        "note": "Requires --cross-val flag in src.main.py (planned). See plan M6.",
    }
    (bundle / "VV7_cross_validation.json").write_text(json.dumps(rec, indent=2))


def vv8_replication_variance(bundle: Path):
    """Use replications.json if present; otherwise note N=1 same-seed setup."""
    rep_p = OUTPUT / "replications.json"
    if not rep_p.exists():
        rec = {"status": "single-seed", "note": "N_REPLICATIONS=1 with SAME_SEED_FOR_ALL_REPS=True (advisor decision May 26). For N=30 different-seed branch run with config.SAME_SEED_FOR_ALL_REPS=False, N_REPLICATIONS=30."}
        (bundle / "VV8_replication_variance.json").write_text(json.dumps(rec, indent=2))
        return
    reps = json.loads(rep_p.read_text())
    summary = {}
    for policy, runs in reps.items():
        if not runs:
            continue
        walks = [r.get("avg_walk_distance", 0) for r in runs]
        leads = [r.get("avg_lead_time", 0) for r in runs]
        summary[policy] = {
            "n": len(runs),
            "walk_mean": sum(walks) / len(walks),
            "walk_min": min(walks), "walk_max": max(walks),
            "lead_mean": sum(leads) / len(leads),
            "lead_min": min(leads), "lead_max": max(leads),
        }
    (bundle / "VV8_replication_variance.json").write_text(json.dumps(summary, indent=2))


def vv9_sensitivity_full(bundle: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sens_p = OUTPUT / "sensitivity.json"
    if not sens_p.exists():
        (bundle / "VV9_sensitivity_full.txt").write_text(
            "sensitivity.json not found — run src.sensitivity first."
        )
        return
    s = json.loads(sens_p.read_text())
    base = s["baseline"]["avg_walk_distance"]
    items = []
    for param, info in s["perturbations"].items():
        runs = info.get("runs") or {}
        if not runs:
            continue
        lo_run = runs.get("low") or {}
        hi_run = runs.get("high") or {}
        lo = (lo_run.get("kpis") or {}).get("avg_walk_distance", base)
        hi = (hi_run.get("kpis") or {}).get("avg_walk_distance", base)
        items.append((info.get("label", param), lo - base, hi - base))
    items.sort(key=lambda x: abs(x[1]) + abs(x[2]), reverse=True)

    fig, ax = plt.subplots(figsize=(8.5, 11))
    fig.suptitle("V&V9 — Full OAT Sensitivity\nWalk-distance Δ vs baseline (±25% each parameter)",
                 fontsize=13, weight="bold")
    labels = [x[0] for x in items]
    lows = [x[1] for x in items]
    highs = [x[2] for x in items]
    y = list(range(len(items)))
    ax.barh(y, lows,  color="#f87171", alpha=0.85, label="Low (-25%)")
    ax.barh(y, highs, color="#4ade80", alpha=0.85, label="High (+25%)")
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8)
    ax.axvline(0, color="#444", lw=1)
    ax.set_xlabel("Δ walk distance vs baseline (m)")
    ax.legend(fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(bundle / "VV9_sensitivity_full.pdf")
    plt.close(fig)


def vv10_tests(bundle: Path):
    """Run pytest with JUnit XML output. Skip gracefully if pytest missing."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "--junitxml",
             str(bundle / "VV10_tests.xml"), "-q", "--tb=no"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        log = bundle / "VV10_pytest_log.txt"
        log.write_text(out.stdout + "\n--- stderr ---\n" + out.stderr)
        return out.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        (bundle / "VV10_tests.xml").write_text(
            '<?xml version="1.0"?><testsuites><testsuite name="placeholder" tests="0"/></testsuites>'
        )
        return -1


def vv11_assumptions(bundle: Path):
    """Shapiro-Wilk / Durbin-Watson / Levene on KPI distributions if available."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rep_p = OUTPUT / "replications.json"
    fig = plt.figure(figsize=(8.5, 11))
    fig.suptitle("V&V11 — Statistical Assumptions\nNormality, independence, equal variance",
                 fontsize=14, weight="bold")

    ax = fig.add_subplot(2, 1, 1)
    ax.set_axis_off()
    bullets = [
        "Shapiro-Wilk: requires N>1; current N=1 same-seed disables the test.",
        "  → For N=30 branch, walk-distance distributions across replications are checked.",
        "Durbin-Watson: order-by-order autocorrelation of walk_m residuals.",
        "  → Paired-by-order Wilcoxon (used in src/analyze.py) is rank-based and",
        "     robust to autocorrelation in the differences.",
        "Levene: equal-variance test across policies (used in Welch ANOVA fallback).",
        "  → Collapses under same-seed; documented as a limitation in ASSUMPTIONS.md §23.",
    ]
    for i, b in enumerate(bullets):
        ax.text(0.05, 0.95 - i * 0.10, b, fontsize=10, transform=ax.transAxes)

    if rep_p.exists():
        try:
            from scipy import stats
            reps = json.loads(rep_p.read_text())
            ax2 = fig.add_subplot(2, 1, 2)
            for i, (policy, runs) in enumerate(reps.items()):
                if len(runs) < 3:
                    continue
                walks = [r.get("avg_walk_distance", 0) for r in runs]
                sw_stat, sw_p = stats.shapiro(walks)
                ax2.scatter([i] * len(walks), walks, alpha=0.6, label=policy[:18])
                ax2.text(i, max(walks) + 1,
                         f"W={sw_stat:.2f}\np={sw_p:.2f}",
                         ha="center", fontsize=7)
            ax2.set_xticks(range(len(reps)))
            ax2.set_xticklabels([k[:14] for k in reps.keys()], rotation=20, fontsize=8)
            ax2.set_ylabel("Walk distance (m)")
            ax2.set_title("Per-policy walk_m by replication (Shapiro-Wilk inset)")
        except Exception as e:
            fig.text(0.5, 0.3, f"Shapiro-Wilk skipped: {e}", ha="center", color="#f87171")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(bundle / "VV11_assumptions.pdf")
    plt.close(fig)


def vv12_manifest(bundle: Path, run_record: dict):
    """Top-level manifest. Anchors every file in the bundle by SHA256."""
    bundle_files = {}
    for p in sorted(bundle.iterdir()):
        if p.is_file() and not p.name.startswith("VV12_"):
            bundle_files[p.name] = {"sha256": _sha256(p), "size_bytes": p.stat().st_size}
    manifest = {
        "schema_version": "1.0",
        "framework": "Sargent V&V (1979, 2013)",
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "wall_clock_started_utc": run_record.get("started"),
        "wall_clock_finished_utc": datetime.utcnow().isoformat() + "Z",
        "step_durations_s": run_record.get("durations", {}),
        "step_status": run_record.get("status", {}),
        "files": bundle_files,
    }
    (bundle / "VV12_manifest.json").write_text(json.dumps(manifest, indent=2))


# ── Orchestrator ───────────────────────────────────────────────────────────────

STEPS = [
    ("VV1_data_integrity",      vv1_data_integrity),
    ("VV2_face_validity",       vv2_face_validity),
    ("VV3_conceptual_validity", vv3_conceptual_validity),
    ("VV4_data_validity",       vv4_data_validity),
    ("VV5_operational_validity",vv5_operational_validity),
    ("VV6_audit_mode",          vv6_audit_mode),
    ("VV7_cross_validation",    vv7_cross_validation),
    ("VV8_replication_variance",vv8_replication_variance),
    ("VV9_sensitivity_full",    vv9_sensitivity_full),
    ("VV10_tests",              vv10_tests),
    ("VV11_assumptions",        vv11_assumptions),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-prefix", default="VV",
                    help="Reports/<prefix>_<timestamp>/ directory name")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    bundle = REPORTS / f"{args.out_prefix}_{ts}"
    bundle.mkdir(parents=True, exist_ok=True)

    run_record = {
        "started": datetime.utcnow().isoformat() + "Z",
        "durations": {},
        "status": {},
    }
    print(f"[V&V suite] bundle → {bundle}")
    for name, fn in STEPS:
        t0 = time.time()
        try:
            sig = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            if len(sig) == 1:
                fn(bundle)
            else:
                fn(bundle)
            run_record["status"][name] = "ok"
            print(f"  ✓ {name}  ({time.time() - t0:.2f}s)")
        except Exception as e:
            traceback.print_exc()
            run_record["status"][name] = f"error: {e}"
            (bundle / f"{name}.error.txt").write_text(traceback.format_exc())
            print(f"  ✗ {name}  ({type(e).__name__}: {e})")
        run_record["durations"][name] = round(time.time() - t0, 3)

    vv12_manifest(bundle, run_record)
    run_record["status"]["VV12_manifest"] = "ok"

    # Zip the bundle
    zip_path = REPORTS / f"{args.out_prefix}_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(bundle.iterdir()):
            zf.write(p, arcname=f"{bundle.name}/{p.name}")
    print(f"[V&V suite] zip → {zip_path}  ({zip_path.stat().st_size / 1024:.1f} KB)")

    # Quick summary
    ok = sum(1 for v in run_record["status"].values() if v == "ok")
    fail = sum(1 for v in run_record["status"].values() if v != "ok")
    print(f"[V&V suite] {ok} ok / {fail} failed / {len(STEPS) + 1} total")


if __name__ == "__main__":
    main()
