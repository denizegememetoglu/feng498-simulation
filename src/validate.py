"""Statistical validation of the simulation against SAP ground truth.

Two tests, both run per-policy with the SAP baseline (Actual SAP) as the
reference point:

1. **Chi-square goodness of fit on per-rack pick volume.**
   - Observed: pick counts by rack from the simulation.
   - Expected: pick counts by rack derived from SAP (özet storage bins
     joined with zppq11 consumption).
   - H0: simulation pick distribution = SAP pick distribution.

2. **Paired t-test on per-material daily pick rate.**
   - Per-material picks-per-day in the simulation vs. observed
     consumption/DATA_DAYS from zppq11.
   - H0: mean per-material daily pick rate is the same.

The supervisor's expectation (May 2026) is that we report a p-value with
the relevant assumptions and limitations — specifically that order-level
timestamps from SAP are unavailable, so we can only validate aggregates.

Output:
   output/validation_report.json
   output/validation_report.txt
"""

import argparse
import json
import os
import shutil
from collections import Counter

from scipy import stats

from src import config
from src.data_loader import decode_storage_bin, preprocess
from src.warehouse import Warehouse
from src.simulation import WarehouseSimulation
from src.slotting import RealBaselinePolicy


ZWM92_SUMMARY_PATH = "output/zwm92_summary.json"


def _zwm92_actuals() -> dict | None:
    """Load cached ZWM92 derived views if present. None means run zwm92."""
    if not os.path.exists(ZWM92_SUMMARY_PATH):
        return None
    with open(ZWM92_SUMMARY_PATH) as f:
        return json.load(f)


def _expected_picks_by_rack(data) -> dict[str, float]:
    """Per-rack expected picks.

    Priority 1: real ZWM92 dispatch counts (`picks_per_rack_actual`). This
    is the ground truth — every value is a real goods-issue from a real bin.
    Priority 2: fallback to the consumption proxy (SAP bins × zppq11
    consumption) when ZWM92 cache is unavailable. The proxy was the old
    headline expected vector; it overcounts low-velocity racks because it
    has no per-bin pick history.
    """
    z = _zwm92_actuals()
    if z and z.get("picks_per_rack_actual"):
        return {r: float(c) for r, c in z["picks_per_rack_actual"].items()}

    weights = Counter()
    consumption = data["consumption"]
    decoded = data["decoded_bins"]
    for mid, bin_list in decoded.items():
        c = consumption.get(mid, 0.0)
        if c <= 0 or not bin_list:
            continue
        per_bin = c / len(bin_list)
        for (rack, _bay, _pos) in bin_list:
            weights[rack] += per_bin
    return dict(weights)


def _expected_picks_by_rack_scoped(data) -> dict[str, float]:
    """SCOPE-CORRECTED expected vector for the restricted chi-square
    (2026-06-10 forensics fix). The old restricted test compared sim picks
    of the 750 ozet-decoded materials against the rack distribution of ALL
    4,036 ZWM92 materials — a scope mismatch that inflated expected counts
    for racks whose decoded materials are dead stock (I/J/U: 97-100% of
    their decoded materials had ZERO picks in the 4-month log) and deflated
    others. Here the expectation is built ONLY from the decoded materials:
    each decoded material contributes its real ZWM92 pick count at the rack
    of its ozet bin. This tests 'does the fitted demand driver reproduce
    real per-material volumes at the real placements' — the apples-to-
    apples question (independently re-derived: chi2 drops 174 -> ~80,
    Cramer's V 0.145 -> ~0.10).
    """
    z = _zwm92_actuals()
    picks_by_mat = (z or {}).get("picks_by_material") or {}
    weights: Counter = Counter()
    for mid, bin_list in data["decoded_bins"].items():
        picks = float(picks_by_mat.get(mid, 0.0))
        if picks <= 0 or not bin_list:
            continue
        per_bin = picks / len(bin_list)
        for (rack, _bay, _pos) in bin_list:
            weights[rack] += per_bin
    return dict(weights)


