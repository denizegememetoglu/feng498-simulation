from abc import ABC, abstractmethod
import math
from src import config


class SlottingPolicy(ABC):
    @abstractmethod
    def assign(self, materials, warehouse):
        """Assign materials to warehouse positions."""

    def _allocate_positions(self, material_id, consumption, total_consumption, warehouse, pool):
        """Allocate proportional positions from a pool. Returns number assigned."""
        daily = consumption / config.DATA_DAYS
        # At least 1 position, scale by share of consumption
        n_positions = max(1, math.ceil(daily / 50))  # ~50 units per pallet per day
        n_positions = min(n_positions, len(pool))
        for i in range(n_positions):
            warehouse.assign_material(material_id, pool[i])
        return pool[n_positions:]  # remaining pool


class HeuristicBaselinePolicy(SlottingPolicy):
    """SE's ABC-FMR class drives placement, but uses heuristic level pools
    (no SAP storage bin lookup). Kept as a control for the SAP-driven baseline.
    """

    def assign(self, materials, warehouse):
        warehouse.clear_assignments()
        fm_pool = warehouse.get_fast_mover_positions()
        mid_pool = warehouse.get_mid_level_positions()
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()

        for mat in materials:
            fmr = mat["se_fmr"]
            abc = mat["se_abc"]

            if fmr == "F" and fm_pool:
                # Fast movers -> fast mover racks
                warehouse.assign_material(mat["material_id"], fm_pool.pop(0))
            elif fmr == "M" and mid_pool:
                warehouse.assign_material(mat["material_id"], mid_pool.pop(0))
            elif fmr in ("R", "D") and upper_pool:
                warehouse.assign_material(mat["material_id"], upper_pool.pop(0))
            elif remaining_pool:
                warehouse.assign_material(mat["material_id"], remaining_pool.pop(0))


class UsageBasedABCPolicy(SlottingPolicy):
    """Team's reclassification: A (top 80%) -> best spots, B (80-95%) -> mid, C -> upper."""

    def assign(self, materials, warehouse):
        warehouse.clear_assignments()
        fm_pool = warehouse.get_fast_mover_positions()
        mid_pool = warehouse.get_mid_level_positions()
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()

        for mat in materials:
            abc = mat["team_abc"]
            if abc == "A" and fm_pool:
                warehouse.assign_material(mat["material_id"], fm_pool.pop(0))
            elif abc == "A" and mid_pool:
                # Overflow A items to mid level
                warehouse.assign_material(mat["material_id"], mid_pool.pop(0))
            elif abc == "B" and mid_pool:
                warehouse.assign_material(mat["material_id"], mid_pool.pop(0))
            elif abc == "B" and upper_pool:
                warehouse.assign_material(mat["material_id"], upper_pool.pop(0))
            elif abc == "C" and upper_pool:
                warehouse.assign_material(mat["material_id"], upper_pool.pop(0))
            elif remaining_pool:
                warehouse.assign_material(mat["material_id"], remaining_pool.pop(0))


class DoubleABCPolicy(SlottingPolicy):
    """Cross-classify by frequency (FMR) AND volume (team ABC).
    Priority: AF > BF > AM > CF > BM > AR > CM > BR > CR
    """
    PRIORITY = ["AF", "BF", "AM", "CF", "BM", "AR", "CM", "BR", "CR",
                "AD", "BD", "CD"]

    def assign(self, materials, warehouse):
        warehouse.clear_assignments()

        # Build combined class for each material
        for mat in materials:
            mat["_double_class"] = mat["team_abc"] + mat["se_fmr"]

        # Sort by priority
        priority_map = {cls: i for i, cls in enumerate(self.PRIORITY)}
        sorted_mats = sorted(
            materials,
            key=lambda m: priority_map.get(m["_double_class"], 99)
        )

        fm_pool = warehouse.get_fast_mover_positions()
        mid_pool = warehouse.get_mid_level_positions()
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()

        for mat in sorted_mats:
            dc = mat["_double_class"]
            priority = priority_map.get(dc, 99)

            if priority <= 1 and fm_pool:  # AF, BF
                warehouse.assign_material(mat["material_id"], fm_pool.pop(0))
            elif priority <= 4 and mid_pool:  # AM, CF, BM
                warehouse.assign_material(mat["material_id"], mid_pool.pop(0))
            elif priority <= 4 and fm_pool:
                warehouse.assign_material(mat["material_id"], fm_pool.pop(0))
            elif upper_pool:
                warehouse.assign_material(mat["material_id"], upper_pool.pop(0))
            elif remaining_pool:
                warehouse.assign_material(mat["material_id"], remaining_pool.pop(0))


