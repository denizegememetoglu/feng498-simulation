import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.data_loader import preprocess
from src.warehouse import Warehouse
from src.simulation import WarehouseSimulation
from src.slotting import ALL_POLICIES, RealBaselinePolicy
from src.visualize import compare_policies, plot_prep_time_distribution


def _instantiate_policy(policy_cls, data):
    if policy_cls is RealBaselinePolicy:
        return policy_cls(
            decoded_bins=data["decoded_bins"],
            kardex_materials=data["kardex_materials"],
        )
    return policy_cls()


def _safe_name(name: str) -> str:
    return name.lower().replace(" ", "_").replace("(", "").replace(")", "")


def run_policy(policy_name, policy_cls, data, n_reps=None):
    """Run a policy `n_reps` times with independent seeds. Returns a dict with
    aggregate summary (mean + std across reps), the KPI of the LAST run for
    distribution plots, and a list of per-rep summaries."""
    n_reps = n_reps if n_reps is not None else config.N_REPLICATIONS
    print(f"  Running: {policy_name} ({n_reps} replications)...")

    materials = data["materials"]
    material_to_line = data["material_to_line"]
    rep_summaries = []
    last_kpi = None
    last_warehouse = None

    for rep in range(n_reps):
        warehouse = Warehouse()
        policy = _instantiate_policy(policy_cls, data)
        policy.assign(materials, warehouse)

        sim = WarehouseSimulation(
            warehouse, materials,
            material_to_line=material_to_line,
            kardex_materials=data["kardex_materials"],
            seed=config.RANDOM_SEED + rep,
        )
        sim.run()
        summary = sim.kpi.summary(
            num_reach_trucks=config.NUM_REACH_TRUCKS,
            num_operators=config.NUM_OPERATORS,
        )
        rep_summaries.append(summary)
        last_kpi = sim.kpi
        last_warehouse = warehouse
        if isinstance(policy, RealBaselinePolicy) and rep == 0:
            print(
                f"    SAP fidelity: {policy.placed_from_sap} from SAP bin, "
                f"{policy.placed_kardex} kardex (fallback slot), "
                f"{policy.placed_fallback} heuristic fallback"
            )

    aggregate = _aggregate_summaries(rep_summaries)
    print(f"    Mean orders={aggregate['orders_completed']:.0f}  "
          f"prep={aggregate['avg_prep_time']:.2f}m  "
          f"lead={aggregate['avg_lead_time']:.2f}m  "
          f"walk={aggregate['avg_walk_distance']:.1f}m  "
          f"RT_util={aggregate['reach_truck_utilization'] * 100:.1f}%")
    if aggregate.get("util_overflow"):
        print(f"    WARN: util overflow events: {aggregate['util_overflow']}")
    return aggregate, last_kpi, last_warehouse, rep_summaries


def _aggregate_summaries(summaries):
    if not summaries:
        return {}
    numeric_keys = [
        "orders_completed", "orders_total", "avg_prep_time", "median_prep_time",
        "p95_prep_time", "avg_lead_time", "p95_lead_time", "avg_op_queue_wait",
        "avg_wait_time", "total_wait_time", "avg_walk_distance",
        "total_walk_distance", "reach_truck_utilization", "operator_utilization",
    ]
    out = {}
    for k in numeric_keys:
        vals = [s.get(k, 0.0) for s in summaries if k in s]
        if vals:
            out[k] = statistics.mean(vals)
            out[k + "_std"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
    overflow_events = []
    for s in summaries:
        overflow_events.extend(s.get("util_overflow", []))
    if overflow_events:
        out["util_overflow"] = overflow_events
    return out


def main():
    print("Preprocessing data...")
    data = preprocess()
    stats = data["stats"]
    print(f"  Materials: {stats['materials_total']} total, "
          f"{stats['materials_with_decoded_bin']} with rack bin, "
          f"{stats['materials_in_kardex']} in Kardex, "
          f"{stats['materials_with_line']} with production line")
    print(f"  Bins: {stats['bins_decoded']} decoded, "
          f"{stats['bins_kardex']} kardex, "
          f"{stats['bins_malformed']} malformed, "
          f"{stats['bins_unmapped_position']} unmapped, "
          f"{stats['bin_duplicates']} duplicates ({stats['bin_conflicts']} conflicts)")
    print(f"  Warehouse: {stats['warehouse_positions']} modeled positions "
          f"vs {stats['warehouse_pdf_capacity']} PDF capacity")

    os.makedirs("output", exist_ok=True)
    results = {}
    last_kpis = {}
    last_warehouses = {}
    rep_details: dict[str, list[dict]] = {}

    for name, policy_cls in ALL_POLICIES.items():
        summary, kpi, wh, reps = run_policy(name, policy_cls, data)
        results[name] = summary
        last_kpis[name] = kpi
        last_warehouses[name] = wh
        rep_details[name] = reps

    print("\nGenerating charts...")
    compare_policies(results)
    plot_prep_time_distribution(last_kpis)

    for name, kpi in last_kpis.items():
        safe = _safe_name(name)
        kpi.to_csv(f"output/{safe}.csv")
        kpi.picks_per_rack_csv(f"output/{safe}_picks_per_rack.csv")
        kpi.picks_per_material_csv(f"output/{safe}_picks_per_material.csv")

    # Aggregate per-rep summaries for later statistical analysis.
    with open("output/replications.json", "w") as f:
        json.dump(rep_details, f, indent=2, default=str)
    with open("output/policy_summary.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\nDone! Results in output/")


if __name__ == "__main__":
    main()
