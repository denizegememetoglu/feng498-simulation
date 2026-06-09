"""Export per-policy slot assignments (no simulation run needed).

Writes output/<safe_name>_assignments.csv with one row per assigned
material: material_id, position_id, rack, bay, level, needs_rt,
zwm92_picks. Assignment is deterministic per policy, so this is the
same placement every replication uses. The viewer's X14 re-slotting
panel joins the Actual-SAP and Line-aware files to produce the
actionable move list.
"""

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.data_loader import preprocess
from src.main import _instantiate_policy, _load_picks_by_material, _safe_name
from src.slotting import ALL_POLICIES
from src.warehouse import Warehouse


def main():
    data = preprocess(write_stats=False)
    picks = _load_picks_by_material()
    for name, cls in ALL_POLICIES.items():
        wh = Warehouse()
        policy = _instantiate_policy(cls, data)
        policy.assign(data["materials"], wh)
        path = f"output/{_safe_name(name)}_assignments.csv"
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["material_id", "position_id", "rack", "bay",
                        "level", "needs_rt", "zwm92_picks"])
            for mid, locs in sorted(wh.material_locations.items()):
                for pid in locs:
                    pos = wh.positions[pid]
                    w.writerow([mid, pid, pos.rack_id, pos.bay_code,
                                pos.level, int(wh.needs_reach_truck(pid)),
                                picks.get(mid, 0)])
        print(f"{name}: {sum(len(v) for v in wh.material_locations.values())} "
              f"slots -> {path}")


if __name__ == "__main__":
    main()
