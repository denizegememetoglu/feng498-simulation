from dataclasses import dataclass, field
import statistics


@dataclass
class OrderRecord:
    order_id: int
    prep_time: float
    wait_time: float
    walk_distance: float
    num_items: int
    timestamp: float


class KPICollector:
    def __init__(self):
        self.orders: list[OrderRecord] = []
        self.milkrun_departures: list[float] = []
        self._rt_busy_time = 0.0
        self._op_busy_time = 0.0
        self._sim_duration = 0.0

    def record_order(self, order_id, prep_time, wait_time, walk_distance, num_items, timestamp):
        self.orders.append(OrderRecord(
            order_id=order_id,
            prep_time=prep_time,
            wait_time=wait_time,
            walk_distance=walk_distance,
            num_items=num_items,
            timestamp=timestamp,
        ))

    def record_milkrun_departure(self, time):
        self.milkrun_departures.append(time)

    def add_rt_busy(self, duration):
        self._rt_busy_time += duration

    def add_op_busy(self, duration):
        self._op_busy_time += duration

    def set_sim_duration(self, duration):
        self._sim_duration = duration

    def summary(self, num_reach_trucks=7, num_operators=4):
        if not self.orders:
            return {"orders_completed": 0}

        prep_times = [o.prep_time for o in self.orders]
        wait_times = [o.wait_time for o in self.orders]
        distances = [o.walk_distance for o in self.orders]

        total_rt_capacity = num_reach_trucks * self._sim_duration if self._sim_duration > 0 else 1
        total_op_capacity = num_operators * self._sim_duration if self._sim_duration > 0 else 1

        return {
            "orders_completed": len(self.orders),
            "avg_prep_time": statistics.mean(prep_times),
            "median_prep_time": statistics.median(prep_times),
            "p95_prep_time": sorted(prep_times)[int(len(prep_times) * 0.95)],
            "avg_wait_time": statistics.mean(wait_times),
            "total_wait_time": sum(wait_times),
            "avg_walk_distance": statistics.mean(distances),
            "total_walk_distance": sum(distances),
            "reach_truck_utilization": min(self._rt_busy_time / total_rt_capacity, 1.0),
            "operator_utilization": min(self._op_busy_time / total_op_capacity, 1.0),
        }

    def to_csv(self, filepath):
        with open(filepath, "w") as f:
            f.write("order_id,prep_time,wait_time,walk_distance,num_items,timestamp\n")
            for o in self.orders:
                f.write(f"{o.order_id},{o.prep_time:.2f},{o.wait_time:.2f},"
                        f"{o.walk_distance:.2f},{o.num_items},{o.timestamp:.2f}\n")