def _sim_picks_by_rack_restricted(kpi, decoded_bins, warehouse) -> dict[str, float]:
    """Restrict simulation pick counts to materials that have a decoded
    SAP bin AND landed in one of THOSE bins (not a fallback rack). Apples-
    to-apples vs SAP-expected. Splits a material's pick count uniformly
    across the racks it physically occupies — handles the multi-bin case."""
    counts: Counter = Counter()
    for mid, bin_list in decoded_bins.items():
        locs = warehouse.material_locations.get(mid)
        if not locs:
            continue
        sap_racks = {b[0] for b in bin_list}
        placed_racks = [warehouse.positions[p].rack_id for p in locs
                        if warehouse.positions[p].rack_id in sap_racks]
        if not placed_racks:
            continue  # fell back to non-SAP rack — exclude
        picks = kpi.picks_by_material.get(mid, 0)
        share = picks / len(placed_racks)
        for r in placed_racks:
            counts[r] += share
    return dict(counts)


def _expected_picks_per_material(data) -> dict[str, float]:
    """Daily picks per material — ZWM92 actuals when cached, else consumption proxy."""
    z_orders_path = "output/zwm92_orders.json"
    if os.path.exists(z_orders_path):
        from src.zwm92 import load_orders_cached
        orders = load_orders_cached(z_orders_path)
        if orders:
            counts: Counter = Counter()
            days = set()
            for o in orders:
                dt = o.get("arrival_dt")
                if dt is not None and not getattr(dt, "is_nat", False):
                    try:
                        days.add(dt.strftime("%Y-%m-%d"))
                    except Exception:
                        pass
                for mid in o["items"]:
                    counts[mid] += 1
            n_days = len(days) or config.DATA_DAYS
            return {mid: c / n_days for mid, c in counts.items()}
    cons = data["consumption"]
    return {mid: c / config.DATA_DAYS for mid, c in cons.items() if c > 0}


def _sim_picks_per_day(kpi, sim_days):
    return {mid: cnt / sim_days for mid, cnt in kpi.picks_by_material.items()}


def _static_sanity_checks(data, warehouse) -> dict:
    issues = []
    warnings = []
    capacity = warehouse.pallet_capacity_from_pdf
    modelled = len(warehouse.positions)
    if capacity != 3203:
        issues.append(f"PDF pallet canary changed: {capacity} != 3203")
    if modelled != data["stats"].get("warehouse_positions"):
        issues.append("Warehouse position count changed between preprocess and validation")
    if decode_storage_bin("BRA-02-02") != ("A", 2, 2):
        issues.append("Storage-bin decoder failed canary BRA-02-02 -> (A,2,2)")
    if data["stats"].get("bins_unmapped_position", 0) > 0:
        warnings.append(
            f"{data['stats']['bins_unmapped_position']} decoded SAP bins do not map to a layout slot"
        )
    if data["stats"].get("bins_invalid_position", 0) > 0:
        warnings.append(
            f"{data['stats']['bins_invalid_position']} decoded SAP bins use a bay position "
            "that does not exist in config/layout.json; see output/bin_validation_errors.csv"
        )
    if data["stats"].get("bins_malformed", 0) > 0:
        warnings.append(f"{data['stats']['bins_malformed']} storage-bin strings are malformed/non-rack")
    return {
        "status": "FAIL" if issues else ("WARN" if warnings else "PASS"),
        "issues": issues,
        "warnings": warnings,
        "pdf_capacity": capacity,
        "modelled_positions": modelled,
        "preprocess_stats": {
            "materials_with_bin": data["stats"].get("materials_with_bin"),
            "materials_with_decoded_bin": data["stats"].get("materials_with_decoded_bin"),
            "decoded_bin_slots_total": data["stats"].get("decoded_bin_slots_total"),
            "bins_unmapped_position": data["stats"].get("bins_unmapped_position", 0),
            "bins_invalid_position": data["stats"].get("bins_invalid_position", 0),
            "bin_validation_errors": data["stats"].get("bin_validation_errors", 0),
        },
    }


def _assignment_sanity(materials, warehouse, kardex_materials) -> dict:
    issues = []
    warnings = []
    assigned_positions = []
    for mid, locs in warehouse.material_locations.items():
        if mid in kardex_materials:
            issues.append(f"Kardex material assigned to rack slot: {mid}")
        for pid in locs:
            if pid not in warehouse.positions:
                issues.append(f"{mid} assigned to nonexistent position {pid}")
            assigned_positions.append(pid)
    if len(assigned_positions) != len(set(assigned_positions)):
        issues.append("Capacity overflow: at least one pallet position has multiple materials")
    rack_materials = {m["material_id"] for m in materials if m["material_id"] not in kardex_materials}
    unplaced = rack_materials - set(warehouse.material_locations)
    if unplaced:
        warnings.append(f"{len(unplaced)} rack materials are unplaced; capacity/input mismatch is explicit")
    return {
        "status": "FAIL" if issues else ("WARN" if warnings else "PASS"),
        "issues": issues,
        "warnings": warnings,
        "assigned_rack_materials": len(warehouse.material_locations),
        "unplaced_rack_materials": len(unplaced),
    }


