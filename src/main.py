import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.data_loader import load_all_data
from src.warehouse import Warehouse
from src.simulation import WarehouseSimulation
from src.slotting import ALL_POLICIES
from src.visualize import compare_policies, plot_prep_time_distribution


def run_policy(policy_name, policy_cls, materials):
    print(f"  Running: {policy_name}...")
    warehouse = Warehouse()
    policy = policy_cls()
    policy.assign(materials, warehouse)

    assigned = sum(1 for p in warehouse.positions.values() if p.material_id is not None)
    print(f"    Assigned {assigned} positions")

    sim = WarehouseSimulation(warehouse, materials)
    sim.run()
    summary = sim.kpi.summary(
        num_reach_trucks=config.NUM_REACH_TRUCKS,
        num_operators=config.NUM_OPERATORS,
    )
    print(f"    Completed {summary['orders_completed']} orders")
    return summary, sim.kpi


def main():
    print("Loading data...")
    data = load_all_data()
    materials = data["abc_analizi"]
    print(f"  Loaded {len(materials)} materials")

    results = {}
    all_kpis = {}

    for name, policy_cls in ALL_POLICIES.items():
        summary, kpi = run_policy(name, policy_cls, materials)
        results[name] = summary
        all_kpis[name] = kpi

    print("\nGenerating charts...")
    os.makedirs("output", exist_ok=True)
    compare_policies(results)
    plot_prep_time_distribution(all_kpis)

    # Save individual CSVs
    for name, kpi in all_kpis.items():
        safe_name = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        kpi.to_csv(f"output/{safe_name}.csv")

    print("\nDone! Results in output/")


if __name__ == "__main__":
    main()
