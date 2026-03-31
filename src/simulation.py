import simpy
import numpy as np
from src import config
from src.kpi import KPICollector


class OrderGenerator:
    def __init__(self, materials, rng):
        self.rng = rng
        self.material_ids = [m["material_id"] for m in materials]
        consumptions = np.array([m["consumption"] for m in materials])
        self.weights = consumptions / consumptions.sum()
        self.inter_arrival = config.SHIFT_DURATION_MIN / config.ORDERS_PER_DAY
        self._order_counter = 0

    def next_order(self):
        self._order_counter += 1
        n_items = self.rng.integers(config.ITEMS_PER_ORDER_MIN, config.ITEMS_PER_ORDER_MAX + 1)
        # Sample materials weighted by consumption (with replacement for realism)
        indices = self.rng.choice(len(self.material_ids), size=n_items, replace=True, p=self.weights)
        items = list(set(self.material_ids[i] for i in indices))  # unique materials per order
        iat = self.rng.exponential(self.inter_arrival)
        return {
            "id": self._order_counter,
            "items": items,
            "inter_arrival_time": iat,
        }


class WarehouseSimulation:
    def __init__(self, warehouse, materials):
        self.warehouse = warehouse
        self.materials = materials
        self.rng = np.random.default_rng(config.RANDOM_SEED)
        self.kpi = KPICollector()
        self.order_gen = OrderGenerator(materials, self.rng)
        self.env = simpy.Environment()
        self.reach_trucks = simpy.Resource(self.env, capacity=config.NUM_REACH_TRUCKS)
        self.operators = simpy.Resource(self.env, capacity=config.NUM_OPERATORS)

    def run(self, duration=None):
        if duration is None:
            duration = config.SHIFT_DURATION_MIN * config.SIM_DAYS
        self.env.process(self._generate_orders(duration))
        self.env.process(self._milkrun_cycle(duration))
        self.env.run(until=duration)
        self.kpi.set_sim_duration(duration)

    def _generate_orders(self, duration):
        while self.env.now < duration:
            order = self.order_gen.next_order()
            self.env.process(self._process_order(order))
            yield self.env.timeout(order["inter_arrival_time"])

    def _process_order(self, order):
        with self.operators.request() as op_req:
            yield op_req
            op_start = self.env.now

            # Resolve material locations
            pick_list = self._resolve_picks(order["items"])
            if not pick_list:
                return

            # Sort by nearest-neighbor from kitting area
            pick_list = self._route_picks(pick_list)

            current_pos = "kitting_area"
            total_walk = 0.0
            total_wait = 0.0

            for pos_id in pick_list:
                # Walk to location
                dist = self.warehouse.travel_distance(current_pos, pos_id)
                walk_time = dist / config.OPERATOR_WALK_SPEED_M_PER_MIN
                yield self.env.timeout(walk_time)
                total_walk += dist

                # Reach truck if needed
                if self.warehouse.needs_reach_truck(pos_id):
                    wait_start = self.env.now
                    with self.reach_trucks.request() as rt_req:
                        yield rt_req
                        wait_dur = self.env.now - wait_start
                        total_wait += wait_dur
                        rt_time = self.warehouse.reach_truck_time(pos_id)
                        yield self.env.timeout(rt_time)
                        self.kpi.add_rt_busy(rt_time)

                # Pick
                yield self.env.timeout(config.OPERATOR_PICK_TIME)
                current_pos = pos_id

            # Walk back to kitting
            return_dist = self.warehouse.distance_to_kitting(current_pos)
            yield self.env.timeout(return_dist / config.OPERATOR_WALK_SPEED_M_PER_MIN)
            total_walk += return_dist

            op_end = self.env.now
            self.kpi.add_op_busy(op_end - op_start)
            self.kpi.record_order(
                order_id=order["id"],
                prep_time=op_end - op_start,
                wait_time=total_wait,
                walk_distance=total_walk,
                num_items=len(pick_list),
                timestamp=op_end,
            )

    def _resolve_picks(self, material_ids):
        """For each material, find a warehouse position. Skip if not in warehouse."""
        picks = []
        for mat_id in material_ids:
            locs = self.warehouse.material_locations.get(mat_id)
            if locs:
                # Pick from the first (closest) assigned location
                picks.append(locs[0])
        return picks

    def _route_picks(self, position_ids):
        """Nearest-neighbor routing from kitting area."""
        if not position_ids:
            return []
        remaining = list(position_ids)
        route = []
        current = "kitting_area"
        while remaining:
            nearest = min(remaining, key=lambda p: self.warehouse.travel_distance(current, p))
            route.append(nearest)
            remaining.remove(nearest)
            current = nearest
        return route

    def _milkrun_cycle(self, duration):
        while self.env.now < duration:
            yield self.env.timeout(config.MILKRUN_CYCLE_MIN)
            self.kpi.record_milkrun_departure(self.env.now)