def _reproducibility_check(materials, material_to_line, kardex_materials) -> dict:
    def _signature():
        wh = Warehouse()
        sim = WarehouseSimulation(
            wh,
            materials,
            material_to_line=material_to_line,
            kardex_materials=kardex_materials,
            seed=config.RANDOM_SEED,
        )
        seq = []
        for _ in range(10):
            order = sim.order_gen.next_order()
            seq.append({
                "items": order["items"],
                "line": order.get("line"),
                "iat": round(order["inter_arrival_time"], 6),
            })
        return seq

    a = _signature()
    b = _signature()
    ok = a == b
    return {
        "status": "PASS" if ok else "FAIL",
        "issues": [] if ok else ["Fixed seed does not reproduce the first 10 generated orders"],
        "sample_size": 10,
    }


def _chi_square_per_rack(sim_counts: dict, expected_weights: dict):
    """Chi-square goodness of fit. Aligns observed and expected on the
    intersection of racks. Returns (statistic, p, dof, observed, expected).

    M3 fix: Cochran's rule (expected cell count >= 5) is checked and any
    low-expected cells are reported as a `cochran_warning` field. When the
    rule is violated the p-value is approximate — the chi-square asymptotic
    distribution starts to drift for sparse cells.
    """
    racks = sorted(set(sim_counts) & set(expected_weights))
    if len(racks) < 2:
        return None
    obs = [sim_counts.get(r, 0) for r in racks]
    obs_total = sum(obs)
    exp_raw = [expected_weights.get(r, 0.0) for r in racks]
    exp_total = sum(exp_raw)
    # Scale expected to the same total as observed (chi-square requires
    # equal totals; we're testing distribution shape, not magnitude).
    if exp_total == 0 or obs_total == 0:
        return None
    exp = [e * obs_total / exp_total for e in exp_raw]
    stat, p = stats.chisquare(obs, exp)
    # Effect size: with n in the hundreds the chi-square has power to
    # reject for even small shape deviations, so the p-value alone
    # overstates the mismatch. Cramér's V (sqrt(chi2 / (n*(k-1)))) is the
    # magnitude: <0.1 negligible, 0.1-0.3 small, 0.3-0.5 medium.
    cramers_v = (float(stat) / (obs_total * (len(racks) - 1))) ** 0.5 \
        if obs_total > 0 and len(racks) > 1 else None
    low_cells = [(r, round(e, 2)) for r, e in zip(racks, exp) if e < 5]
    cochran_warning = None
    if low_cells:
        cochran_warning = (
            f"Cochran's rule violated: {len(low_cells)} of {len(racks)} cells "
            f"have expected count < 5 — {low_cells}. Unpooled p-value is "
            f"approximate; the POOLED test below is the headline number."
        )

    # 2026-06-09: pool low-expected cells (standard remedy) so the headline
    # test satisfies Cochran's rule. All racks with E<5 merge into one
    # OTHER cell; if the pool itself stays below 5 it merges into the
    # smallest valid cell. The unpooled arrays are kept for transparency.
    pooled = None
    if low_cells:
        keep = [(r, o, e) for r, o, e in zip(racks, obs, exp) if e >= 5]
        pool_o = sum(o for r, o, e in zip(racks, obs, exp) if e < 5)
        pool_e = sum(e for r, o, e in zip(racks, obs, exp) if e < 5)
        labels = [r for r, _, _ in keep]
        obs_p = [o for _, o, _ in keep]
        exp_p = [e for _, _, e in keep]
        if keep and pool_e < 5:
            i_min = exp_p.index(min(exp_p))
            labels[i_min] = f"{labels[i_min]}+OTHER"
            obs_p[i_min] += pool_o
            exp_p[i_min] += pool_e
        else:
            labels.append("OTHER(pooled)")
            obs_p.append(pool_o)
            exp_p.append(pool_e)
        if len(labels) >= 2:
            stat_p, p_p = stats.chisquare(obs_p, exp_p)
            pooled = {
                "racks": labels,
                "observed": obs_p,
                "expected": [round(e, 2) for e in exp_p],
                "chi_square": float(stat_p),
                "p_value": float(p_p),
                "dof": len(labels) - 1,
                "cochran_satisfied": all(e >= 5 for e in exp_p),
            }

    return {
        "racks": racks,
        "observed": obs,
        "expected": [round(e, 2) for e in exp],
        "chi_square": float(stat),
        "p_value": float(p),
        "cramers_v": round(cramers_v, 4) if cramers_v is not None else None,
        "dof": len(racks) - 1,
        "cochran_low_cells": [r for r, _ in low_cells],
        "cochran_warning": cochran_warning,
        "pooled": pooled,
    }


