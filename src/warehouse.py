import json
import os
from dataclasses import dataclass

from src import config


@dataclass
class PalletPosition:
    position_id: str   # SAP-style "<RACK>-<bay:02d>-<pos:02d>", e.g. "A-02-02"
    rack_id: str       # "A", "B", ..., "J", "U"
    segment_index: int # 0 for linear racks; 0..N-1 for polylines
    bay_code: int      # bay number from PDF (A2..A12 -> 2..12; B1..B12 -> 1..12)
    level: int         # 0-based, 0 = floor
    position: int      # 1-based position within bay (matches SAP convention)
    x: float
    y: float
    has_kit_corridor: bool
    material_id: str | None = None


def _load_layout(path: str) -> dict:
    if not os.path.isabs(path):
        # Resolve relative to project root (parent of src/)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, path)
    with open(path, "r") as f:
        return json.load(f)


def _segment_has_kit_access(segment: dict) -> bool:
    """True if the segment has a kit corridor on either side, or
    kit_corridor_side is TBD and config allows the optimistic assumption."""
    side = segment.get("kit_corridor_side")
    if side in ("east", "west", "north", "south"):
        return True
    if side == "TBD" and config.ASSUME_KIT_ACCESS_WHEN_TBD:
        return True
    return False


def _bay_center(segment: dict, bay_index: int) -> tuple[float, float]:
    """Return (x, y) for the center of bay `bay_index` (0-based) within
    the segment. Linear interpolation along start->end."""
    sx, sy = segment["start"]
    ex, ey = segment["end"]
    n = segment["bays"]
    # Position the bay center at (i + 0.5) / n along the segment
    t = (bay_index + 0.5) / n
    return sx + (ex - sx) * t, sy + (ey - sy) * t


