from dataclasses import dataclass
from src import config


@dataclass
class PalletPosition:
    position_id: str
    module: int
    level: int
    compartment: int
    slot: int
    x: float          # meters along rack length
    y: float          # meters perpendicular to racks (center of rack)
    has_kit_corridor: bool  # has kit corridor on at least one side
    material_id: str | None = None


class Warehouse:
    """
    Layout: alternating aisle types between modules.

    Gap between M(i) and M(i+1):
      - even i -> 3m reach truck aisle
      - odd i  -> 1.6m kit corridor (operator only)

    So each module except M0 and M10 has one RT aisle side and one kit corridor side.
    M0 has RT aisle on right (between M0-M1), wall on left.
    M10 has kit corridor on left (between M9-M10), wall on right.

    Operator can pick directly (no RT) if:
      - The position's module has a kit corridor on at least one side
      - AND level < FAST_MOVER_MAX_LEVEL (reachable by hand)

    Reach truck access for upper levels always comes from the 3m aisle side.
    """

    def __init__(self):
        self.positions: dict[str, PalletPosition] = {}
        self.material_locations: dict[str, list[str]] = {}
        self.module_y_centers: list[float] = []  # y-center of each module
        self.module_has_kit_corridor: list[bool] = []
        self.kitting_x = 0.0
        self.kitting_y = 0.0
        self._build_layout()

    def _build_layout(self):
        """Build positions with alternating aisle pattern."""
        y_cursor = 0.0

        for m in range(config.NUM_MODULES):
            # Does this module border a kit corridor?
            # Kit corridors are at odd-indexed gaps: between M1-M2, M3-M4, M5-M6, M7-M8, M9-M10
            # Module m borders a kit corridor if:
            #   - gap (m-1) is odd (kit corridor on left) -> m-1 odd -> m is even and m>=2
            #   - gap (m) is odd (kit corridor on right) -> m is odd
            has_kit = False
            if m > 0 and (m - 1) % 2 == 1:  # kit corridor on left side
                has_kit = True
            if m < config.NUM_MODULES - 1 and m % 2 == 1:  # kit corridor on right side
                has_kit = True
            self.module_has_kit_corridor.append(has_kit)

            y_center = y_cursor + config.RACK_DEPTH_M / 2
            self.module_y_centers.append(y_center)

            for c in range(config.COMPARTMENTS_PER_MODULE):
                x = c * config.COMPARTMENT_WIDTH_M + config.COMPARTMENT_WIDTH_M / 2
                for lv in range(config.LEVELS_PER_MODULE):
                    for s in range(config.PALLETS_PER_COMPARTMENT):
                        pid = f"M{m:02d}-L{lv}-C{c:02d}-S{s}"
                        self.positions[pid] = PalletPosition(
                            position_id=pid,
                            module=m,
                            level=lv,
                            compartment=c,
                            slot=s,
                            x=x,
                            y=y_center,
                            has_kit_corridor=has_kit,
                        )

            # Add gap after this module
            y_cursor += config.RACK_DEPTH_M
            if m < config.NUM_MODULES - 1:
                if m % 2 == 0:
                    y_cursor += config.AISLE_WIDTH_M      # RT aisle
                else:
                    y_cursor += config.KIT_CORRIDOR_WIDTH_M  # kit corridor

    def travel_distance(self, pos_a, pos_b):
        """Manhattan distance between two positions or kitting area."""
        ax, ay = self._get_coords(pos_a)
        bx, by = self._get_coords(pos_b)
        return abs(ax - bx) + abs(ay - by)

    def distance_to_kitting(self, position_id):
        pos = self.positions[position_id]
        return abs(pos.x - self.kitting_x) + abs(pos.y - self.kitting_y)

    def can_pick_directly(self, position_id):
        """Operator can pick without reach truck if module has kit corridor AND low level."""
        pos = self.positions[position_id]
        return pos.has_kit_corridor and pos.level < config.FAST_MOVER_MAX_LEVEL

    def needs_reach_truck(self, position_id):
        """Reach truck needed if no kit corridor access OR high level."""
        return not self.can_pick_directly(position_id)

    def reach_truck_time(self, position_id):
        pos = self.positions[position_id]
        lift_time = pos.level * config.REACH_TRUCK_LIFT_TIME_PER_LEVEL
        return lift_time + config.REACH_TRUCK_PICK_PLACE_TIME

    def assign_material(self, material_id, position_id):
        pos = self.positions[position_id]
        pos.material_id = material_id
        if material_id not in self.material_locations:
            self.material_locations[material_id] = []
        self.material_locations[material_id].append(position_id)

    def clear_assignments(self):
        for pos in self.positions.values():
            pos.material_id = None
        self.material_locations.clear()

    def get_available_positions(self):
        """All empty positions sorted by distance to kitting."""
        available = [p for p in self.positions.values() if p.material_id is None]
        available.sort(key=lambda p: abs(p.x - self.kitting_x) + abs(p.y - self.kitting_y))
        return [p.position_id for p in available]

    def get_fast_mover_positions(self):
        """Positions where operator can pick directly: kit corridor + low level."""
        available = [
            p for p in self.positions.values()
            if p.material_id is None and p.has_kit_corridor and p.level < config.FAST_MOVER_MAX_LEVEL
        ]
        available.sort(key=lambda p: (p.level, abs(p.x - self.kitting_x) + abs(p.y - self.kitting_y)))
        return [p.position_id for p in available]

    def get_mid_level_positions(self):
        """Mid-level positions (3-5), any module."""
        available = [
            p for p in self.positions.values()
            if p.material_id is None and 3 <= p.level <= 5
        ]
        available.sort(key=lambda p: (p.level, abs(p.x - self.kitting_x) + abs(p.y - self.kitting_y)))
        return [p.position_id for p in available]

    def get_upper_level_positions(self):
        """Upper positions (6+), any module."""
        available = [
            p for p in self.positions.values()
            if p.material_id is None and p.level >= 6
        ]
        available.sort(key=lambda p: (p.level, abs(p.x - self.kitting_x) + abs(p.y - self.kitting_y)))
        return [p.position_id for p in available]

    def get_aisle_type_between(self, module_a, module_b):
        """Return 'rt' or 'kit' for the aisle between two adjacent modules."""
        gap_idx = min(module_a, module_b)
        return "rt" if gap_idx % 2 == 0 else "kit"

    def _get_coords(self, pos_ref):
        if pos_ref == "kitting_area":
            return self.kitting_x, self.kitting_y
        pos = self.positions[pos_ref]
        return pos.x, pos.y
