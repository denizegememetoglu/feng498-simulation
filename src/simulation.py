"""Discrete-event simulation of operator picking.

The May 2026 review highlighted several modelling gaps; this version fixes
them all *without new field data* (timing constants are still placeholders
and get refined after the May 20 site visit).

  * `list(set(...))` silently deduplicated weighted samples — fixed.
  * Operator queue wait was invisible — now `op_queue_wait` is tracked
    separately from `prep_time` (operator-active) and `lead_time` (arrival
    to completion).
  * RT travel from the depot to the pick face was unmodelled — now added
    to RT busy time.
  * Orders sampled from the global material pool, ignoring the
    material→production-line join — line-based sampling is on by default.
  * The milk-run cycle did not interact with kits or resources — gated by
    `ENABLE_MILKRUN`, off by default.
  * Warmup / cooldown windows let the KPI exclude transients.

May 11 update:
  * Kardex (2766 materials) is a separate resource pool with carousel
    rotation time; no rack walk for those picks.
  * Multi-bin: a material can occupy multiple positions (özet duplicates).
    The simulation picks from the location nearest to current_pos.
  * Per-line kitting points: each order's start/end leg uses the
    production line's kitting point, not the global centroid.
  * Position lock: each pallet slot is a 1-capacity resource, so two
    operators can't pick from the same slot concurrently.
  * Shift breaks supported when `SHIFT_MODE == "daily"`.
"""

from collections import defaultdict

import numpy as np
import simpy

from src import config
from src.kpi import KPICollector


class OrderGenerator:
    def __init__(self, materials, material_to_line, rng):
        self.rng = rng
        self.materials = materials
        self.material_ids = [m["material_id"] for m in materials]
        self.consumption_by_id = {m["material_id"]: m["consumption"] for m in materials}
        consumptions = np.array([m["consumption"] for m in materials], dtype=float)
        self.global_weights = consumptions / consumptions.sum()

        self.by_line: dict[str, list[str]] = defaultdict(list)
        for m in materials:
            line = material_to_line.get(m["material_id"])
            if line:
                self.by_line[line].append(m["material_id"])
        self.line_names = list(self.by_line.keys())
        line_totals = np.array(
            [sum(self.consumption_by_id[mid] for mid in self.by_line[ln])
             for ln in self.line_names],
            dtype=float,
        )
        if line_totals.size and line_totals.sum() > 0:
            self.line_weights = line_totals / line_totals.sum()
        else:
            self.line_weights = None

        self._line_id_arrays: dict[str, np.ndarray] = {}
        self._line_weight_arrays: dict[str, np.ndarray] = {}
        for ln, mids in self.by_line.items():
            ids = np.array(mids)
            w = np.array([self.consumption_by_id[mid] for mid in mids], dtype=float)
            self._line_id_arrays[ln] = ids
            self._line_weight_arrays[ln] = w / w.sum()

        self.inter_arrival = config.SHIFT_DURATION_MIN / config.ORDERS_PER_DAY
        self._order_counter = 0

    def _sample_items_global(self, n_items: int) -> list[str]:
        n = min(n_items, len(self.material_ids))
        idx = self.rng.choice(len(self.material_ids), size=n, replace=False, p=self.global_weights)
        return [self.material_ids[i] for i in idx]

    def _sample_items_line(self, line: str, n_items: int) -> list[str]:
        ids = self._line_id_arrays[line]
        if len(ids) < n_items:
            base = list(ids)
            need = n_items - len(base)
            extras = self._sample_items_global(need + len(base))
            extras = [m for m in extras if m not in base][:need]
            return base + extras
        weights = self._line_weight_arrays[line]
        idx = self.rng.choice(len(ids), size=n_items, replace=False, p=weights)
        return [str(ids[i]) for i in idx]

    def next_order(self):
        self._order_counter += 1
        n_items = self.rng.integers(config.ITEMS_PER_ORDER_MIN, config.ITEMS_PER_ORDER_MAX + 1)
        line = None
        if config.LINE_BASED_SAMPLING and self.line_weights is not None:
            line_idx = self.rng.choice(len(self.line_names), p=self.line_weights)
            line = self.line_names[line_idx]
            items = self._sample_items_line(line, n_items)
        else:
            items = self._sample_items_global(n_items)
        iat = self.rng.exponential(self.inter_arrival)
        return {
            "id": self._order_counter,
            "items": items,
            "line": line,
            "inter_arrival_time": iat,
        }


def _shift_is_active(t: float) -> bool:
    """`daily` mode gates orders to the shift window of each 24h day AND
    respects BREAK_SCHEDULE within that window. Continuous mode is always
    active."""
    if config.SHIFT_MODE != "daily":
        return True
    day_minute = t % 1440.0
    if day_minute >= config.SHIFT_DURATION_MIN:
        return False
    for (start, dur) in config.BREAK_SCHEDULE:
        if start <= day_minute < start + dur:
            return False
    return True


