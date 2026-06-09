"""2x-load robustness check: SAP baseline vs Line-aware Slotting.

Runs both policies at IAT_MEAN_MIN_OVERRIDE=2.68 (≈2x arrival rate),
3 seeds x 3 days, WITHOUT touching the main outputs. Writes
output/stress_test.json and prints a summary — the defense answer to
'is the Line-aware win an artifact of the calibrated arrival rate?'
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src import config
from src.data_loader import preprocess
from src.main import _instantiate_policy
from src.simulation import WarehouseSimulation
from src.slotting import ALL_POLICIES
from src.warehouse import Warehouse

POLICIES = ["Baseline (Actual SAP)", "Line-aware Slotting"]
SEEDS = [42, 43, 44]
SIM_DAYS = 3
IAT_OVERRIDE = 2.68  # ≈2x the fitted inter-batch rate


def main():
    snapshot = (config.IAT_MEAN_MIN_OVERRIDE, config.SIM_DAYS)
    config.IAT_MEAN_MIN_OVERRIDE = IAT_OVERRIDE
    config.SIM_DAYS = SIM_DAYS
    data = preprocess(write_stats=False)
    results = {}
    try:
        for name in POLICIES:
            reps = []
            for seed in SEEDS:
                wh = Warehouse()
                policy = _instantiate_policy(ALL_POLICIES[name], data)
                policy.assign(data["materials"], wh)
                sim = WarehouseSimulation(
                    wh, data["materials"],
                    material_to_line=data["material_to_line"],
                    kardex_materials=data["kardex_materials"], seed=seed)
                sim.run()
                s = sim.kpi.summary()
                reps.append({k: s[k] for k in (
                    "avg_lead_time", "avg_total_wait",
                    "reach_truck_utilization", "throughput_orders_per_day",
                    "orders_started", "orders_completed")})
            mean = {k: sum(r[k] for r in reps) / len(reps) for k in reps[0]}
            results[name] = {"reps": reps, "mean": mean}
            print(f"{name}: lead={mean['avg_lead_time']:.2f} min  "
                  f"wait={mean['avg_total_wait']:.2f}  "
                  f"RT util={mean['reach_truck_utilization']:.3f}")
    finally:
        config.IAT_MEAN_MIN_OVERRIDE, config.SIM_DAYS = snapshot
    payload = {"iat_override_min": IAT_OVERRIDE, "sim_days": SIM_DAYS,
               "seeds": SEEDS, "results": results}
    with open("output/stress_test.json", "w") as f:
        json.dump(payload, f, indent=2)
    print("-> output/stress_test.json")


if __name__ == "__main__":
    main()