class Warehouse:
    """Loads the irregular partner-facility layout from config/layout.json.

    Each rack's segments come from data/rack-drawings/<rack>.pdf:
    bay count, bay codes, level count, and pallet count are PDF-verified.
    Kit-corridor / RT-aisle sides are TBD until the May 20 site visit;
    config.ASSUME_KIT_ACCESS_WHEN_TBD controls the placeholder behaviour.
    """

    def __init__(self, layout_path: str = None):
        self.positions: dict[str, PalletPosition] = {}
        self.material_locations: dict[str, list[str]] = {}
        self.layout = _load_layout(layout_path or config.LAYOUT_FILE)
        self.kitting_x = self.layout["kitting"]["x"] + self.layout["kitting"]["width_m"] / 2
        self.kitting_y = self.layout["kitting"]["y"] + self.layout["kitting"]["depth_m"] / 2
        self._build_layout()

    def _build_layout(self):
        for rack in self.layout["racks"]:
            rack_id = rack["id"]
            for seg_i, segment in enumerate(rack["segments"]):
                has_kit = _segment_has_kit_access(segment)
                levels = segment["levels"]
                pallets_per_bay = segment["pallets_per_bay"]
                bay_count = segment["bays"]
                bay_start = segment["bay_code_start"]
                expected = segment["pallet_count"]
                # We materialise bay_count * levels * pallets_per_bay positions;
                # this overcounts vs `pallet_count` (which excludes ÖN/ARKA passage
                # cutouts). Track expected separately for fidelity reporting.
                for b in range(bay_count):
                    bx, by = _bay_center(segment, b)
                    bay_code = bay_start + b
                    for lv in range(levels):
                        for p in range(1, pallets_per_bay + 1):
                            pid = f"{rack_id}-{bay_code:02d}-{p:02d}-L{lv}"
                            self.positions[pid] = PalletPosition(
                                position_id=pid,
                                rack_id=rack_id,
                                segment_index=seg_i,
                                bay_code=bay_code,
                                level=lv,
                                position=p,
                                x=bx,
                                y=by,
                                has_kit_corridor=has_kit,
                            )

    @property
    def pallet_capacity_from_pdf(self) -> int:
        return sum(s["pallet_count"] for r in self.layout["racks"] for s in r["segments"])

    def sap_position_id(self, rack_id: str, bay_code: int, position: int) -> str | None:
        """Return the position_id for the SAP-format coordinate at level 0
        (the SAP storage bin doesn't encode a level). Level 0 chosen so that
        the RealBaselinePolicy places materials at the bottom by default —
        per Sümeyra (May 4) the lower 3 levels are operator-reachable."""
        pid = f"{rack_id}-{bay_code:02d}-{position:02d}-L0"
        return pid if pid in self.positions else None

    def travel_distance(self, pos_a, pos_b):
        ax, ay = self._get_coords(pos_a)
        bx, by = self._get_coords(pos_b)
        return abs(ax - bx) + abs(ay - by)

    def distance_to_kitting(self, position_id):
        pos = self.positions[position_id]
        return abs(pos.x - self.kitting_x) + abs(pos.y - self.kitting_y)

    def can_pick_directly(self, position_id):
        pos = self.positions[position_id]
        return pos.has_kit_corridor and pos.level < config.FAST_MOVER_MAX_LEVEL

    def needs_reach_truck(self, position_id):
        return not self.can_pick_directly(position_id)

    def reach_truck_time(self, position_id):
        pos = self.positions[position_id]
        lift_time = pos.level * config.REACH_TRUCK_LIFT_TIME_PER_LEVEL
        return lift_time + config.REACH_TRUCK_PICK_PLACE_TIME

    def assign_material(self, material_id, position_id):
        pos = self.positions[position_id]
        pos.material_id = material_id
        self.material_locations.setdefault(material_id, []).append(position_id)

    def clear_assignments(self):
        for pos in self.positions.values():
            pos.material_id = None
        self.material_locations.clear()

    def _key_dist(self, pos: PalletPosition) -> float:
        return abs(pos.x - self.kitting_x) + abs(pos.y - self.kitting_y)

    def get_available_positions(self):
        avail = [p for p in self.positions.values() if p.material_id is None]
        avail.sort(key=self._key_dist)
        return [p.position_id for p in avail]

    def get_fast_mover_positions(self):
        avail = [
            p for p in self.positions.values()
            if p.material_id is None
            and p.has_kit_corridor
            and p.level < config.FAST_MOVER_MAX_LEVEL
        ]
        avail.sort(key=lambda p: (p.level, self._key_dist(p)))
        return [p.position_id for p in avail]

    def get_mid_level_positions(self):
        """Mid band: roughly the middle third of each rack's level range,
        capped at level 5 to match the original behaviour."""
        avail = []
        for p in self.positions.values():
            if p.material_id is not None:
                continue
            max_lv = self._max_level_for_rack(p.rack_id)
            mid_lo = max(config.FAST_MOVER_MAX_LEVEL, 1)
            mid_hi = min(max_lv - 2, 5)
            if mid_lo <= p.level <= mid_hi:
                avail.append(p)
        avail.sort(key=lambda p: (p.level, self._key_dist(p)))
        return [p.position_id for p in avail]

    def get_upper_level_positions(self):
        avail = []
        for p in self.positions.values():
            if p.material_id is not None:
                continue
            max_lv = self._max_level_for_rack(p.rack_id)
            upper_lo = max(6, max_lv - 1)
            if p.level >= upper_lo:
                avail.append(p)
        avail.sort(key=lambda p: (p.level, self._key_dist(p)))
        return [p.position_id for p in avail]

    def _max_level_for_rack(self, rack_id: str) -> int:
        for r in self.layout["racks"]:
            if r["id"] == rack_id:
                return max(s["levels"] for s in r["segments"])
        return 0

    def _get_coords(self, pos_ref):
        if pos_ref == "kitting_area":
            return self.kitting_x, self.kitting_y
        pos = self.positions[pos_ref]
        return pos.x, pos.y
