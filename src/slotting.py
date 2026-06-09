from abc import ABC, abstractmethod


class SlottingPolicy(ABC):
    def __init__(self, kardex_materials=None):
        self.kardex_materials = kardex_materials or set()

    def rack_materials(self, materials):
        """Materials that need rack slots. Kardex materials stay out of rack
        capacity for every policy so automated-storage items are not silently
        treated as pallet-rack items."""
        return [m for m in materials if m["material_id"] not in self.kardex_materials]

    @staticmethod
    def pop_free(pool, warehouse):
        while pool:
            pid = pool.pop(0)
            if warehouse.positions[pid].material_id is None:
                return pid
        return None

    @abstractmethod
    def assign(self, materials, warehouse):
        """Assign materials to warehouse positions."""


class HeuristicBaselinePolicy(SlottingPolicy):
    """SE's ABC-FMR class drives placement, but uses heuristic level pools
    (no SAP storage bin lookup). Kept as a control for the SAP-driven baseline.
    """

    def assign(self, materials, warehouse):
        materials = self.rack_materials(materials)
        warehouse.clear_assignments()
        fm_pool = warehouse.get_fast_mover_positions()
        mid_pool = warehouse.get_mid_level_positions()
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()

        for mat in materials:
            fmr = mat["se_fmr"]

            if fmr == "F" and fm_pool:
                # Fast movers -> fast mover racks
                target = self.pop_free(fm_pool, warehouse)
            elif fmr == "M" and mid_pool:
                target = self.pop_free(mid_pool, warehouse)
            elif fmr in ("R", "D") and upper_pool:
                target = self.pop_free(upper_pool, warehouse)
            elif remaining_pool:
                target = self.pop_free(remaining_pool, warehouse)
            else:
                target = None
            if target is not None:
                warehouse.assign_material(mat["material_id"], target)


class UsageBasedABCPolicy(SlottingPolicy):
    """Team's reclassification: A (top 80%) -> best spots, B (80-95%) -> mid, C -> upper."""

    def assign(self, materials, warehouse):
        materials = self.rack_materials(materials)
        warehouse.clear_assignments()
        fm_pool = warehouse.get_fast_mover_positions()
        mid_pool = warehouse.get_mid_level_positions()
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()

        for mat in materials:
            abc = mat["team_abc"]
            if abc == "A" and fm_pool:
                target = self.pop_free(fm_pool, warehouse)
            elif abc == "A" and mid_pool:
                # Overflow A items to mid level
                target = self.pop_free(mid_pool, warehouse)
            elif abc == "B" and mid_pool:
                target = self.pop_free(mid_pool, warehouse)
            elif abc == "B" and upper_pool:
                target = self.pop_free(upper_pool, warehouse)
            elif abc == "C" and upper_pool:
                target = self.pop_free(upper_pool, warehouse)
            elif remaining_pool:
                target = self.pop_free(remaining_pool, warehouse)
            else:
                target = None
            if target is not None:
                warehouse.assign_material(mat["material_id"], target)


class DoubleABCPolicy(SlottingPolicy):
    """Cross-classify by frequency (FMR) AND volume (team ABC).
    Priority: AF > BF > AM > CF > BM > AR > CM > BR > CR
    """
    PRIORITY = ["AF", "BF", "AM", "CF", "BM", "AR", "CM", "BR", "CR",
                "AD", "BD", "CD"]

    def assign(self, materials, warehouse):
        materials = self.rack_materials(materials)
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
                target = self.pop_free(fm_pool, warehouse)
            elif priority <= 4 and mid_pool:  # AM, CF, BM
                target = self.pop_free(mid_pool, warehouse)
            elif priority <= 4 and fm_pool:
                target = self.pop_free(fm_pool, warehouse)
            elif upper_pool:
                target = self.pop_free(upper_pool, warehouse)
            elif remaining_pool:
                target = self.pop_free(remaining_pool, warehouse)
            else:
                target = None
            if target is not None:
                warehouse.assign_material(mat["material_id"], target)


