"""Phase 1.5 sanity checks Q1-Q10 → output/sanity_report_v1.{json,txt}.

Each Q produces a record:
    {"id": "Q1", "title": "...", "status": "PASS|WARN|FAIL", "detail": ...}

Q1  geometry      — viewer_layout_v1.json per-rack bays/posts/levels
Q2  capacity      — config/layout.json pallet_count totals (canary 3203)
Q3  SAP join      — src.data_loader load_data().meta hard-coded targets
Q4  ZWM92 driver  — zwm92_summary.json IAT/n_items/orders_built
Q5  F400 timing   — timing_study_f400.json vs src.config constants
Q6  pipeline rerun— policy_summary.json walk/lead in plausible range
Q7  validation    — validation_report.json chi-square / Cochran
Q8  visual        — manual review marker (WARN until human signs off)
Q9  walk realism  — sim walk vs F400 corridor traversal × speed
Q10 sensitivity   — sensitivity.json monotonic response per parameter

Top-level summary: counts per status + canary lock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config as cfg

OUT_JSON = ROOT / "output" / "sanity_report_v1.json"
OUT_TXT = ROOT / "output" / "sanity_report_v1.txt"
LAYOUT_SANITY_TXT = ROOT / "output" / "layout_sanity_v1.txt"

# Targets derived from HANDOFF.md
EXPECTED_PALLET_CANARY = 3203
EXPECTED_RACK_CAPACITIES = {
    "A": 297, "B": 288, "C": 297, "D": 300, "E": 294, "F": 303, "G": 288,
    "H": 240, "I": 252, "J": 381, "U": 263,
}
PDF_BAYS_EXPECTED = {  # web/index.html PDF_BAY_OVERRIDES + small clamp
    "A": 11, "B": 11, "C": 12, "D": 12, "E": 12, "F": 12, "G": 12,
    "H": 11, "I": 11, "J": None, "U": 14,
}
EXPECTED_LEVELS = {
    "A": 9, "B": 9, "C": 9, "D": 9, "E": 9, "F": 9,
    "G": 7, "H": 7, "I": 8, "J": 8, "U": 7,
}
LOAD_DATA_TARGETS = {
    "materials_with_bin": 3804,
    "materials_with_decoded_bin": 781,
    "decoded_bin_slots_total": 833,  # decoded BIN count (CLAUDE.md: "833 decoded")
}
EXPECTED_WAREHOUSE_POSITIONS = 3137  # Warehouse._build_layout output (CLAUDE.md)
ZWM92_TARGETS = {
    "orders_built_min": 40000,
    "iat_within_shift_mean_min": 5.0, "iat_within_shift_mean_max": 6.0,
    "n_distinct_per_kit_mean_min": 3.5, "n_distinct_per_kit_mean_max": 4.5,
}
F400_TARGETS = {
    "OPERATOR_PICK_TIME": ("OPERATOR_PICK_TIME", 0.005),
    "MANUAL_PICK_TIME_PENALTY": ("MANUAL_PICK_TIME_PENALTY", 0.005),
    "REACH_TRUCK_PICK_PLACE_TIME": ("REACH_TRUCK_PICK_PLACE_TIME", 0.005),
}
KPI_RANGES = {
    "avg_walk_distance": (60.0, 100.0),
    "avg_lead_time":     (2.0, 7.0),
    "reach_truck_utilization": (0.0, 0.30),
    "operator_utilization":    (0.0, 0.30),
}


def _load_json(rel: str) -> dict:
    return json.load(open(ROOT / rel, encoding="utf-8"))


# ─── Q1 ─────────────────────────────────────────────────────────────────────
def q1_geometry() -> dict:
    layout = _load_json("output/viewer_layout_v1.json")
    issues, warns = [], []
    by_letter: dict[str, dict] = {}
    for r in layout["racks"]:
        if not r["letter"]:
            continue
        L = r["letter"]
        by_letter.setdefault(L, {"compound_rows": 0, "bays_total": 0, "levels": None})
        by_letter[L]["compound_rows"] += 1
        by_letter[L]["bays_total"] += r["bays"]
        by_letter[L]["levels"] = len(r["level_heights_cm"])
        if len(r["posts"]) != r["bays"] + 1:
            issues.append(f"idx={r['codex_idx']} {L}: posts={len(r['posts'])} ≠ bays+1={r['bays']+1}")

    for L, exp_bays in PDF_BAYS_EXPECTED.items():
        if L not in by_letter:
            issues.append(f"letter {L} missing from viewer_layout_v1")
            continue
        got = by_letter[L]["bays_total"]
        if L == "J":
            # J is compound; viewer total bays = 0+11+1+4 = 17 — informational only
            continue
        if got != exp_bays:
            issues.append(f"letter {L}: bays {got} ≠ PDF {exp_bays}")
        exp_lvls = EXPECTED_LEVELS[L]
        got_lvls = by_letter[L]["levels"]
        if got_lvls != exp_lvls:
            issues.append(f"letter {L}: levels {got_lvls} ≠ expected {exp_lvls}")

    # Also dump per-rack diagnostic to layout_sanity_v1.txt
    lines = ["# viewer_layout_v1.json per-rack diagnostic", ""]
    lines.append(f"{'idx':>3} {'L':1} {'role':30} {'dir':3} {'bays':>4} {'posts':>5} {'lvls':>4} {'pitch':>7}")
    for r in layout["racks"]:
        lines.append(
            f"{r['codex_idx']:>3} {str(r['letter']) or '-':1} {r['role']:30} {r['dir']:3} "
            f"{r['bays']:>4} {len(r['posts']):>5} {len(r['level_heights_cm']):>4} {r['bay_pitch_cm']:>7.2f}"
        )
    lines += ["", "letter aggregates (compound rows summed):"]
    for L in sorted(by_letter):
        d = by_letter[L]
        lines.append(f"  {L}: {d['compound_rows']} rows, total_bays={d['bays_total']}, levels={d['levels']}")
    LAYOUT_SANITY_TXT.write_text("\n".join(lines), encoding="utf-8")

    status = "FAIL" if issues else ("WARN" if warns else "PASS")
    return {"id": "Q1", "title": "Geometry sanity (viewer_layout_v1)",
            "status": status, "issues": issues, "warns": warns,
            "by_letter": by_letter}


# ─── Q2 ─────────────────────────────────────────────────────────────────────
def q2_capacity() -> dict:
    layout = _load_json("config/layout.json")
    per_rack: dict[str, int] = {}
    for rack in layout["racks"]:
        rid = rack["id"]
        per_rack[rid] = sum(s["pallet_count"] for s in rack["segments"])
    total = sum(per_rack.values())
    issues = []
    if total != EXPECTED_PALLET_CANARY:
        issues.append(f"pallet canary {total} ≠ {EXPECTED_PALLET_CANARY}")
    for L, exp in EXPECTED_RACK_CAPACITIES.items():
        got = per_rack.get(L)
        if got is None:
            issues.append(f"rack {L} missing")
        elif got != exp:
            issues.append(f"rack {L}: {got} ≠ PDF {exp}")
    status = "FAIL" if issues else "PASS"
    return {"id": "Q2", "title": "Pallet capacity sanity (canary 3203)",
            "status": status, "total": total, "per_rack": per_rack, "issues": issues}


# ─── Q3 ─────────────────────────────────────────────────────────────────────
def q3_sap_join() -> dict:
    stats = _load_json("output/preprocess_stats.json")
    issues, warns = [], []
    for k, exp in LOAD_DATA_TARGETS.items():
        got = stats.get(k)
        if got != exp:
            issues.append(f"{k}: {got} ≠ {exp}")
    # Cross-check Warehouse modelled positions count (separately from preprocess bins)
    try:
        from src.warehouse import Warehouse
        wh = Warehouse()
        n_pos = len(wh.positions)
        if n_pos != EXPECTED_WAREHOUSE_POSITIONS:
            warns.append(f"warehouse.positions {n_pos} ≠ {EXPECTED_WAREHOUSE_POSITIONS}")
    except Exception as e:
        warns.append(f"Warehouse load failed: {e!r}")
        n_pos = None
    status = "FAIL" if issues else ("WARN" if warns else "PASS")
    return {"id": "Q3", "title": "SAP join coverage (preprocess + warehouse positions)",
            "status": status, "got": {k: stats.get(k) for k in LOAD_DATA_TARGETS},
            "expected": LOAD_DATA_TARGETS, "warehouse_positions": n_pos,
            "expected_warehouse_positions": EXPECTED_WAREHOUSE_POSITIONS,
            "issues": issues, "warns": warns}


# ─── Q4 ─────────────────────────────────────────────────────────────────────
def q4_zwm92() -> dict:
    s = _load_json("output/zwm92_summary.json")
    issues = []
    if s["orders_built"] < ZWM92_TARGETS["orders_built_min"]:
        issues.append(f"orders_built {s['orders_built']} < {ZWM92_TARGETS['orders_built_min']}")
    iat = s["iat_within_shift_mean"]
    if not (ZWM92_TARGETS["iat_within_shift_mean_min"] <= iat <= ZWM92_TARGETS["iat_within_shift_mean_max"]):
        issues.append(f"iat_within_shift_mean {iat:.3f} outside [5.0,6.0]")
    n = s["n_distinct_per_kit_mean"]
    if not (ZWM92_TARGETS["n_distinct_per_kit_mean_min"] <= n <= ZWM92_TARGETS["n_distinct_per_kit_mean_max"]):
        issues.append(f"n_distinct_per_kit_mean {n:.3f} outside [3.5,4.5]")
    status = "FAIL" if issues else "PASS"
    return {"id": "Q4", "title": "ZWM92 driver distributions",
            "status": status,
            "orders_built": s["orders_built"], "iat_within_shift_mean": iat,
            "n_distinct_per_kit_mean": n, "issues": issues}


# ─── Q5 ─────────────────────────────────────────────────────────────────────
def q5_f400() -> dict:
    t = _load_json("output/timing_study_f400.json")
    mapping = t.get("config_mapping", {})
    issues = []
    for name, (attr, tol) in F400_TARGETS.items():
        timing_val = mapping.get(name)
        cfg_val = getattr(cfg, attr, None)
        if timing_val is None or cfg_val is None:
            issues.append(f"{name}: timing={timing_val} cfg={cfg_val}")
            continue
        if abs(timing_val - cfg_val) > tol:
            issues.append(f"{name}: timing={timing_val} cfg={cfg_val} Δ={abs(timing_val-cfg_val):.4f}>{tol}")
    extra = {
        "KARDEX_PICK_TIME": cfg.KARDEX_PICK_TIME,
        "KARDEX_CAROUSEL_TIME": cfg.KARDEX_CAROUSEL_TIME,
    }
    status = "FAIL" if issues else "PASS"
    return {"id": "Q5", "title": "F400 timing constants vs src.config",
            "status": status, "mapping": mapping, "config_constants": {
                "OPERATOR_PICK_TIME": cfg.OPERATOR_PICK_TIME,
                "MANUAL_PICK_TIME_PENALTY": cfg.MANUAL_PICK_TIME_PENALTY,
                "REACH_TRUCK_PICK_PLACE_TIME": cfg.REACH_TRUCK_PICK_PLACE_TIME,
                **extra,
            }, "issues": issues}


# ─── Q6 ─────────────────────────────────────────────────────────────────────
def q6_pipeline() -> dict:
    p = _load_json("output/policy_summary.json")
    issues, warns = [], []
    per_policy = {}
    for name, kpi in p.items():
        rec = {k: kpi.get(k) for k in KPI_RANGES}
        per_policy[name] = rec
        for k, (lo, hi) in KPI_RANGES.items():
            v = kpi.get(k)
            if v is None:
                issues.append(f"{name}: {k} missing")
            elif not (lo <= v <= hi):
                warns.append(f"{name}: {k}={v:.3f} outside [{lo},{hi}]")
    status = "FAIL" if issues else ("WARN" if warns else "PASS")
    return {"id": "Q6", "title": "Pipeline rerun KPIs in plausible range",
            "status": status, "per_policy": per_policy,
            "issues": issues, "warns": warns}


# ─── Q7 ─────────────────────────────────────────────────────────────────────
def q7_validation() -> dict:
    v = _load_json("output/validation_report.json")
    chi = v.get("chi_square_per_rack_restricted", {})
    p_val = chi.get("p_value")
    cochran = chi.get("cochran_warning")
    issues, warns = [], []
    if p_val is None:
        issues.append("chi_square p_value missing")
    # Test rejects = expected; we only flag if the test ACCEPTS (p > 0.05) which would be suspicious.
    if isinstance(p_val, (int, float)) and p_val > 0.05:
        warns.append(f"chi-square restricted p={p_val:.4f} > 0.05 (test fails to reject — investigate)")
    if cochran:
        warns.append(f"Cochran's rule: {cochran}")
    status = "FAIL" if issues else ("WARN" if warns else "PASS")
    return {"id": "Q7", "title": "Validation chi-square + Cochran",
            "status": status, "p_value_restricted": p_val,
            "cochran_warning": cochran, "issues": issues, "warns": warns}


# ─── Q8 ─────────────────────────────────────────────────────────────────────
def q8_visual() -> dict:
    return {"id": "Q8", "title": "Visual sanity (top-down vs hand sketch)",
            "status": "WARN",
            "detail": "manual review required — open http://localhost:8000/web/?view=top "
                      "and compare against /home/dege/Downloads/WhatsApp Image 2026-05-06 at 15.39.54.jpeg"}


# ─── Q9 ─────────────────────────────────────────────────────────────────────
def q9_walk_realism() -> dict:
    p = _load_json("output/policy_summary.json")
    t = _load_json("output/timing_study_f400.json")
    walks = {name: kpi["avg_walk_distance"] for name, kpi in p.items()}
    speed = getattr(cfg, "OPERATOR_WALK_SPEED_M_PER_MIN", 50.0)
    corridor_min = t.get("config_mapping", {}).get("MANUAL_PICK_TIME_PENALTY")
    per_corridor_m = corridor_min * speed if corridor_min else None
    n_distinct_mean = _load_json("output/zwm92_summary.json")["n_distinct_per_kit_mean"]
    # Sanity heuristic: avg walk per order in [n_distinct * per_corridor_m, n_distinct * per_corridor_m * 30]
    if per_corridor_m is None:
        return {"id": "Q9", "title": "Walk distance realism", "status": "WARN",
                "detail": "MANUAL_PICK_TIME_PENALTY missing from timing study"}
    lo = n_distinct_mean * per_corridor_m
    hi = n_distinct_mean * per_corridor_m * 30
    warns = []
    for name, w in walks.items():
        if not (lo <= w <= hi):
            warns.append(f"{name}: walk {w:.2f} outside [{lo:.2f}, {hi:.2f}] m")
    status = "WARN" if warns else "PASS"
    return {"id": "Q9", "title": "Walk distance realism (F400 corridor × speed)",
            "status": status, "per_policy_walk_m": walks,
            "f400_corridor_min": corridor_min, "walk_speed_m_per_min": speed,
            "per_corridor_m": per_corridor_m, "n_distinct_mean": n_distinct_mean,
            "plausible_range_m": [lo, hi], "warns": warns}


# ─── Q10 ────────────────────────────────────────────────────────────────────
def q10_sensitivity() -> dict:
    s = _load_json("output/sensitivity.json")
    perts = s["perturbations"]
    expected_signs = {
        # parameter: {kpi: "↑" or "↓" expected when parameter ↑}
        "OPERATOR_WALK_SPEED_M_PER_MIN": {"avg_lead_time": "↓"},
        "REACH_TRUCK_SPEED_M_PER_MIN":   {"avg_lead_time": "↓"},
        "REACH_TRUCK_LIFT_TIME_PER_LEVEL": {"avg_lead_time": "↑"},
        "REACH_TRUCK_PICK_PLACE_TIME":   {"avg_lead_time": "↑"},
        "OPERATOR_PICK_TIME":            {"avg_lead_time": "↑"},
        "MANUAL_PICK_TIME_PENALTY":      {"avg_lead_time": "↑"},
        "KARDEX_PICK_TIME":              {"avg_lead_time": "↑"},
        "KARDEX_CAROUSEL_TIME":          {"avg_lead_time": "↑"},
        "IAT_MEAN_MIN_OVERRIDE":         {"avg_lead_time": "↓"},  # higher IAT → lower load → shorter wait
    }
    results, warns = {}, []
    for pname, expects in expected_signs.items():
        run = perts.get(pname)
        if not run:
            warns.append(f"{pname}: not in sensitivity.json")
            results[pname] = {"status": "MISSING"}
            continue
        rec = {}
        for kpi, want in expects.items():
            low = run["runs"]["low"]["delta_pct"].get(kpi)
            high = run["runs"]["high"]["delta_pct"].get(kpi)
            if low is None or high is None:
                rec[kpi] = {"status": "MISSING"}
                continue
            # Monotonic = signs of low and high are opposite (one negative one positive)
            mono = (low < 0 < high) or (high < 0 < low)
            sign_high = "↑" if high > 0 else "↓"
            actual_sign = sign_high  # high direction
            ok = mono and (actual_sign == want)
            rec[kpi] = {"low_delta_pct": low, "high_delta_pct": high,
                        "monotonic": mono, "expected_sign_high": want,
                        "actual_sign_high": actual_sign, "status": "PASS" if ok else "WARN"}
            if not ok:
                warns.append(f"{pname}/{kpi}: low={low:+.2f}% high={high:+.2f}% expected={want} got={actual_sign} monotonic={mono}")
        results[pname] = rec
    status = "WARN" if warns else "PASS"
    return {"id": "Q10", "title": "Sensitivity tornado monotonicity",
            "status": status, "per_parameter": results, "warns": warns}


# ─── Orchestrator ───────────────────────────────────────────────────────────
def main() -> None:
    qs = [q1_geometry(), q2_capacity(), q3_sap_join(), q4_zwm92(), q5_f400(),
          q6_pipeline(), q7_validation(), q8_visual(), q9_walk_realism(),
          q10_sensitivity()]

    summary = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for q in qs:
        summary[q["status"]] += 1

    payload = {
        "schema_version": "1.0",
        "_source": "scripts/run_sanity.py",
        "summary": summary,
        "canary_pallet_count": next(q for q in qs if q["id"] == "Q2")["total"],
        "checks": qs,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Sanity report v1 — Phase 1.5 Q1-Q10",
        f"# Generated by scripts/run_sanity.py against config/layout.json + output/*",
        "",
        f"Summary: PASS={summary['PASS']} WARN={summary['WARN']} FAIL={summary['FAIL']}",
        f"Pallet canary: {payload['canary_pallet_count']} (expected 3203 — {'OK' if payload['canary_pallet_count']==3203 else 'FAIL'})",
        "",
    ]
    for q in qs:
        lines.append(f"--- {q['id']}  [{q['status']}]  {q['title']}")
        for k, v in q.items():
            if k in ("id", "title", "status"):
                continue
            if isinstance(v, list) and v:
                lines.append(f"  {k}:")
                for it in v[:10]:
                    lines.append(f"    - {it}")
                if len(v) > 10:
                    lines.append(f"    ... +{len(v)-10} more")
            elif isinstance(v, dict):
                lines.append(f"  {k}: {{ {', '.join(f'{kk}={vv}' for kk,vv in list(v.items())[:6])} ... }}")
            else:
                lines.append(f"  {k}: {v}")
        lines.append("")

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_TXT}")
    print(f"Wrote {LAYOUT_SANITY_TXT}")
    print(f"Summary: PASS={summary['PASS']} WARN={summary['WARN']} FAIL={summary['FAIL']}")
    if summary["FAIL"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
