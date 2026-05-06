import sys
import os
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


def run_policy(policy_name, policy_cls, data):
    print(f"  Running: {policy_name}...")
    warehouse = Warehouse()
    materials = data["materials"]
    policy = _instantiate_policy(policy_cls, data)
    policy.assign(materials, warehouse)

    assigned = sum(1 for p in warehouse.positions.values() if p.material_id is not None)
    print(f"    Assigned {assigned} positions")
    if isinstance(policy, RealBaselinePolicy):
        print(
            f"    SAP fidelity: {policy.placed_from_sap} from SAP bin, "
            f"{policy.placed_kardex} kardex (fallback slot), "
            f"{policy.placed_fallback} heuristic fallback"
        )

    sim = WarehouseSimulation(warehouse, materials)
    sim.run()
    summary = sim.kpi.summary(
        num_reach_trucks=config.NUM_REACH_TRUCKS,
        num_operators=config.NUM_OPERATORS,
    )
    print(f"    Completed {summary['orders_completed']} orders")
    return summary, sim.kpi


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
          f"{stats['bins_unmapped_position']} unmapped")
    print(f"  Warehouse: {stats['warehouse_positions']} modeled positions "
          f"vs {stats['warehouse_pdf_capacity']} PDF capacity")

    results = {}
    all_kpis = {}

    for name, policy_cls in ALL_POLICIES.items():
        summary, kpi = run_policy(name, policy_cls, data)
        results[name] = summary
        all_kpis[name] = kpi

    print("\nGenerating charts...")
    os.makedirs("output", exist_ok=True)
    compare_policies(results)
    plot_prep_time_distribution(all_kpis)

    for name, kpi in all_kpis.items():
        safe_name = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        kpi.to_csv(f"output/{safe_name}.csv")

    print("\nDone! Results in output/")


if __name__ == "__main__":
    main()