class RealBaselinePolicy(SlottingPolicy):
    """The partner's actual placement read from the SAP `özet` Storage Bin column.

    `decoded_bins` is now `dict[str, list[(rack, bay, pos)]]` — a material
    can have multiple bins (forward + reserve, or multiple slots for high-
    volume items). We assign the material to ALL of its decoded bins that
    are still free; the simulation picks from the closest available one.

    Materials whose bin is Kardex (KDX*) are routed to the Kardex resource at
    simulation time (no rack slot needed). Materials with no decoded rack
    bin and no Kardex membership fall back to the heuristic level pools so
    capacity isn't artificially reduced.

    Reports `placed_from_sap` / `placed_kardex` / `placed_fallback` counters
    (counting MATERIALS, not slots) so the report can quote a fidelity
    number that's comparable to the older single-bin runs.
    """

    def __init__(self, decoded_bins=None, kardex_materials=None):
        super().__init__(kardex_materials=kardex_materials)
        self.decoded_bins = decoded_bins or {}
        self.placed_from_sap = 0       # materials with >= 1 SAP slot assigned
        self.placed_kardex = 0         # kardex-routed (no rack slot needed)
        self.placed_fallback = 0       # heuristic-pool fallback
        self.sap_slots_assigned = 0    # total slots placed via SAP (>= materials)

    def assign(self, materials, warehouse):
        warehouse.clear_assignments()
        self.placed_from_sap = 0
        self.placed_kardex = 0
        self.placed_fallback = 0
        self.sap_slots_assigned = 0

        deferred = []
        for mat in materials:
            mid = mat["material_id"]
            decoded_list = self.decoded_bins.get(mid) or []
            placed_any = False
            for (rack, bay, pos) in decoded_list:
                if hasattr(warehouse, "sap_position_ids"):
                    candidate_ids = warehouse.sap_position_ids(rack, bay, pos)
                else:
                    pid = warehouse.sap_position_id(rack, bay, pos)
                    candidate_ids = [pid] if pid is not None else []
                free_pid = next(
                    (
                        pid for pid in candidate_ids
                        if warehouse.positions[pid].material_id is None
                    ),
                    None,
                )
                if free_pid is not None:
                    warehouse.assign_material(mid, free_pid)
                    self.sap_slots_assigned += 1
                    placed_any = True
            if placed_any:
                self.placed_from_sap += 1
                continue
            # Kardex-only materials don't need a rack slot — the simulation
            # dispatches them to the Kardex resource directly. We still mark
            # them so the counters add up.
            if mid in self.kardex_materials:
                self.placed_kardex += 1
                continue
            deferred.append((mat, "fallback"))

        fm_pool = warehouse.get_fast_mover_positions()
        mid_pool = warehouse.get_mid_level_positions()
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()

        for mat, _reason in deferred:
            fmr = mat["se_fmr"]
            target = None
            if fmr == "F" and fm_pool:
                target = self.pop_free(fm_pool, warehouse)
            elif fmr == "M" and mid_pool:
                target = self.pop_free(mid_pool, warehouse)
            elif fmr in ("R", "D") and upper_pool:
                target = self.pop_free(upper_pool, warehouse)
            elif remaining_pool:
                target = self.pop_free(remaining_pool, warehouse)
            if target is not None:
                warehouse.assign_material(mat["material_id"], target)
                self.placed_fallback += 1


class TravelDistancePolicy(SlottingPolicy):
    """Greedy optimal: highest pick frequency -> closest to kitting area.

    When `picks_by_material` is provided (e.g. read from ZWM92 dispatch
    counts), sort by real pick frequency. Otherwise fall back to the SAP
    `consumption` column — the legacy proxy that underweights low-volume
    but high-frequency materials. C3 fix: prior versions silently used
    consumption even when ZWM92 picks were available.
    """

    def __init__(self, picks_by_material: dict[str, int] | None = None, kardex_materials=None):
        super().__init__(kardex_materials=kardex_materials)
        self.picks_by_material = picks_by_material or {}

    def assign(self, materials, warehouse):
        materials = self.rack_materials(materials)
        warehouse.clear_assignments()
        freq = self.picks_by_material

        def _sort_key(m):
            mid = m["material_id"]
            # Real ZWM92 pick frequency beats consumption proxy when present.
            return freq.get(mid, m["consumption"])

        sorted_mats = sorted(materials, key=_sort_key, reverse=True)
        all_positions = warehouse.get_available_positions()

        for mat in sorted_mats:
            if not all_positions:
                break
            target = self.pop_free(all_positions, warehouse)
            if target is not None:
                warehouse.assign_material(mat["material_id"], target)


