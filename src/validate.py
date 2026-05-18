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

import json
import os
from collections import Counter

from scipy import stats

from src import config
from src.data_loader import preprocess
from src.warehouse import Warehouse
from src.simulation import WarehouseSimulation
from src.slotting import RealBaselinePolicy


def _expected_picks_by_rack(data) -> dict[str, float]:
    """Project SAP storage bins onto rack ids and weight by consumption.

    For each material with a decoded SAP bin, the rack on that bin is its
    'home rack'. We weight by zppq11 consumption (units/76d) — if a
    material is consumed 1000 units in 76 days and lives in rack J, then
    rack J gets 1000 units of expected demand. Materials without a decoded
    bin contribute nothing to the expected distribution (we know their
    pick volume but not the rack)."""
    weights = Counter()
    consumption = data["consumption"]
    decoded = data["decoded_bins"]
    for mid, bin_list in decoded.items():
        c = consumption.get(mid, 0.0)
        if c <= 0 or not bin_list:
            continue
        # Split consumption uniformly across the material's bins. This is
        # the most-defensible assumption without per-bin pick history.
        per_bin = c / len(bin_list)
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
    """Daily picks per material from zppq11 consumption / DATA_DAYS."""
    cons = data["consumption"]
    return {mid: c / config.DATA_DAYS for mid, c in cons.items() if c > 0}


def _sim_picks_per_day(kpi, sim_days):
    return {mid: cnt / sim_days for mid, cnt in kpi.picks_by_material.items()}


def _chi_square_per_rack(sim_counts: dict, expected_weights: dict):
    """Chi-square goodness of fit. Aligns observed and expected on the
    intersection of racks. Returns (statistic, p, dof, observed, expected)."""
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
    return {
        "racks": racks,
        "observed": obs,
        "expected": [round(e, 2) for e in exp],
        "chi_square": float(stat),
        "p_value": float(p),
        "dof": len(racks) - 1,
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


def run_validation():
    print("Validation: preprocessing data...")
    data = preprocess()
    materials = data["materials"]
    print(f"  Materials: {len(materials)} active")

    expected_by_rack = _expected_picks_by_rack(data)
    expected_per_mat = _expected_picks_per_material(data)
    print(f"  Expected: {len(expected_by_rack)} racks weighted, "
          f"{len(expected_per_mat)} materials with consumption")

    print("\nRunning Actual SAP baseline policy for validation...")
    warehouse = Warehouse()
    policy = RealBaselinePolicy(
        decoded_bins=data["decoded_bins"],
        kardex_materials=data["kardex_materials"],
    )
    policy.assign(materials, warehouse)

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

    sim_days = config.SIM_DAYS
    sim_rates = _sim_picks_per_day(kpi, sim_days)

    # Two chi-square tests:
    # (a) sim distribution over ALL picks vs. SAP-expected over only the
    #     SAP-decoded subset — biased because fallback-placed materials
    #     dominate the sim numerator.
    # (b) sim distribution restricted to SAP-decoded materials only —
    #     apples-to-apples. This is the meaningful test.
    chi_all = _chi_square_per_rack(dict(kpi.picks_by_rack), expected_by_rack)
    chi_restricted = _chi_square_per_rack(
        _sim_picks_by_rack_restricted(kpi, data["decoded_bins"], warehouse),
        expected_by_rack,
    )
    chi = chi_restricted
    ttest = _t_test_per_material(sim_rates, expected_per_mat)

    report = {
        "chi_square_per_rack_restricted": chi_restricted,
        "chi_square_per_rack_all_sim_picks": chi_all,
        "t_test_per_material": ttest,
        "notes": [
            "Chi-square (restricted): simulation pick distribution is "
            "restricted to materials that have a decoded SAP bin "
            "(apples-to-apples vs. SAP-expected). H0 = same shape.",
            "Chi-square (all sim picks): biased because the simulation "
            "places ~5600 materials without a SAP bin via fallback, "
            "shifting the rack distribution away from SAP — kept for "
            "completeness but the restricted test is the headline number.",
            "T-test runs on log(daily picks + 1e-3) over materials common "
            "to both sim and SAP-consumption (zppq11); H0 = same mean.",
            "Order-level SAP timestamps unavailable — lead-time validation "
            "is not possible; only aggregate validation here.",
            "BOM data still pending (May 2026) — when available, expected "
            "rack distribution can be refined to weight by bill-of-materials "
            "co-pick frequency rather than raw consumption.",
        ],
    }

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
            verdict = "REJECT H0 (distributions differ)" if c["p_value"] < 0.05 else "fail to reject H0"
            f.write(f"  verdict      = {verdict}\n\n")
        else:
            f.write("  not computable (need >= 2 racks)\n\n")

    with open("output/validation_report.txt", "w") as f:
        f.write("Validation report\n")
        f.write("=" * 60 + "\n\n")
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
        f.write("Notes:\n")
        for n in report["notes"]:
            f.write(f"  - {n}\n")

    print("\nReport written to output/validation_report.{json,txt}")
    if chi:
        print(f"  Chi-square p = {chi['p_value']:.4f}")
    if ttest:
        print(f"  T-test p     = {ttest['p_value']:.4f}")


if __name__ == "__main__":
    run_validation()
