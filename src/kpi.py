from collections import Counter
from dataclasses import dataclass, field
import statistics

import numpy as np


@dataclass
class OrderRecord:
    order_id: int
    arrival_time: float
    op_queue_wait: float
    rt_queue_wait: float
    prep_time: float          # operator-active duration (after op grant)
    lead_time: float          # arrival -> completion (includes op queue)
    walk_distance: float
    num_items: int
    line: str | None
    timestamp: float          # completion timestamp


class KPICollector:
    def __init__(self):
        self.orders: list[OrderRecord] = []
        self.milkrun_departures: list[float] = []
        self._rt_busy_time = 0.0
        self._op_busy_time = 0.0
        self._sim_duration = 0.0
        self._warmup = 0.0
        self._cooldown = 0.0
        # Validation telemetry: pick counts by rack and by material across the
        # whole run (irrespective of warmup window — full data is what we need
        # for chi-square vs. SAP). Use `_active_orders` for windowed averages.
        self.picks_by_rack: Counter = Counter()
        self.picks_by_material: Counter = Counter()
        # Surface util overflow rather than silently capping it.
        self.util_overflow: list[tuple[str, float]] = []

    def record_order(self, *, order_id, arrival_time, op_queue_wait,
                     rt_queue_wait, prep_time, lead_time, walk_distance,
                     num_items, line, timestamp):
        self.orders.append(OrderRecord(
            order_id=order_id,
            arrival_time=arrival_time,
            op_queue_wait=op_queue_wait,
            rt_queue_wait=rt_queue_wait,
            prep_time=prep_time,
            lead_time=lead_time,
            walk_distance=walk_distance,
            num_items=num_items,
            line=line,
            timestamp=timestamp,
        ))

    def record_milkrun_departure(self, time):
        self.milkrun_departures.append(time)

    def record_pick(self, rack_id: str, material_id: str):
        self.picks_by_rack[rack_id] += 1
        self.picks_by_material[material_id] += 1

    def add_rt_busy(self, duration):
        self._rt_busy_time += duration

    def add_op_busy(self, duration):
        self._op_busy_time += duration

    def set_sim_duration(self, duration, warmup=0.0, cooldown=0.0):
        self._sim_duration = duration
        self._warmup = warmup
        self._cooldown = cooldown

    def _active_orders(self):
        """Orders whose arrival fell inside the [warmup, duration-cooldown] window."""
        lo = self._warmup
        hi = self._sim_duration - self._cooldown
        return [o for o in self.orders if lo <= o.arrival_time < hi]

    def summary(self, num_reach_trucks=7, num_operators=4):
        active = self._active_orders()
        if not active:
            return {"orders_completed": 0}

        prep_times = np.array([o.prep_time for o in active])
        rt_waits = np.array([o.rt_queue_wait for o in active])
        op_waits = np.array([o.op_queue_wait for o in active])
        leads = np.array([o.lead_time for o in active])
        distances = np.array([o.walk_distance for o in active])

        # Utilization compares cumulative busy time to cumulative resource
        # capacity across the entire simulation (busy time is recorded for
        # every order, not just those in the active window).
        total_window = max(self._sim_duration, 1.0)
        rt_capacity = num_reach_trucks * total_window
        op_capacity = num_operators * total_window
        rt_util_raw = self._rt_busy_time / rt_capacity if rt_capacity > 0 else 0.0
        op_util_raw = self._op_busy_time / op_capacity if op_capacity > 0 else 0.0
        if rt_util_raw > 1.0:
            self.util_overflow.append(("reach_truck", rt_util_raw))
        if op_util_raw > 1.0:
            self.util_overflow.append(("operator", op_util_raw))

        return {
            "orders_completed": len(active),
            "orders_total": len(self.orders),
            "avg_prep_time": float(prep_times.mean()),
            "median_prep_time": float(np.median(prep_times)),
            "p95_prep_time": float(np.percentile(prep_times, 95)),
            "avg_lead_time": float(leads.mean()),
            "p95_lead_time": float(np.percentile(leads, 95)),
            "avg_op_queue_wait": float(op_waits.mean()),
            "avg_wait_time": float(rt_waits.mean()),
            "total_wait_time": float(rt_waits.sum()),
            "avg_walk_distance": float(distances.mean()),
            "total_walk_distance": float(distances.sum()),
            "reach_truck_utilization": rt_util_raw,
            "operator_utilization": op_util_raw,
            "util_overflow": list(self.util_overflow),
        }

    def to_csv(self, filepath):
        with open(filepath, "w") as f:
            f.write("order_id,arrival_time,op_queue_wait,rt_queue_wait,"
                    "prep_time,lead_time,walk_distance,num_items,line,timestamp\n")
            for o in self.orders:
                line = o.line or ""
                f.write(f"{o.order_id},{o.arrival_time:.2f},"
                        f"{o.op_queue_wait:.2f},{o.rt_queue_wait:.2f},"
                        f"{o.prep_time:.2f},{o.lead_time:.2f},"
                        f"{o.walk_distance:.2f},{o.num_items},{line},"
                        f"{o.timestamp:.2f}\n")

    def picks_per_rack_csv(self, filepath):
        with open(filepath, "w") as f:
            f.write("rack_id,pick_count\n")
            for rack in sorted(self.picks_by_rack):
                f.write(f"{rack},{self.picks_by_rack[rack]}\n")

    def picks_per_material_csv(self, filepath):
        with open(filepath, "w") as f:
            f.write("material_id,pick_count\n")
            for mat in sorted(self.picks_by_material):
                f.write(f"{mat},{self.picks_by_material[mat]}\n")
