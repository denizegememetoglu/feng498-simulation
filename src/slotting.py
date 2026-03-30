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


class BaselinePolicy(SlottingPolicy):
    """Schneider's current classification: use SE's ABC-FMR to place materials."""

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
    "Baseline (Schneider)": BaselinePolicy,
    "Usage-based ABC": UsageBasedABCPolicy,
    "Double ABC": DoubleABCPolicy,
    "Travel-distance Optimized": TravelDistancePolicy,
}
