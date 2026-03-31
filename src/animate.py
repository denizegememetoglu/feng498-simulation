"""Warehouse simulation visualizer — produces an MP4 animation showing:
- Top-down warehouse layout (racks, aisles, kitting area)
- Operators moving between pick locations
- Reach truck busy/idle indicators
- Heatmap overlay of pick frequency per rack position
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import simpy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.animation as animation
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from collections import defaultdict

from src import config
from src.data_loader import load_all_data
from src.warehouse import Warehouse
from src.slotting import ALL_POLICIES


# ── Recording simulation ─────────────────────────────────────────────────────

class AnimationRecorder:
    """Runs a SimPy simulation and records every event for playback."""

    def __init__(self, warehouse, materials, rng):
        self.warehouse = warehouse
        self.materials = materials
        self.rng = rng

        # Build order generator helpers
        self.material_ids = [m["material_id"] for m in materials]
        consumptions = np.array([m["consumption"] for m in materials])
        self.weights = consumptions / consumptions.sum()
        self.inter_arrival = config.SHIFT_DURATION_MIN / config.ORDERS_PER_DAY

        # Event log: list of (time, event_type, data_dict)
        self.events = []
        self.pick_counts = defaultdict(int)  # position_id -> count
        self._order_counter = 0

    def run(self, duration=None):
        if duration is None:
            duration = config.SHIFT_DURATION_MIN  # 1 day for animation
        env = simpy.Environment()
        self.reach_trucks = simpy.Resource(env, capacity=config.NUM_REACH_TRUCKS)
        self.operators = simpy.Resource(env, capacity=config.NUM_OPERATORS)
        self.env = env
        env.process(self._generate_orders(duration))
        env.run(until=duration)

    def _generate_orders(self, duration):
        while self.env.now < duration:
            self._order_counter += 1
            n_items = self.rng.integers(config.ITEMS_PER_ORDER_MIN, config.ITEMS_PER_ORDER_MAX + 1)
            indices = self.rng.choice(len(self.material_ids), size=n_items, replace=True, p=self.weights)
            items = list(set(self.material_ids[i] for i in indices))
            self.env.process(self._process_order(self._order_counter, items))
            iat = self.rng.exponential(self.inter_arrival)
            yield self.env.timeout(iat)

    def _process_order(self, order_id, material_ids):
        op_id = None
        with self.operators.request() as op_req:
            yield op_req
            op_id = order_id % config.NUM_OPERATORS

            picks = []
            for mat_id in material_ids:
                locs = self.warehouse.material_locations.get(mat_id)
                if locs:
                    picks.append(locs[0])
            if not picks:
                return

            # Nearest-neighbor route
            remaining = list(picks)
            route = []
            cur = "kitting_area"
            while remaining:
                nearest = min(remaining, key=lambda p: self.warehouse.travel_distance(cur, p))
                route.append(nearest)
                remaining.remove(nearest)
                cur = nearest

            cur_pos = "kitting_area"
            for pos_id in route:
                pos = self.warehouse.positions[pos_id]
                # Walk
                cx, cy = self._get_xy(cur_pos)
                walk_dist = abs(cx - pos.x) + abs(cy - pos.y)
                walk_time = walk_dist / config.OPERATOR_WALK_SPEED_M_PER_MIN
                self.events.append((self.env.now, "op_move_start", {
                    "op": op_id, "from": (cx, cy), "to": (pos.x, pos.y),
                    "duration": walk_time}))
                yield self.env.timeout(walk_time)

                # Reach truck?
                if self.warehouse.needs_reach_truck(pos_id):
                    self.events.append((self.env.now, "rt_request", {"op": op_id, "pos": (pos.x, pos.y)}))
                    with self.reach_trucks.request() as rt_req:
                        yield rt_req
                        rt_time = self.warehouse.reach_truck_time(pos_id)
                        self.events.append((self.env.now, "rt_busy", {
                            "pos": (pos.x, pos.y), "duration": rt_time}))
                        yield self.env.timeout(rt_time)
                        self.events.append((self.env.now, "rt_done", {"pos": (pos.x, pos.y)}))

                # Pick
                self.events.append((self.env.now, "pick", {"op": op_id, "pos": (pos.x, pos.y)}))
                self.pick_counts[pos_id] += 1
                yield self.env.timeout(config.OPERATOR_PICK_TIME)
                cur_pos = pos_id

            # Return to kitting
            cx, cy = self._get_xy(cur_pos)
            ret_dist = abs(cx) + abs(cy)
            ret_time = ret_dist / config.OPERATOR_WALK_SPEED_M_PER_MIN
            self.events.append((self.env.now, "op_move_start", {
                "op": op_id, "from": (cx, cy), "to": (0.0, 0.0),
                "duration": ret_time}))
            yield self.env.timeout(ret_time)
            self.events.append((self.env.now, "op_idle", {"op": op_id}))

    def _get_xy(self, pos_ref):
        if pos_ref == "kitting_area":
            return 0.0, 0.0
        p = self.warehouse.positions[pos_ref]
        return p.x, p.y


# ── Rendering ─────────────────────────────────────────────────────────────────

def build_animation(recorder, warehouse, policy_name, output_path="output/simulation.mp4"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    events = recorder.events
    if not events:
        print("No events to animate.")
        return

    total_time = events[-1][0]
    fps = 30
    speed_factor = total_time / 60  # compress to ~60 seconds of video
    n_frames = fps * 60

    # ── Figure setup
    fig, (ax_main, ax_rt) = plt.subplots(
        1, 2, figsize=(18, 9), gridspec_kw={"width_ratios": [4, 1]})
    fig.suptitle(f"Warehouse Simulation — {policy_name}", fontsize=14, fontweight="bold")

    # ── Draw static warehouse layout with alternating aisles
    max_x = config.COMPARTMENTS_PER_MODULE * config.COMPARTMENT_WIDTH_M
    module_ys = []
    y_cursor = 0.0
    for m in range(config.NUM_MODULES):
        module_ys.append(y_cursor)
        y_cursor += config.RACK_DEPTH_M
        if m < config.NUM_MODULES - 1:
            if m % 2 == 0:
                y_cursor += config.AISLE_WIDTH_M
            else:
                y_cursor += config.KIT_CORRIDOR_WIDTH_M
    max_y = y_cursor

    # Draw racks and aisles
    for m in range(config.NUM_MODULES):
        y = module_ys[m]
        has_kit = warehouse.module_has_kit_corridor[m]
        color = "#f39c12" if has_kit else "#bdc3c7"
        rect = mpatches.FancyBboxPatch(
            (0, y), max_x, config.RACK_DEPTH_M,
            boxstyle="round,pad=0.05", facecolor=color, edgecolor="#7f8c8d", linewidth=0.8)
        ax_main.add_patch(rect)
        label = f"M{m}" + (" (kit)" if has_kit else "")
        ax_main.text(-1.5, y + config.RACK_DEPTH_M / 2, label, fontsize=7,
                     ha="right", va="center", color="#2c3e50")

    # Draw aisle labels between modules
    for m in range(config.NUM_MODULES - 1):
        y_top = module_ys[m] + config.RACK_DEPTH_M
        if m % 2 == 0:
            y_mid = y_top + config.AISLE_WIDTH_M / 2
            ax_main.text(max_x + 1, y_mid, "RT 3m", fontsize=6, color="#e74c3c",
                         ha="left", va="center")
        else:
            y_mid = y_top + config.KIT_CORRIDOR_WIDTH_M / 2
            ax_main.text(max_x + 1, y_mid, "Kit 1.6m", fontsize=6, color="#2980b9",
                         ha="left", va="center")

    # Kitting area
    kit_rect = mpatches.FancyBboxPatch(
        (-4, -3), 4, 3, boxstyle="round,pad=0.1",
        facecolor="#2ecc71", edgecolor="#27ae60", linewidth=1.5)
    ax_main.add_patch(kit_rect)
    ax_main.text(-2, -1.5, "KIT\nALANI", fontsize=8, ha="center", va="center",
                 fontweight="bold", color="white")

    ax_main.set_xlim(-6, max_x + 2)
    ax_main.set_ylim(-5, max_y + 2)
    ax_main.set_aspect("equal")
    ax_main.set_xlabel("X (m) — along rack")
    ax_main.set_ylabel("Y (m) — across aisles")

    # ── Heatmap: build a scatter of all positions colored by pick frequency
    all_x = [p.x for p in warehouse.positions.values()]
    all_y = [p.y for p in warehouse.positions.values()]
    pick_freq = [recorder.pick_counts.get(pid, 0) for pid in warehouse.positions]
    max_freq = max(pick_freq) if max(pick_freq) > 0 else 1
    norm = Normalize(0, max_freq)
    cmap = plt.cm.YlOrRd
    heat_scatter = ax_main.scatter(
        all_x, all_y, c=pick_freq, cmap=cmap, norm=norm,
        s=3, alpha=0.4, zorder=1)

    # Colorbar
    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax_main, shrink=0.5, pad=0.02)
    cbar.set_label("Pick frequency", fontsize=8)

    # ── Operator dots
    op_colors = plt.cm.Set1(np.linspace(0, 1, config.NUM_OPERATORS))
    op_dots = []
    for i in range(config.NUM_OPERATORS):
        dot, = ax_main.plot([], [], "o", color=op_colors[i], markersize=8,
                            zorder=10, markeredgecolor="black", markeredgewidth=0.5)
        op_dots.append(dot)

    # ── Reach truck panel
    ax_rt.set_xlim(0, 1)
    ax_rt.set_ylim(0, config.NUM_REACH_TRUCKS + 1)
    ax_rt.set_title("Reach Trucks", fontsize=10)
    ax_rt.set_xticks([])
    ax_rt.set_yticks(range(1, config.NUM_REACH_TRUCKS + 1))
    ax_rt.set_yticklabels([f"RT {i+1}" for i in range(config.NUM_REACH_TRUCKS)], fontsize=8)

    rt_bars = []
    for i in range(config.NUM_REACH_TRUCKS):
        bar = mpatches.FancyBboxPatch(
            (0.1, i + 0.7), 0.8, 0.5,
            boxstyle="round,pad=0.05", facecolor="#2ecc71", edgecolor="#333")
        ax_rt.add_patch(bar)
        rt_bars.append(bar)

    # Time display
    time_text = ax_main.text(
        0.02, 0.98, "", transform=ax_main.transAxes,
        fontsize=11, fontweight="bold", va="top",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    # ── Precompute operator positions at each frame time
    # Build per-operator movement timeline
    op_timelines = {i: [] for i in range(config.NUM_OPERATORS)}  # op_id -> [(t_start, t_end, from_xy, to_xy)]
    for t, etype, data in events:
        if etype == "op_move_start":
            op = data["op"]
            op_timelines[op].append((
                t, t + data["duration"],
                data["from"], data["to"]
            ))

    # RT busy periods
    rt_busy_periods = []  # [(t_start, t_end)]
    for t, etype, data in events:
        if etype == "rt_busy":
            rt_busy_periods.append((t, t + data["duration"]))

    def get_op_pos(op_id, t):
        for t_start, t_end, from_xy, to_xy in op_timelines[op_id]:
            if t_start <= t <= t_end:
                frac = (t - t_start) / (t_end - t_start) if t_end > t_start else 1.0
                x = from_xy[0] + frac * (to_xy[0] - from_xy[0])
                y = from_xy[1] + frac * (to_xy[1] - from_xy[1])
                return x, y
        return 0.0, 0.0  # at kitting area

    def count_rt_busy(t):
        return sum(1 for ts, te in rt_busy_periods if ts <= t <= te)

    def update(frame):
        t = (frame / n_frames) * total_time
        hours = int(t // 60)
        mins = int(t % 60)
        time_text.set_text(f"t = {hours:02d}:{mins:02d}  (Day sim)")

        # Update operator positions
        for op_id in range(config.NUM_OPERATORS):
            x, y = get_op_pos(op_id, t)
            op_dots[op_id].set_data([x], [y])

        # Update RT status
        n_busy = count_rt_busy(t)
        for i in range(config.NUM_REACH_TRUCKS):
            if i < n_busy:
                rt_bars[i].set_facecolor("#e74c3c")
            else:
                rt_bars[i].set_facecolor("#2ecc71")

        return op_dots + [time_text] + rt_bars

    print(f"  Rendering {n_frames} frames...")
    anim = animation.FuncAnimation(fig, update, frames=n_frames, interval=1000 / fps, blit=False)

    writer = animation.FFMpegWriter(fps=fps, bitrate=2000)
    anim.save(output_path, writer=writer)
    plt.close()
    print(f"  Saved: {output_path}")


# ── Static heatmap per policy ─────────────────────────────────────────────────

def plot_warehouse_heatmap(warehouse, recorder, policy_name, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_title(f"Pick Frequency Heatmap — {policy_name}", fontsize=13, fontweight="bold")

    # Draw racks with alternating aisles
    max_x = config.COMPARTMENTS_PER_MODULE * config.COMPARTMENT_WIDTH_M
    y_cursor = 0.0
    for m in range(config.NUM_MODULES):
        has_kit = warehouse.module_has_kit_corridor[m]
        color = "#fff3cd" if has_kit else "#f0f0f0"
        rect = mpatches.Rectangle(
            (0, y_cursor), max_x, config.RACK_DEPTH_M,
            facecolor=color, edgecolor="#999", linewidth=0.5)
        ax.add_patch(rect)
        label = f"M{m}" + (" *" if has_kit else "")
        ax.text(-1, y_cursor + config.RACK_DEPTH_M / 2, label, fontsize=7,
                ha="right", va="center")
        y_cursor += config.RACK_DEPTH_M
        if m < config.NUM_MODULES - 1:
            if m % 2 == 0:
                y_cursor += config.AISLE_WIDTH_M
            else:
                y_cursor += config.KIT_CORRIDOR_WIDTH_M

    # Scatter by pick count (aggregate across levels to show top-down view)
    # Group by (module, compartment) → sum pick counts across levels and slots
    from collections import defaultdict
    comp_picks = defaultdict(int)
    comp_xy = {}
    for pid, pos in warehouse.positions.items():
        key = (pos.module, pos.compartment)
        comp_picks[key] += recorder.pick_counts.get(pid, 0)
        comp_xy[key] = (pos.x, pos.y)

    xs = [comp_xy[k][0] for k in comp_picks]
    ys = [comp_xy[k][1] for k in comp_picks]
    counts = [comp_picks[k] for k in comp_picks]
    max_c = max(counts) if max(counts) > 0 else 1

    sc = ax.scatter(xs, ys, c=counts, cmap="YlOrRd", s=40,
                    norm=Normalize(0, max_c), edgecolors="#333", linewidths=0.3)
    fig.colorbar(sc, ax=ax, shrink=0.6, label="Pick count")

    # Kitting area
    kit = mpatches.Rectangle((-4, -3), 4, 3, facecolor="#2ecc71", edgecolor="#27ae60")
    ax.add_patch(kit)
    ax.text(-2, -1.5, "KIT", fontsize=9, ha="center", va="center",
            fontweight="bold", color="white")

    ax.set_xlim(-6, max_x + 2)
    ax.set_ylim(-5, y_cursor + 2)
    ax.set_aspect("equal")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  Saved: {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading data...")
    data = load_all_data()
    materials = data["abc_analizi"]
    print(f"  {len(materials)} materials loaded")

    # Pick which policy to animate (default: Usage-based ABC)
    policy_name = sys.argv[1] if len(sys.argv) > 1 else "Usage-based ABC"
    if policy_name not in ALL_POLICIES:
        print(f"Unknown policy. Available: {list(ALL_POLICIES.keys())}")
        return

    print(f"\nPolicy: {policy_name}")
    warehouse = Warehouse()
    policy = ALL_POLICIES[policy_name]()
    policy.assign(materials, warehouse)

    assigned = sum(1 for p in warehouse.positions.values() if p.material_id is not None)
    print(f"  {assigned} positions assigned")

    print("\nRunning simulation (1 day)...")
    rng = np.random.default_rng(config.RANDOM_SEED)
    recorder = AnimationRecorder(warehouse, materials, rng)
    recorder.run(duration=config.SHIFT_DURATION_MIN)
    print(f"  {len(recorder.events)} events recorded")

    # Static heatmap
    safe = policy_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
    plot_warehouse_heatmap(warehouse, recorder, policy_name, f"output/heatmap_{safe}.png")

    # Animation
    print("\nBuilding animation...")
    try:
        build_animation(recorder, warehouse, policy_name, f"output/simulation_{safe}.mp4")
    except Exception as e:
        print(f"  Animation failed (ffmpeg needed): {e}")
        print("  Heatmap was still saved successfully.")


if __name__ == "__main__":
    main()
