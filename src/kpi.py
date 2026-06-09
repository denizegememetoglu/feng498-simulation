from collections import Counter
from dataclasses import dataclass, field
import statistics

import numpy as np

from src import config


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
        self._kardex_busy_time = 0.0
        self._sim_duration = 0.0
        self._warmup = 0.0
        self._cooldown = 0.0
        # Arrivals counted at generation time. orders_started - orders_total
        # = orders still in flight when the run was cut off at `duration`
        # (survivorship telemetry — those orders never reach record_order).
        self.orders_started = 0
        # Validation telemetry: pick counts by rack and by material across the
        # whole run (irrespective of warmup window — full data is what we need
        # for chi-square vs. SAP). Use `_active_orders` for windowed averages.
        self.picks_by_rack: Counter = Counter()
        self.picks_by_material: Counter = Counter()
        # Surface util overflow rather than silently capping it.
        self.util_overflow: list[tuple[str, float]] = []
        # Orders whose entire item list resolved to neither rack nor Kardex
        # picks (no decoded SAP slot and no Kardex membership). Recorded as
        # orders to keep totals comparable, but flagged separately.
        self.orders_with_no_locations = 0

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

    def add_kardex_busy(self, duration):
        self._kardex_busy_time += duration

    def set_sim_duration(self, duration, warmup=0.0, cooldown=0.0):
        self._sim_duration = duration
        self._warmup = warmup
        self._cooldown = cooldown

    def _active_orders(self):
        """Orders whose arrival fell inside the [warmup, duration-cooldown] window."""
        lo = self._warmup
        hi = self._sim_duration - self._cooldown
        return [o for o in self.orders if lo <= o.arrival_time < hi]

    def summary(self, num_reach_trucks: int | None = None,
                num_operators: int | None = None):
        if num_reach_trucks is None:
            num_reach_trucks = config.NUM_REACH_TRUCKS
        if num_operators is None:
            num_operators = config.NUM_OPERATORS
        active = self._active_orders()
        if not active:
            return {"orders_completed": 0}

        prep_times = np.array([o.prep_time for o in active])
        rt_waits = np.array([o.rt_queue_wait for o in active])
        op_waits = np.array([o.op_queue_wait for o in active])
        leads = np.array([o.lead_time for o in active])
        distances = np.array([o.walk_distance for o in active])

        # Utilization compares cumulative busy time to cumulative resource
        # capacity across the entire simulation. Both numerator and
        # denominator span the FULL run (incl. warmup/cooldown, 2.5% of the
        # window) while the order KPIs use the active window only — a known,
        # documented mismatch kept because splitting busy spans across the
        # window edges adds complexity for a <2.5% effect (ASSUMPTIONS §24).
        total_window = max(self._sim_duration, 1.0)
        rt_capacity = num_reach_trucks * total_window
        op_capacity = num_operators * total_window
        kdx_capacity = config.NUM_KARDEX_UNITS * total_window
        rt_util_raw = self._rt_busy_time / rt_capacity if rt_capacity > 0 else 0.0
        op_util_raw = self._op_busy_time / op_capacity if op_capacity > 0 else 0.0
        kdx_util_raw = (self._kardex_busy_time / kdx_capacity
                        if kdx_capacity > 0 else 0.0)
        # Compute overflow flags locally — summary() must stay idempotent
        # (the recorder calls it periodically; the old append-to-self list
        # double-counted overflows on every call).
        overflow = []
        if rt_util_raw > 1.0:
            overflow.append(("reach_truck", rt_util_raw))
        if op_util_raw > 1.0:
            overflow.append(("operator", op_util_raw))
        self.util_overflow = overflow

        # Throughput over the active KPI window. One sim day == one 480-min
        # shift, so orders/day is the per-shift throughput the advisor asked
        # for; orders/hr is the rate form for Minitab.
        active_window_min = max(total_window - self._warmup - self._cooldown, 1.0)
        throughput_per_hr = len(active) / (active_window_min / 60.0)

        total_waits = op_waits + rt_waits

        return {
            "orders_started": int(self.orders_started),
            "orders_completed": len(active),
            "orders_total": len(self.orders),
            "orders_with_no_locations": int(self.orders_with_no_locations),
            "throughput_orders_per_hr": float(throughput_per_hr),
            "throughput_orders_per_day": float(
                throughput_per_hr * config.SHIFT_DURATION_MIN / 60.0),
            "avg_prep_time": float(prep_times.mean()),
            "median_prep_time": float(np.median(prep_times)),
            "p95_prep_time": float(np.percentile(prep_times, 95)),
            "avg_lead_time": float(leads.mean()),
            "p95_lead_time": float(np.percentile(leads, 95)),
            "avg_op_queue_wait": float(op_waits.mean()),
            # avg_wait_time kept as the RT-queue wait for backward compat;
            # avg_rt_queue_wait is the explicit name, avg_total_wait is the
            # advisor's "waiting time" KPI (all queueing per order).
            "avg_wait_time": float(rt_waits.mean()),
            "avg_rt_queue_wait": float(rt_waits.mean()),
            "avg_total_wait": float(total_waits.mean()),
            "p95_total_wait": float(np.percentile(total_waits, 95)),
            "total_wait_time": float(rt_waits.sum()),
            "avg_walk_distance": float(distances.mean()),
            "total_walk_distance": float(distances.sum()),
            "reach_truck_utilization": rt_util_raw,
            "operator_utilization": op_util_raw,
            "kardex_utilization": kdx_util_raw,
            "util_overflow": list(overflow),
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
