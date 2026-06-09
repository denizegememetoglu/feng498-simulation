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

import os
from collections import defaultdict

import numpy as np
import simpy

from src import config
from src.kpi import KPICollector


class OrderGenerator:
    """Synthetic Poisson order source. Used ONLY when the ZWM92 driver cache
    (output/zwm92_orders.json) is missing — production runs use
    ZWM92DistributionDriver. Kept as a silent fallback so dev/CI environments
    without SAP exports still run end-to-end. See ASSUMPTIONS §21 for the
    fitted-distribution driver narrative."""

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


class ZWM92DistributionDriver:
    """Arena-style order source: samples from distributions fitted to ZWM92.

    The May 26 review (advisor decision) was to retire the raw-trace replay
    in favour of fitted distributions so each replication is a statistically
    independent realisation of the same arrival process. The fit happens
    once at construction time (`src.zwm92.fit_distributions`) and writes
    the parameters to output/zwm92_fit.json for documentation.

    Sampling (2026-06-09 batch-arrival redesign — ZWM92 kit-orders arrive
    in same-timestamp dispatch bursts, mean 4.68 kits/batch):
      - inter_batch ~ Empirical(within-shift positive gaps; mean 5.36 min,
                      CV 2.04 — empirical kept because CV >> 1 rules out
                      the Exponential)
      - batch_size  ~ Empirical(same-timestamp run lengths)
      - per order in the batch:
          line     ~ Categorical(line_weights)
          n_items  ~ Empirical(n_items_per_order)
          items    ~ Categorical(per_line_material_weights[line])

    Materials not in the active master are filtered after sampling.

    Falls back to the synthetic OrderGenerator if the ZWM92 fit cache is
    missing (prints a [WARN] — results are then synthetic, not ZWM92-driven).
    """

    def __init__(self, materials, material_to_line, rng,
                 orders_cache: str = "output/zwm92_orders.json"):
        self._rng = rng
        self._order_counter = 0
        self._fallback: OrderGenerator | None = None
        self.fit_summary: dict | None = None

        if not os.path.exists(orders_cache):
            print(f"[WARN] ZWM92 cache not found at {orders_cache} — "
                  f"falling back to the SYNTHETIC OrderGenerator. Results "
                  f"are NOT ZWM92-driven; run `python -m src.zwm92` first.")
            self._fallback = OrderGenerator(materials, material_to_line, rng)
            return

        from src.zwm92 import fit_distributions
        fit = fit_distributions(orders_path=orders_cache)
        self.fit_summary = fit["summary"]

        material_ids = {m["material_id"] for m in materials}
        # Pre-filter the per-line material pools to the active master.
        self._lines: list[str] = []
        self._line_p: list[float] = []
        self._line_mids: dict[str, np.ndarray] = {}
        self._line_w: dict[str, np.ndarray] = {}
        for line, p in zip(fit["line_names"], fit["line_weights"]):
            ids = fit["per_line_material_ids"].get(line, [])
            ws = fit["per_line_material_weights"].get(line, [])
            filtered = [(m, w) for m, w in zip(ids, ws) if m in material_ids]
            if not filtered:
                continue
            mids = np.array([m for m, _ in filtered])
            wsa = np.array([w for _, w in filtered], dtype=float)
            wsa /= wsa.sum()
            self._lines.append(line)
            self._line_p.append(p)
            self._line_mids[line] = mids
            self._line_w[line] = wsa
        if not self._lines:
            print("[WARN] ZWM92 per-line material pools are empty after "
                  "filtering against the active master — falling back to "
                  "the SYNTHETIC OrderGenerator.")
            self._fallback = OrderGenerator(materials, material_to_line, rng)
            return

        line_p = np.array(self._line_p, dtype=float)
        line_p /= line_p.sum()
        self._line_p_norm = line_p
        fitted_mean = float(fit["iat_mean_min"]) or 1.0
        override = getattr(config, "IAT_MEAN_MIN_OVERRIDE", None)
        if override is not None and override > 0:
            # Sensitivity sweep handle — override the cached fit so the
            # arrival rate can be perturbed without regenerating ZWM92.
            self._iat_mean = float(override)
        else:
            self._iat_mean = fitted_mean
        # Empirical inter-batch gap pool; rescaled when the sensitivity
        # override shifts the mean (shape preserved, rate perturbed).
        iat_samples = fit.get("iat_samples") or []
        self._iat_pool = (np.array(iat_samples, dtype=float)
                          * (self._iat_mean / fitted_mean)
                          if iat_samples else None)
        batch_pool = fit.get("batch_size_empirical") or []
        self._batch_pool = (np.array(batch_pool, dtype=int)
                            if batch_pool else np.array([1]))
        self._n_items_pool = np.array(fit["n_items_empirical"], dtype=int)

    @property
    def is_distribution_driven(self) -> bool:
        return self._fallback is None

    def _sample_iat(self) -> float:
        """Inter-batch gap: empirical pool when fitted, Exp fallback."""
        if self._iat_pool is not None and len(self._iat_pool):
            return float(self._rng.choice(self._iat_pool))
        return float(self._rng.exponential(self._iat_mean))

    def _build_order(self, line: str) -> dict:
        self._order_counter += 1
        n_items = int(self._rng.choice(self._n_items_pool))
        n_items = max(1, min(n_items, len(self._line_mids[line])))
        idx = self._rng.choice(len(self._line_mids[line]),
                               size=n_items,
                               replace=False,
                               p=self._line_w[line])
        return {
            "id": self._order_counter,
            "items": self._line_mids[line][idx].tolist(),
            "line": line,
            "inter_arrival_time": 0.0,
        }

    def next_order(self):
        if self._fallback is not None:
            return self._fallback.next_order()
        line_idx = self._rng.choice(len(self._lines), p=self._line_p_norm)
        order = self._build_order(self._lines[line_idx])
        order["inter_arrival_time"] = self._sample_iat()
        return order

    def next_batch(self):
        """One arrival event = one dispatch batch.

        Returns (inter_arrival_min, [orders]) — the gap precedes the batch.
        The production LINE is sampled once per batch: 99.9% of observed
        multi-kit ZWM92 batches are single-line (a batch is one production
        order's kit release). Items are sampled per kit within that line.
        """
        if self._fallback is not None:
            o = self._fallback.next_order()
            return o["inter_arrival_time"], [o]
        iat = self._sample_iat()
        size = int(self._rng.choice(self._batch_pool))
        line_idx = self._rng.choice(len(self._lines), p=self._line_p_norm)
        line = self._lines[line_idx]
        orders = [self._build_order(line) for _ in range(max(1, size))]
        return iat, orders