def _next_active_minute(t: float) -> float:
    """How long until the next active minute under SHIFT_MODE=daily."""
    if config.SHIFT_MODE != "daily":
        return 0.0
    day_minute = t % 1440.0
    # End of shift?
    if day_minute >= config.SHIFT_DURATION_MIN:
        return 1440.0 - day_minute
    # In a break?
    for (start, dur) in config.BREAK_SCHEDULE:
        if start <= day_minute < start + dur:
            return (start + dur) - day_minute
    return 0.0


class WarehouseSimulation:
    def __init__(self, warehouse, materials, material_to_line=None,
                 kardex_materials=None, seed=None):
        self.warehouse = warehouse
        self.materials = materials
        self.material_to_line = material_to_line or {}
        self.kardex_materials = kardex_materials or set()
        seed = seed if seed is not None else config.RANDOM_SEED
        self.rng = np.random.default_rng(seed)
        self.kpi = KPICollector()
        self.order_gen = OrderGenerator(materials, self.material_to_line, self.rng)
        self.env = simpy.Environment()
        self.reach_trucks = simpy.Resource(self.env, capacity=config.NUM_REACH_TRUCKS)
        self.operators = simpy.Resource(self.env, capacity=config.NUM_OPERATORS)
        self.kardex = simpy.Resource(self.env, capacity=config.NUM_KARDEX_UNITS)
        # Lazy per-position locks (only create for positions actually visited).
        self._position_locks: dict[str, simpy.Resource] = {}

        # Pre-resolve per-line kitting points so we don't dig into layout dict
        # every order.
        self._line_kitting: dict[str, tuple[float, float]] = {}
        for entry in warehouse.layout.get("production_lines", []):
            kp = entry.get("kitting_point")
            if kp and len(kp) == 2:
                self._line_kitting[entry["name"]] = (float(kp[0]), float(kp[1]))
        # Kardex station coords for walk distance from kitting to Kardex.
        self._kardex_stations = [
            (s.get("x", warehouse.layout["kardex"]["x"]),
             s.get("y", warehouse.layout["kardex"]["y"]))
            for s in warehouse.layout.get("kardex_stations", [])
        ]
        if not self._kardex_stations:
            kx = warehouse.layout["kardex"]["x"]
            ky = warehouse.layout["kardex"]["y"]
            self._kardex_stations = [(kx, ky)]

    def _position_lock(self, position_id: str) -> simpy.Resource:
        lock = self._position_locks.get(position_id)
        if lock is None:
            lock = simpy.Resource(self.env, capacity=1)
            self._position_locks[position_id] = lock
        return lock

    def _kitting_xy_for_line(self, line: str | None) -> tuple[float, float]:
        if config.PER_LINE_KITTING and line and line in self._line_kitting:
            return self._line_kitting[line]
        return (self.warehouse.kitting_x, self.warehouse.kitting_y)

    def _distance(self, ax, ay, bx, by) -> float:
        return abs(ax - bx) + abs(ay - by)

    def _walk_distance_from(self, current_xy, position_id):
        pos = self.warehouse.positions[position_id]
        return self._distance(current_xy[0], current_xy[1], pos.x, pos.y)

    def _closest_kardex(self, current_xy):
        return min(self._kardex_stations,
                   key=lambda s: self._distance(current_xy[0], current_xy[1], s[0], s[1]))

    def run(self, duration=None):
        if duration is None:
            if config.SHIFT_MODE == "daily":
                duration = 1440.0 * config.SIM_DAYS
            else:
                duration = config.SHIFT_DURATION_MIN * config.SIM_DAYS
        self.env.process(self._generate_orders(duration))
        if config.ENABLE_MILKRUN:
            self.env.process(self._milkrun_cycle(duration))
        self.env.run(until=duration)
        self.kpi.set_sim_duration(duration, config.WARMUP_MIN, config.COOLDOWN_MIN)

    def _generate_orders(self, duration):
        while self.env.now < duration:
            wait = _next_active_minute(self.env.now)
            if wait > 0:
                yield self.env.timeout(wait)
                continue
            order = self.order_gen.next_order()
            order["arrival_time"] = self.env.now
            self.env.process(self._process_order(order))
            yield self.env.timeout(order["inter_arrival_time"])

    def _process_order(self, order):
        arrival = order["arrival_time"]
        with self.operators.request() as op_req:
            yield op_req
            op_grant = self.env.now
            op_queue_wait = op_grant - arrival

            rack_picks, kardex_picks = self._resolve_picks(order["items"])
            if not rack_picks and not kardex_picks:
                self.kpi.record_order(
                    order_id=order["id"],
                    arrival_time=arrival,
                    op_queue_wait=op_queue_wait,
                    rt_queue_wait=0.0,
                    prep_time=0.0,
                    lead_time=op_queue_wait,
                    walk_distance=0.0,
                    num_items=0,
                    line=order.get("line"),
                    timestamp=self.env.now,
                )
                return

            rack_picks = self._route_rack_picks(rack_picks, order.get("line"))

            start_xy = self._kitting_xy_for_line(order.get("line"))
            current_xy = start_xy
            total_walk = 0.0
            total_rt_wait = 0.0

            # Rack-side picks
            for mat_id, pos_id in rack_picks:
                pos = self.warehouse.positions[pos_id]
                dist = self._distance(current_xy[0], current_xy[1], pos.x, pos.y)
                yield self.env.timeout(dist / config.OPERATOR_WALK_SPEED_M_PER_MIN)
                total_walk += dist

                pos_lock_ctx = (self._position_lock(pos_id).request()
                                if config.ENABLE_POSITION_LOCK else None)
                if pos_lock_ctx is not None:
                    yield pos_lock_ctx

                try:
                    if self.warehouse.needs_reach_truck(pos_id):
                        wait_start = self.env.now
                        with self.reach_trucks.request() as rt_req:
                            yield rt_req
                            rt_wait = self.env.now - wait_start
                            total_rt_wait += rt_wait
                            travel = self.warehouse.reach_truck_travel_time(pos_id)
                            lift = self.warehouse.reach_truck_time(pos_id)
                            rt_busy = travel + lift
                            yield self.env.timeout(rt_busy)
                            self.kpi.add_rt_busy(rt_busy)
                    elif self.warehouse.can_pick_directly(pos_id):
                        yield self.env.timeout(config.OPERATOR_PICK_TIME)
                    else:
                        yield self.env.timeout(self.warehouse.manual_pick_time(pos_id))
                finally:
                    if pos_lock_ctx is not None:
                        self._position_locks[pos_id].release(pos_lock_ctx)

                self.kpi.record_pick(rack_id=pos.rack_id, material_id=mat_id)
                current_xy = (pos.x, pos.y)

            # Kardex picks (single trip to nearest carousel, queue per pick).
            if kardex_picks:
                kx, ky = self._closest_kardex(current_xy)
                dist = self._distance(current_xy[0], current_xy[1], kx, ky)
                yield self.env.timeout(dist / config.OPERATOR_WALK_SPEED_M_PER_MIN)
                total_walk += dist
                for mat_id in kardex_picks:
                    with self.kardex.request() as kdx_req:
                        yield kdx_req
                        yield self.env.timeout(config.KARDEX_CAROUSEL_TIME)
                        yield self.env.timeout(config.KARDEX_PICK_TIME)
                    self.kpi.record_pick(rack_id="KDX", material_id=mat_id)
                current_xy = (kx, ky)

            # Walk back to the line's kitting point
            return_dist = self._distance(current_xy[0], current_xy[1], start_xy[0], start_xy[1])
            yield self.env.timeout(return_dist / config.OPERATOR_WALK_SPEED_M_PER_MIN)
            total_walk += return_dist

            op_end = self.env.now
            prep_time = op_end - op_grant
            lead_time = op_end - arrival
            self.kpi.add_op_busy(prep_time)
            self.kpi.record_order(
                order_id=order["id"],
                arrival_time=arrival,
                op_queue_wait=op_queue_wait,
                rt_queue_wait=total_rt_wait,
                prep_time=prep_time,
                lead_time=lead_time,
                walk_distance=total_walk,
                num_items=len(rack_picks) + len(kardex_picks),
                line=order.get("line"),
                timestamp=op_end,
            )

    def _resolve_picks(self, material_ids):
        """Split the order items into rack picks and Kardex picks.

        Rack picks become a list of (material_id, position_id) using the
        first assigned location (multi-bin nearest-pick happens later in
        `_route_rack_picks`). Kardex picks are just material ids; they all
        go through the Kardex resource.
        """
        rack_picks = []
        kardex_picks = []
        for mat_id in material_ids:
            if config.ENABLE_KARDEX_RESOURCE and mat_id in self.kardex_materials:
                kardex_picks.append(mat_id)
                continue
            locs = self.warehouse.material_locations.get(mat_id)
            if locs:
                rack_picks.append((mat_id, locs))  # full list, picked nearest
        return rack_picks, kardex_picks

    def _route_rack_picks(self, picks, line):
        """Greedy nearest-neighbor from the line's kitting point. For
        multi-bin materials, choose the bin closest to the current
        position at decision time."""
        if not picks:
            return []
        remaining = list(picks)  # each entry: (mat_id, [pos_id, pos_id, ...])
        route: list[tuple[str, str]] = []
        cur_x, cur_y = self._kitting_xy_for_line(line)

        while remaining:
            best_idx = 0
            best_pos = None
            best_dist = float("inf")
            for i, (_mid, pos_list) in enumerate(remaining):
                for p in pos_list:
                    pos = self.warehouse.positions[p]
                    d = abs(pos.x - cur_x) + abs(pos.y - cur_y)
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
                        best_pos = p
            mid, _ = remaining.pop(best_idx)
            route.append((mid, best_pos))
            pos = self.warehouse.positions[best_pos]
            cur_x, cur_y = pos.x, pos.y
        return route

    def _milkrun_cycle(self, duration):
        while self.env.now < duration:
            yield self.env.timeout(config.MILKRUN_CYCLE_MIN)
            self.kpi.record_milkrun_departure(self.env.now)