def _t_test_per_material(sim_rates: dict, expected_rates: dict):
    """Paired t-test on log(daily picks + eps) so the heavy-tailed
    consumption distribution doesn't dominate. Pairs materials present in
    both sim and expected."""
    common = sorted(set(sim_rates) & set(expected_rates))
    if len(common) < 30:
        return None
    import math
    eps = 1e-3
    sim_arr = [math.log(sim_rates[m] + eps) for m in common]
    exp_arr = [math.log(expected_rates[m] + eps) for m in common]
    t, p = stats.ttest_rel(sim_arr, exp_arr)
    return {
        "n_materials_paired": len(common),
        "t_statistic": float(t),
        "p_value": float(p),
        "mean_log_diff": float(sum(s - e for s, e in zip(sim_arr, exp_arr)) / len(sim_arr)),
    }


def _daily_volume_check(kpi, sim_days: float):
    """Operational validity (INFORMATIONAL): single-run sim arrivals/day vs
    the real ZWM92 daily volume. Daily volume is heavy-tailed (batch CV≈2 —
    one-day samples observed at 304/382/485 across seeds), so a short
    validation run swings ±30% naturally. This check therefore only
    reports the number; the gate is `_replication_ci_check`, which judges
    the mean over the N>=20 independent-seed replication run."""
    try:
        from src.zwm92 import fit_distributions
        fit = fit_distributions()
        target = float(fit["orders_per_active_day"])
    except Exception as exc:  # cache missing — synthetic fallback run
        return {"status": "SKIP", "reason": f"ZWM92 fit unavailable: {exc}"}
    sim_per_day = kpi.orders_started / max(sim_days, 1e-9)
    rel_err = (sim_per_day - target) / target
    return {
        "status": "INFO" if abs(rel_err) <= 0.50 else "WARN",
        "sim_orders_per_day": round(sim_per_day, 1),
        "zwm92_orders_per_active_day": round(target, 1),
        "relative_error": round(rel_err, 4),
        "note": "Single short-run estimate — informational only; the "
                "replication-CI check is the rigorous volume gate.",
    }