# Back-compat alias — older imports still find the class even though
# behaviour switched to Arena-style sampling.
ZWM92TraceDriver = ZWM92DistributionDriver


def _sample_pick_time(rng, mean: float, sigma: float) -> float:
    """Lognormal sample with mean ≈ `mean` (matches the deterministic
    constant in expectation). `sigma` is the underlying normal's std on the
    log scale; small sigma → tightly clustered around mean, large sigma →
    heavy right tail. Returns a positive duration in minutes.
    """
    if mean <= 0:
        return 0.0
    if not getattr(config, "STOCHASTIC_PICK_TIMES", False) or sigma <= 0:
        return mean
    import math
    # Reparameterise so that E[X] == mean given sigma.
    mu = math.log(mean) - 0.5 * sigma * sigma
    return float(rng.lognormal(mu, sigma))


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
                 kardex_materials=None, seed=None, recorder=None):
        self.warehouse = warehouse
        self.materials = materials
        self.material_to_line = material_to_line or {}
        self.kardex_materials = kardex_materials or set()
        seed = seed if seed is not None else config.RANDOM_SEED
        # Two independent RNG streams (2026-06-09 CRN fix). A single shared
        # stream entangles arrivals with service-time draws: a policy that
        # makes one extra lognormal draw shifts every subsequent IAT, so
        # different policies saw different demand even at the same seed.
        # Separate streams keep the arrival trajectory identical across
        # policies (true common random numbers); the offset is arbitrary
        # but fixed so runs stay reproducible.
        self.arrival_rng = np.random.default_rng(seed)
        self.service_rng = np.random.default_rng(seed + 1_000_003)
        self.rng = self.service_rng  # back-compat alias
        self.kpi = KPICollector()
        # Opt-in JSONL recorder for sim_v2.html playback (M3 — AD-2 schema).
        # None ⇒ zero overhead, normal CI runs unchanged.
        self.recorder = recorder
        # Pseudo-IDs for the recorder so playback can render distinct
        # operators / RTs / orders without us tracking SimPy Resource slots.
        self._op_round_robin = 0
        self._rt_round_robin = 0
        if getattr(config, "TRACE_DRIVEN", True):
            self.order_gen = ZWM92DistributionDriver(
                materials, self.material_to_line, self.arrival_rng,
                orders_cache=getattr(config, "ZWM92_ORDERS_CACHE",
                                     "output/zwm92_orders.json"),
            )
        else:
            self.order_gen = OrderGenerator(materials, self.material_to_line,
                                            self.arrival_rng)
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
            # WARNING: layout.json lacks `kardex_stations: [{x,y}, ...]` — all
            # 4 Kardex units collapse to a single center point. Per-station
            # queueing dynamics are underestimated (one shared FIFO instead of
            # 4 parallel queues). Layout-geometry rebuild deferred — see
            # ASSUMPTIONS §23.
            kdx = warehouse.layout["kardex"]
            kx = kdx["x"] + kdx.get("width_m", 0.0) / 2
            ky = kdx["y"] + kdx.get("depth_m", 0.0) / 2
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
        if len(self._kardex_stations) == 1:
            return self._kardex_stations[0]
        # Nearest by ROUTED distance, not raw Manhattan — with multiple
        # stations the closest as-the-crow-flies unit can be behind a rack.
        def routed(s):
            try:
                return self.warehouse.route_between_points(
                    current_xy, s, mode="operator").distance
            except ValueError:
                return float("inf")
        return min(self._kardex_stations, key=routed)

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
        use_batches = (getattr(config, "BATCH_ARRIVALS", True)
                       and hasattr(self.order_gen, "next_batch"))
        while self.env.now < duration:
            wait = _next_active_minute(self.env.now)
            if wait > 0:
                yield self.env.timeout(wait)
                continue
            if use_batches:
                iat, orders = self.order_gen.next_batch()
            else:
                order = self.order_gen.next_order()
                if order is None:
                    # Trace exhausted — stop generating but let in-flight orders finish.
                    break
                iat, orders = order["inter_arrival_time"], [order]
            for order in orders:
                order["arrival_time"] = self.env.now
                self.kpi.orders_started += 1
                self.env.process(self._process_order(order))
            if self.recorder is not None:
                self.recorder.maybe_kpi_snapshot(self.env.now, self.kpi)
            yield self.env.timeout(iat)

    def _process_order(self, order):
        arrival = order["arrival_time"]
        if self.recorder is not None:
            self.recorder.order_start(arrival, order["id"], order.get("line"),
                                      len(order.get("items", [])))
        with self.operators.request() as op_req:
            yield op_req
            op_grant = self.env.now
            op_queue_wait = op_grant - arrival
            self._op_round_robin = (self._op_round_robin + 1) % max(1, config.NUM_OPERATORS)
            op_id = self._op_round_robin + 1
            if self.recorder is not None:
                self.recorder.op_grant(op_grant, order["id"], op_id, op_queue_wait)

            rack_picks, kardex_picks = self._resolve_picks(order["items"])
            if not rack_picks and not kardex_picks:
                # No decoded SAP slot and not Kardex-routed — flag separately
                # so it doesn't silently inflate orders_completed in policy KPIs.
                self.kpi.orders_with_no_locations += 1
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
                route = self.warehouse.route_to_position(current_xy, pos_id, mode="operator")
                target_xy = route.path[-1]
                dist = route.distance
                move_start = self.env.now
                yield self.env.timeout(dist / config.OPERATOR_WALK_SPEED_M_PER_MIN)
                if self.recorder is not None and dist > 0.01:
                    self.recorder.op_move(self.env.now, order["id"], op_id,
                                          current_xy, target_xy, dist, route.path,
                                          start_t=move_start)
                total_walk += dist

                pos_lock_ctx = (self._position_lock(pos_id).request()
                                if config.ENABLE_POSITION_LOCK else None)
                if pos_lock_ctx is not None:
                    yield pos_lock_ctx

                try:
                    if self.warehouse.needs_reach_truck(pos_id):
                        wait_start = self.env.now
                        rt_req = self.reach_trucks.request()
                        yield rt_req
                        rt_wait = self.env.now - wait_start
                        total_rt_wait += rt_wait
                        self._rt_round_robin = (self._rt_round_robin + 1) % max(1, config.NUM_REACH_TRUCKS)
                        rt_id = self._rt_round_robin + 1
                        rt_route = self.warehouse.route_to_position(
                            (config.REACH_TRUCK_DEPOT_X, config.REACH_TRUCK_DEPOT_Y),
                            pos_id,
                            mode="reach_truck",
                        )
                        travel = rt_route.distance / config.REACH_TRUCK_SPEED_M_PER_MIN
                        # Lift time is a level-dependent constant; only
                        # the pick/place portion is stochastic.
                        base_pp = config.REACH_TRUCK_PICK_PLACE_TIME
                        pp = _sample_pick_time(
                            self.service_rng, base_pp,
                            getattr(config, "REACH_TRUCK_PICK_TIME_SIGMA", 0.0))
                        lift = self.warehouse.reach_truck_time(pos_id) \
                               - base_pp + pp
                        rt_busy = travel + lift
                        if self.recorder is not None:
                            self.recorder.rt_dispatch(self.env.now, order["id"],
                                                      rt_id, pos_id, rt_wait,
                                                      rt_route.path,
                                                      travel_time_min=travel,
                                                      service_time_min=lift,
                                                      return_time_min=travel)
                        # Operator is blocked only until the pallet is
                        # delivered; the RT then drives back to the depot
                        # on its own (resource stays held — a truck that
                        # is returning cannot serve the next request).
                        # 2026-06-09 fix: the return leg used to be
                        # missing entirely (truck teleported home).
                        yield self.env.timeout(rt_busy)
                        self.kpi.add_rt_busy(rt_busy)
                        self.env.process(self._rt_return(rt_req, travel))
                    elif self.warehouse.can_pick_directly(pos_id):
                        yield self.env.timeout(_sample_pick_time(
                            self.service_rng, config.OPERATOR_PICK_TIME,
                            getattr(config, "OPERATOR_PICK_TIME_SIGMA", 0.0)))
                    else:
                        base = self.warehouse.manual_pick_time(pos_id)
                        op = config.OPERATOR_PICK_TIME
                        penalty = base - op  # the configured penalty share
                        op_s = _sample_pick_time(
                            self.service_rng, op,
                            getattr(config, "OPERATOR_PICK_TIME_SIGMA", 0.0))
                        pen_s = _sample_pick_time(
                            self.service_rng, penalty,
                            getattr(config, "MANUAL_PICK_PENALTY_SIGMA", 0.0))
                        yield self.env.timeout(op_s + pen_s)
                finally:
                    if pos_lock_ctx is not None:
                        self._position_locks[pos_id].release(pos_lock_ctx)

                self.kpi.record_pick(rack_id=pos.rack_id, material_id=mat_id)
                if self.recorder is not None:
                    self.recorder.pick(self.env.now, order["id"], op_id, pos, mat_id)
                current_xy = target_xy

            # Kardex picks: single trip to nearest carousel, ONE carousel
            # rotation amortized across all picks at that station (H1 fix —
            # previously per-item carousel+pick over-inflated Kardex time
            # by ~Nx). Operator holds the Kardex unit for the entire batch
            # instead of re-queueing per item.
            if kardex_picks:
                kx, ky = self._closest_kardex(current_xy)
                route = self.warehouse.route_between_points(current_xy, (kx, ky), mode="operator")
                dist = route.distance
                move_start = self.env.now
                yield self.env.timeout(dist / config.OPERATOR_WALK_SPEED_M_PER_MIN)
                if self.recorder is not None and dist > 0.01:
                    self.recorder.op_move(self.env.now, order["id"], op_id,
                                          current_xy, (kx, ky), dist, route.path,
                                          start_t=move_start)
                total_walk += dist
                with self.kardex.request() as kdx_req:
                    yield kdx_req
                    kdx_hold_start = self.env.now
                    # Single carousel rotation to surface the requested tray;
                    # picks then happen back-to-back at the same station.
                    yield self.env.timeout(_sample_pick_time(
                        self.service_rng, config.KARDEX_CAROUSEL_TIME,
                        getattr(config, "KARDEX_CAROUSEL_SIGMA", 0.0)))
                    for mat_id in kardex_picks:
                        yield self.env.timeout(_sample_pick_time(
                            self.service_rng, config.KARDEX_PICK_TIME,
                            getattr(config, "KARDEX_PICK_TIME_SIGMA", 0.0)))
                        self.kpi.record_pick(rack_id="KDX", material_id=mat_id)
                        if self.recorder is not None:
                            self.recorder.kardex_pick(self.env.now, order["id"],
                                                      op_id, (kx, ky), mat_id)
                    self.kpi.add_kardex_busy(self.env.now - kdx_hold_start)
                current_xy = (kx, ky)

            # Walk back to the line's kitting point
            return_route = self.warehouse.route_between_points(current_xy, start_xy, mode="operator")
            return_dist = return_route.distance
            move_start = self.env.now
            yield self.env.timeout(return_dist / config.OPERATOR_WALK_SPEED_M_PER_MIN)
            if self.recorder is not None and return_dist > 0.01:
                self.recorder.op_move(self.env.now, order["id"], op_id,
                                      current_xy, start_xy, return_dist, return_route.path,
                                      start_t=move_start)
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
            if self.recorder is not None:
                self.recorder.order_done(op_end, order["id"], total_walk,
                                         lead_time, prep_time,
                                         len(rack_picks) + len(kardex_picks))

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
            best_route = None
            best_dist = float("inf")
            for i, (_mid, pos_list) in enumerate(remaining):
                for p in pos_list:
                    candidate_route = self.warehouse.route_to_position(
                        (cur_x, cur_y), p, mode="operator"
                    )
                    d = candidate_route.distance
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
                        best_pos = p
                        best_route = candidate_route
            mid, _ = remaining.pop(best_idx)
            route.append((mid, best_pos))
            cur_x, cur_y = best_route.path[-1]
        return route

    def _rt_return(self, rt_req, return_travel_min: float):
        """Drive the reach truck back to the depot, then free it. Runs as a
        detached process so the operator doesn't wait for the return leg,
        but the truck stays unavailable (and busy) until it's home."""
        yield self.env.timeout(return_travel_min)
        self.kpi.add_rt_busy(return_travel_min)
        self.reach_trucks.release(rt_req)

    def _milkrun_cycle(self, duration):
        while self.env.now < duration:
            yield self.env.timeout(config.MILKRUN_CYCLE_MIN)
            self.kpi.record_milkrun_departure(self.env.now)