class RealBaselinePolicy(SlottingPolicy):
    """The partner's actual placement read from the SAP `özet` Storage Bin column.

    For materials with a decoded bin that maps to a real (rack, bay) in the
    layout, place them at level 0 of that bin. For materials whose bin is
    Kardex (KDX*), unmapped, malformed, or missing, fall back to the heuristic
    level pools so all materials still get a slot — otherwise capacity drops
    and the comparison is unfair.

    Reports `placed_from_sap` / `placed_kardex` / `placed_fallback` counters
    so the report can quote a fidelity number.
    """

    def __init__(self, decoded_bins=None, kardex_materials=None):
        self.decoded_bins = decoded_bins or {}
        self.kardex_materials = kardex_materials or set()
        self.placed_from_sap = 0
        self.placed_kardex = 0
        self.placed_fallback = 0

    def assign(self, materials, warehouse):
        warehouse.clear_assignments()
        self.placed_from_sap = 0
        self.placed_kardex = 0
        self.placed_fallback = 0

        deferred = []
        for mat in materials:
            mid = mat["material_id"]
            decoded = self.decoded_bins.get(mid)
            if decoded is not None:
                rack, bay, pos = decoded
                pid = warehouse.sap_position_id(rack, bay, pos)
                if pid is not None and warehouse.positions[pid].material_id is None:
                    warehouse.assign_material(mid, pid)
                    self.placed_from_sap += 1
                    continue
            # Kardex-stored materials are not in any rack — track separately
            # but still assign a fallback slot so the simulation has a position
            # to dispatch from. Real Kardex picks have a different time profile;
            # that's a TODO May 20 (Sümeyra: Kardex pick ≈ instant after queue).
            if mid in self.kardex_materials:
                deferred.append((mat, "kardex"))
            else:
                deferred.append((mat, "fallback"))

        fm_pool = warehouse.get_fast_mover_positions()
        mid_pool = warehouse.get_mid_level_positions()
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()

        for mat, reason in deferred:
            fmr = mat["se_fmr"]
            target = None
            if fmr == "F" and fm_pool:
                target = fm_pool.pop(0)
            elif fmr == "M" and mid_pool:
                target = mid_pool.pop(0)
            elif fmr in ("R", "D") and upper_pool:
                target = upper_pool.pop(0)
            elif remaining_pool:
                target = remaining_pool.pop(0)
            if target is not None:
                warehouse.assign_material(mat["material_id"], target)
                if reason == "kardex":
                    self.placed_kardex += 1
                else:
                    self.placed_fallback += 1


class TravelDistancePolicy(SlottingPolicy):
    """Greedy optimal: highest consumption -> closest to kitting area."""

    def assign(self, materials, warehouse):
        warehouse.clear_assignments()
        # Materials already sorted by consumption desc from data_loader
        sorted_mats = sorted(materials, key=lambda m: m["consumption"], reverse=True)
        # Positions sorted by distance to kitting (closest first)
        all_positions = warehouse.get_available_positions()

        for mat in sorted_mats:
            if not all_positions:
                break
            warehouse.assign_material(mat["material_id"], all_positions.pop(0))


ALL_POLICIES = {
    "Baseline (Heuristic)": HeuristicBaselinePolicy,
    "Baseline (Actual SAP)": RealBaselinePolicy,
    "Usage-based ABC": UsageBasedABCPolicy,
    "Double ABC": DoubleABCPolicy,
    "Travel-distance Optimized": TravelDistancePolicy,
}