def _replication_ci_check(reps_path: str = "output/replications.json",
                          alpha: float = 0.05):
    """Operational validity from the multi-replication run: does the 95% CI
    of simulated throughput (orders/day) contain the real ZWM92 daily
    volume? Reads the latest replications.json if present."""
    import math
    if not os.path.exists(reps_path):
        return {"status": "SKIP",
                "reason": f"{reps_path} not found — run python -m src.main first"}
    try:
        from src.zwm92 import fit_distributions
        target = float(fit_distributions()["orders_per_active_day"])
    except Exception as exc:
        return {"status": "SKIP", "reason": f"ZWM92 fit unavailable: {exc}"}
    with open(reps_path) as f:
        reps = json.load(f)
    out = {"status": "SKIP", "zwm92_orders_per_active_day": round(target, 1),
           "per_policy": {}}
    sap_name = "Baseline (Actual SAP)"
    for pol, rs in reps.items():
        vals = [r.get("throughput_orders_per_day") for r in rs]
        vals = [v for v in vals if v is not None]
        # Arrivals (not completions) carry the volume signal, but completed
        # throughput is the advisor KPI — report CI on throughput and note
        # the started-volume separately.
        started = [r.get("orders_started") for r in rs]
        started = [s for s in started if s is not None]
        if len(vals) < 2:
            continue
        n = len(vals)
        m = sum(vals) / n
        sd = (sum((v - m) ** 2 for v in vals) / (n - 1)) ** 0.5
        h = float(stats.t.ppf(1 - alpha / 2, df=n - 1)) * sd / math.sqrt(n)
        entry = {
            "n": n,
            "throughput_mean": round(float(m), 1),
            "throughput_ci95": [round(float(m - h), 1), round(float(m + h), 1)],
        }
        if started:
            sm = sum(started) / len(started)
            # Use the sim_days the replications were RUN with (persisted per
            # rep since 2026-06-09), not the live config — a later validate
            # call with a different SIM_DAYS would otherwise mis-scale.
            days = next((r.get("sim_days") for r in rs if r.get("sim_days")),
                        getattr(config, "SIM_DAYS", 5) or 5)
            entry["arrivals_per_day_mean"] = round(sm / days, 1)
            entry["volume_vs_zwm92_rel_err"] = round(
                (sm / days - target) / target, 4)
        out["per_policy"][pol] = entry
        if pol == sap_name:
            # The CI is on COMPLETED throughput, which sits below arrivals
            # whenever the system can't keep up — containment of the raw
            # volume is judged on arrivals_per_day instead.
            rel = entry.get("volume_vs_zwm92_rel_err")
            if rel is not None:
                out["status"] = "PASS" if abs(rel) <= 0.10 else "WARN"
                out["headline"] = (
                    f"{sap_name}: simulated arrivals/day within "
                    f"{abs(rel) * 100:.1f}% of ZWM92 actual ({target:.0f})")
    return out