class LineAwareSlottingPolicy(SlottingPolicy):
    """Proposed improvement (2026-06-09): congestion- and line-aware slotting.

    Why the existing 'improvement' policies lose under realistic load:
      * TravelDistancePolicy sorts ALL levels by distance to the CENTRAL
        kitting centroid, so the most-picked materials land on
        RT-required levels near that point — every pick then queues a
        reach truck (measured: RT util 43.7% vs baseline 20.9%, lead
        time 2x) and orders don't even START at the central point any
        more (per-line kitting points cover 76% of pick volume).

    Rules (greedy over materials sorted by real ZWM92 pick frequency):
      1. origin(material) = its production line's kitting point from
         layout.json `production_lines` (fallback: central centroid);
      2. picked materials take the nearest FREE position by ROUTED
         distance from that origin among positions that do NOT need a
         reach truck (kit-corridor level < FAST_MOVER_MAX_LEVEL, or a
         manual-pick level), spreading load across the per-line
         corridors by construction;
      3. when a line's no-RT space runs out, fall back to the nearest
         RT-served position from the same origin;
      4. zero-pick materials go to upper/reserve levels last, keeping
         prime positions for live SKUs.
    """

    def __init__(self, picks_by_material: dict[str, int] | None = None,
                 material_to_line: dict[str, str] | None = None,
                 kardex_materials=None):
        super().__init__(kardex_materials=kardex_materials)
        self.picks_by_material = picks_by_material or {}
        self.material_to_line = material_to_line or {}

    def _line_origins(self, warehouse) -> dict[str, tuple[float, float]]:
        origins = {}
        for entry in warehouse.layout.get("production_lines", []):
            kp = entry.get("kitting_point")
            if kp and len(kp) == 2:
                origins[entry["name"]] = (float(kp[0]), float(kp[1]))
        return origins

    def assign(self, materials, warehouse):
        materials = self.rack_materials(materials)
        warehouse.clear_assignments()

        origins = self._line_origins(warehouse)
        central = (warehouse.kitting_x, warehouse.kitting_y)

        # Pre-sort every position once per origin (routed distance). The
        # shared route cache makes this cheap after the first replication.
        all_pids = list(warehouse.positions.keys())

        def sorted_pools(origin):
            scored = []
            for pid in all_pids:
                try:
                    d = warehouse.route_to_position(origin, pid).distance
                except ValueError:
                    continue
                scored.append((d, pid))
            scored.sort()
            no_rt = [pid for _d, pid in scored
                     if not warehouse.needs_reach_truck(pid)]
            rt = [pid for _d, pid in scored
                  if warehouse.needs_reach_truck(pid)]
            return no_rt, rt

        pools = {None: sorted_pools(central)}
        for line, origin in origins.items():
            pools[line] = sorted_pools(origin)

        freq = self.picks_by_material
        picked = [m for m in materials if freq.get(m["material_id"], 0) > 0]
        unpicked = [m for m in materials if freq.get(m["material_id"], 0) <= 0]
        picked.sort(key=lambda m: freq[m["material_id"]], reverse=True)

        for mat in picked:
            mid = mat["material_id"]
            line = self.material_to_line.get(mid)
            no_rt, rt = pools.get(line if line in pools else None,
                                  pools[None])
            target = self.pop_free(no_rt, warehouse) or self.pop_free(rt, warehouse)
            if target is not None:
                warehouse.assign_material(mid, target)

        # Reserve stock: upper levels first so prime slots stay free for
        # any remaining picked materials in future replications.
        upper_pool = warehouse.get_upper_level_positions()
        remaining_pool = warehouse.get_available_positions()
        for mat in unpicked:
            target = (self.pop_free(upper_pool, warehouse)
                      or self.pop_free(remaining_pool, warehouse))
            if target is not None:
                warehouse.assign_material(mat["material_id"], target)


ALL_POLICIES = {
    "Baseline (Heuristic)": HeuristicBaselinePolicy,
    "Baseline (Actual SAP)": RealBaselinePolicy,
    "Usage-based ABC": UsageBasedABCPolicy,
    "Double ABC": DoubleABCPolicy,
    "Travel-distance Optimized": TravelDistancePolicy,
    "Line-aware Slotting": LineAwareSlottingPolicy,
}