def run_validation(
    full_routes: bool = False,
    route_sample_per_segment: int = 3,
    sim_days: float = 2.0,
):
    print("Validation: preprocessing data...")
    data = preprocess()
    materials = data["materials"]
    print(f"  Materials: {len(materials)} active")

    print("  Route/layout sanity...")
    route_wh = Warehouse()
    static_sanity = _static_sanity_checks(data, route_wh)
    route_report = route_wh.validate_route_model(
        full=full_routes,
        sample_per_segment=route_sample_per_segment,
    )
    os.makedirs("output", exist_ok=True)
    route_wh.write_route_debug("output/route_debug.json", route_report)
    for mirror in ("web/route_debug.json", "docs/route_debug.json"):
        os.makedirs(os.path.dirname(mirror), exist_ok=True)
        shutil.copyfile("output/route_debug.json", mirror)
    if route_report["issues"]:
        print(f"  Route model: FAIL ({len(route_report['issues'])} issue(s))")
        raise SystemExit("Route model failed; see output/route_debug.json")
    if route_report["warnings"]:
        print(f"  Route model: WARN ({len(route_report['warnings'])} assumptions/TODOs; "
              f"{route_report['validation_scope']} scope, "
              f"{route_report['validated_routes']} routes checked)")
    if static_sanity["issues"]:
        raise SystemExit(f"Static sanity failed: {static_sanity['issues']}")

    expected_by_rack = _expected_picks_by_rack(data)
    expected_per_mat = _expected_picks_per_material(data)
    print(f"  Expected: {len(expected_by_rack)} racks weighted, "
          f"{len(expected_per_mat)} materials with consumption")

    original_sim_days = config.SIM_DAYS
    if sim_days <= 0:
        raise SystemExit("--sim-days must be positive")
    config.SIM_DAYS = float(sim_days)

    print(f"\nRunning Actual SAP baseline policy for validation "
          f"({config.SIM_DAYS:g} simulated day(s); use --full-sim for "
          f"{original_sim_days:g} day(s))...")
    warehouse = Warehouse()
    policy = RealBaselinePolicy(
        decoded_bins=data["decoded_bins"],
        kardex_materials=data["kardex_materials"],
    )
    policy.assign(materials, warehouse)
    sap_fidelity = {
        "sap_materials_placed": policy.placed_from_sap,
        "sap_slots_assigned": policy.sap_slots_assigned,
        "kardex_materials_routed": policy.placed_kardex,
        "heuristic_fallback_materials": policy.placed_fallback,
        "bin_validation_errors": data["stats"].get("bin_validation_errors", 0),
    }
    assignment_sanity = _assignment_sanity(materials, warehouse, data["kardex_materials"])
    if assignment_sanity["issues"]:
        raise SystemExit(f"Assignment sanity failed: {assignment_sanity['issues']}")
    if assignment_sanity["warnings"]:
        print(f"  Assignment sanity: WARN ({len(assignment_sanity['warnings'])})")
    reproducibility = _reproducibility_check(
        materials,
        data["material_to_line"],
        data["kardex_materials"],
    )
    if reproducibility["issues"]:
        raise SystemExit(f"Reproducibility failed: {reproducibility['issues']}")

    sim = WarehouseSimulation(
        warehouse, materials,
        material_to_line=data["material_to_line"],
        kardex_materials=data["kardex_materials"],
        seed=config.RANDOM_SEED,
    )
    sim.run()
    kpi = sim.kpi
    print(f"  Sim picks: {sum(kpi.picks_by_rack.values())} total across "
          f"{len(kpi.picks_by_rack)} racks")

    actual_sim_days = config.SIM_DAYS
    sim_rates = _sim_picks_per_day(kpi, actual_sim_days)

    # Two chi-square tests:
    # (a) sim distribution over ALL picks vs. SAP-expected over only the
    #     SAP-decoded subset — biased because fallback-placed materials
    #     dominate the sim numerator.
    # (b) sim distribution restricted to SAP-decoded materials only —
    #     apples-to-apples. This is the meaningful test.
    chi_all = _chi_square_per_rack(dict(kpi.picks_by_rack), expected_by_rack)
    # 2026-06-10 scope fix: the restricted test's expected vector must come
    # from the SAME material subset as the observed vector (decoded
    # materials only) — see _expected_picks_by_rack_scoped docstring.
    expected_scoped = _expected_picks_by_rack_scoped(data)
    chi_restricted = _chi_square_per_rack(
        _sim_picks_by_rack_restricted(kpi, data["decoded_bins"], warehouse),
        expected_scoped if expected_scoped else expected_by_rack,
    )
    chi = chi_restricted
    ttest = _t_test_per_material(sim_rates, expected_per_mat)
    daily_volume = _daily_volume_check(kpi, actual_sim_days)
    replication_ci = _replication_ci_check()

    expected_source = ("ZWM92 actuals (real per-bin dispatch counts)"
                       if _zwm92_actuals() and _zwm92_actuals().get("picks_per_rack_actual")
                       else "consumption proxy (özet bins × zppq11)")
    status_inputs = [
        static_sanity["status"],
        assignment_sanity["status"],
        reproducibility["status"],
        route_report["status"],
    ]
    status_warnings = []
    if (chi_restricted and chi_restricted.get("cochran_warning")
            and not (chi_restricted.get("pooled") or {}).get("cochran_satisfied")):
        status_warnings.append(
            "restricted chi-square violates Cochran's rule even after pooling")
    if ttest is None:
        status_warnings.append("paired material t-test is not computable")
    if daily_volume.get("status") == "WARN":
        status_warnings.append(
            f"single-run daily volume off by "
            f"{daily_volume['relative_error'] * 100:+.1f}% vs ZWM92 "
            f"(beyond even the heavy-tail band)")
    if replication_ci.get("status") == "WARN":
        status_warnings.append("replication arrivals/day outside ±10% of ZWM92")
    if "FAIL" in status_inputs:
        report_status = "FAIL"
    elif "WARN" in status_inputs or status_warnings:
        report_status = "WARN"
    else:
        report_status = "PASS"
    report = {
        "status": report_status,
        "expected_source": expected_source,
        "static_sanity": static_sanity,
        "assignment_sanity": assignment_sanity,
        "reproducibility": reproducibility,
        "sap_fidelity": sap_fidelity,
        "status_warnings": status_warnings,
        "route_model": {
            "status": route_report["status"],
            "issues_count": len(route_report["issues"]),
            "warnings_count": len(route_report["warnings"]),
            "validation_scope": route_report["validation_scope"],
            "validated_routes": route_report["validated_routes"],
            "overlapping_rack_geometry_count": len(route_report["overlapping_rack_geometry"]),
            "debug_json": "output/route_debug.json",
            "notes": route_report["notes"],
        },
        "sim_days": actual_sim_days,
        "full_sim_days": original_sim_days,
        "chi_square_per_rack_restricted": chi_restricted,
        "chi_square_per_rack_all_sim_picks": chi_all,
        "t_test_per_material": ttest,
        "daily_volume_check": daily_volume,
        "replication_ci_check": replication_ci,
        "notes": [
            f"Expected rack distribution source: {expected_source}.",
            "Chi-square (restricted): simulation pick distribution is "
            "restricted to materials that have a decoded SAP bin, and "
            "(2026-06-10 scope fix) the EXPECTED vector is built from the "
            "same decoded-material subset — each decoded material "
            "contributes its real ZWM92 pick count at its ozet rack. "
            "H0 = same shape. The pre-fix expected used ALL ZWM92 "
            "materials, which inflated expected counts at racks whose "
            "decoded materials are dead stock (I/J/U: 97-100% zero-pick "
            "over the 4-month log) — a scope mismatch, not model error.",
            "KDX fidelity note: 329 materials dispatched from KDX in ZWM92 "
            "are missing from the ozet kardex set, but only 1 of them is "
            "in the active master (8 pick rows, ~0% of volume) — "
            "negligible for the sim; disclosed for completeness.",
            "Chi-square (all sim picks): biased because the simulation "
            "places ~5600 materials without a SAP bin via fallback, "
            "shifting the rack distribution away from SAP — kept for "
            "completeness but the restricted test is the headline number.",
            "T-test runs on log(daily picks + 1e-3) over materials common "
            "to both sim and expected; H0 = same mean.",
            "ZWM92 (167,784 rows, 2026-01-02 to 2026-05-18, 9 product "
            "families) closes the prior validation gap — we now compare "
            "against real per-rack dispatch counts, not a consumption proxy.",
            "Default src.validate uses a short validation sim sample so the "
            "command stays interactive; run python -m src.validate --full-sim "
            "for the configured full-horizon statistical validation.",
            "SCOPE LIMIT (honesty): the chi-square/t-test 'expected' vectors "
            "come from the same ZWM92 dataset the driver distributions were "
            "fitted on — these are internal-consistency checks, not holdout "
            "validation (no second observation period exists). Independent "
            "evidence: F400 video timing (separate source), daily-volume "
            "calibration, and face validation of routes/layout.",
            "daily_volume_check / replication_ci_check (2026-06-09): the "
            "batch-arrival driver must reproduce the real daily kit-order "
            "volume (~396/day); the replication check puts a 95% CI around "
            "simulated throughput across the N>=20 independent-seed runs.",
        ],
    }
    config.SIM_DAYS = original_sim_days

    os.makedirs("output", exist_ok=True)
    with open("output/validation_report.json", "w") as f:
        json.dump(report, f, indent=2)

    def _write_chi(f, label, c):
        f.write(f"Chi-square ({label}):\n")
        if c:
            f.write(f"  racks tested: {c['racks']}\n")
            f.write(f"  observed     = {c['observed']}\n")
            f.write(f"  expected     = {c['expected']}\n")
            f.write(f"  chi-square   = {c['chi_square']:.3f}\n")
            f.write(f"  dof          = {c['dof']}\n")
            f.write(f"  p-value      = {c['p_value']:.4f}\n")
            if c.get("cramers_v") is not None:
                mag = ("negligible" if c["cramers_v"] < 0.1 else
                       "small" if c["cramers_v"] < 0.3 else
                       "medium" if c["cramers_v"] < 0.5 else "large")
                f.write(f"  Cramér's V   = {c['cramers_v']:.3f} ({mag} effect; "
                        f"with n in the hundreds the test has power to reject "
                        f"for even small shape deviations)\n")
            verdict = "REJECT H0 (distributions differ)" if c["p_value"] < 0.05 else "fail to reject H0"
            f.write(f"  verdict      = {verdict}\n")
            if c.get("cochran_warning"):
                f.write(f"  WARNING      = {c['cochran_warning']}\n")
            pl = c.get("pooled")
            if pl:
                f.write(f"  POOLED (low-E cells merged; Cochran "
                        f"{'OK' if pl['cochran_satisfied'] else 'STILL VIOLATED'}):\n")
                f.write(f"    cells      = {pl['racks']}\n")
                f.write(f"    chi-square = {pl['chi_square']:.3f}  dof = {pl['dof']}  "
                        f"p = {pl['p_value']:.4f}\n")
                v = ("REJECT H0 (distributions differ)"
                     if pl["p_value"] < 0.05 else "fail to reject H0")
                f.write(f"    verdict    = {v}\n")
            f.write("\n")
        else:
            f.write("  not computable (need >= 2 racks)\n\n")

    with open("output/validation_report.txt", "w") as f:
        f.write("Validation report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Overall status: {report_status}\n")
        if status_warnings:
            f.write("Status warnings:\n")
            for w in status_warnings:
                f.write(f"  - {w}\n")
        f.write(
            "SAP fidelity: "
            f"{sap_fidelity['sap_materials_placed']} materials placed from SAP bins; "
            f"{sap_fidelity['sap_slots_assigned']} SAP slots assigned; "
            f"{sap_fidelity['kardex_materials_routed']} Kardex routed; "
            f"{sap_fidelity['heuristic_fallback_materials']} heuristic fallback.\n\n"
        )
        _write_chi(f, "restricted to SAP-decoded materials [headline]", chi_restricted)
        _write_chi(f, "all sim picks vs SAP-decoded (biased)", chi_all)
        f.write("Paired t-test (log daily picks per material):\n")
        if ttest:
            f.write(f"  n paired = {ttest['n_materials_paired']}\n")
            f.write(f"  t        = {ttest['t_statistic']:.3f}\n")
            f.write(f"  p-value  = {ttest['p_value']:.4f}\n")
            verdict = "REJECT H0 (means differ)" if ttest["p_value"] < 0.05 else "fail to reject H0"
            f.write(f"  verdict  = {verdict}\n\n")
        else:
            f.write("  not computable (need >= 30 paired materials)\n\n")
        f.write("Daily volume calibration (sim vs ZWM92 actual):\n")
        if daily_volume.get("status") == "SKIP":
            f.write(f"  SKIP — {daily_volume.get('reason')}\n\n")
        else:
            f.write(f"  status   = {daily_volume['status']} (informational; "
                    f"rigorous gate = replication CI check)\n")
            f.write(f"  sim      = {daily_volume['sim_orders_per_day']} orders/day\n")
            f.write(f"  ZWM92    = {daily_volume['zwm92_orders_per_active_day']} orders/active day\n")
            f.write(f"  rel err  = {daily_volume['relative_error'] * 100:+.1f}%\n\n")
        f.write("Replication CI check (multi-rep throughput vs ZWM92):\n")
        if replication_ci.get("status") == "SKIP":
            f.write(f"  SKIP — {replication_ci.get('reason', 'n/a')}\n\n")
        else:
            f.write(f"  status   = {replication_ci['status']}\n")
            if replication_ci.get("headline"):
                f.write(f"  {replication_ci['headline']}\n")
            for pol, e in replication_ci.get("per_policy", {}).items():
                f.write(f"  {pol}: throughput {e['throughput_mean']}/day "
                        f"CI95 {e['throughput_ci95']} (n={e['n']})\n")
            f.write("\n")
        f.write("Notes:\n")
        for n in report["notes"]:
            f.write(f"  - {n}\n")

    print("\nReport written to output/validation_report.{json,txt}")
    if chi:
        print(f"  Chi-square p = {chi['p_value']:.4f}")
    if ttest:
        print(f"  T-test p     = {ttest['p_value']:.4f}")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run data, assignment, reproducibility, route, and SAP/ZWM92 validation."
    )
    parser.add_argument(
        "--full-routes",
        action="store_true",
        help="Check every modeled level-0 bay access route. Default checks a representative sample.",
    )
    parser.add_argument(
        "--route-sample-per-segment",
        type=int,
        default=3,
        help="Representative bays per rack segment for default route validation.",
    )
    parser.add_argument(
        "--sim-days",
        type=float,
        default=2.0,
        help="Simulation days for the default validation run. 2 days "
             "(~800 kit-orders under batch arrivals) keeps per-material "
             "rates stable enough for the paired t-test; use a smaller "
             "value only for quick smoke checks.",
    )
    parser.add_argument(
        "--full-sim",
        action="store_true",
        help="Run the full configured validation horizon instead of the quick default.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    sim_days = config.SIM_DAYS if args.full_sim else args.sim_days
    run_validation(
        full_routes=args.full_routes,
        route_sample_per_segment=args.route_sample_per_segment,
        sim_days=sim_days,
    )
