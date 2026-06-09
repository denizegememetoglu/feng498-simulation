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


@dataclass(frozen=True)
class RectObstacle:
    obstacle_id: str
    kind: str
    x0: float
    y0: float
    x1: float
    y1: float

    def as_dict(self) -> dict:
        return {
            "id": self.obstacle_id,
            "kind": self.kind,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
        }


@dataclass(frozen=True)
class RouteResult:
    distance: float
    path: tuple[tuple[float, float], ...]
    intersections: tuple[str, ...] = ()


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


def _expand_bay_overrides(overrides: list) -> dict[int, dict]:
    """Expand a list of `{bays: [...], pallets_per_bay: int, position_offset?: int}`
    entries into a flat {bay_code -> override_dict} mapping."""
    out: dict[int, dict] = {}
    for entry in overrides:
        bays = entry.get("bays", [])
        record = {k: v for k, v in entry.items() if k != "bays"}
        for bay in bays:
            out[bay] = record
    return out


def _bay_center(segment: dict, bay_index: int) -> tuple[float, float]:
    """Return (x, y) for the center of bay `bay_index` (0-based) within
    the segment. Linear interpolation along start->end."""
    sx, sy = segment["start"]
    ex, ey = segment["end"]
    n = segment["bays"]
    # Position the bay center at (i + 0.5) / n along the segment
    t = (bay_index + 0.5) / n
    return sx + (ex - sx) * t, sy + (ey - sy) * t


def _is_valid_side(side: str | None) -> bool:
    return side in ("east", "west", "north", "south")


def _segment_axis(segment: dict) -> str:
    sx, sy = segment["start"]
    ex, ey = segment["end"]
    return "x" if abs(ex - sx) >= abs(ey - sy) else "y"


class Warehouse:
    """Loads the irregular partner-facility layout from config/layout.json.

    Each rack's segments come from data/rack-drawings/<rack>.pdf:
    bay count, bay codes, level count, and pallet count are PDF-verified.
    Kit-corridor / RT-aisle sides are TBD until the May 20 site visit;
    config.ASSUME_KIT_ACCESS_WHEN_TBD controls the placeholder behaviour.
    """

    # Class-level cache pool, keyed by routing-geometry fingerprint.
    # See __init__ — instances with identical geometry share route caches.
    _SHARED_ROUTE_CACHES: dict[tuple, tuple[dict, dict, dict]] = {}

    def __init__(self, layout_path: str = None):
        self.positions: dict[str, PalletPosition] = {}
        self.material_locations: dict[str, list[str]] = {}
        self.layout = _load_layout(layout_path or config.LAYOUT_FILE)
        self.kitting_x = self.layout["kitting"]["x"] + self.layout["kitting"]["width_m"] / 2
        self.kitting_y = self.layout["kitting"]["y"] + self.layout["kitting"]["depth_m"] / 2
        self._segments_by_key: dict[tuple[str, int], dict] = {}
        self.route_obstacles: list[RectObstacle] = []
        self.visual_obstacles: list[RectObstacle] = []
        self.non_blocking_storage: list[RectObstacle] = []
        self._safe_x_lines: list[float] = []
        self._safe_y_lines: list[float] = []
        self._build_layout()
        self._build_route_model()
        # Route caches are SHARED across Warehouse instances with identical
        # routing geometry (2026-06-09 perf fix). main.py builds a fresh
        # Warehouse per replication; per-instance caches re-warmed from zero
        # on every rep, dominating the multi-rep runtime. Routing depends
        # only on (obstacles, safe lines, clearance), so instances with the
        # same geometry key can reuse one cache safely.
        geom_key = (
            tuple((o.x0, o.y0, o.x1, o.y1) for o in self.route_obstacles),
            tuple(self._safe_x_lines),
            tuple(self._safe_y_lines),
            float(getattr(config, "ROUTE_CLEARANCE_M", 0.6)),
            bool(getattr(config, "ASSUME_KIT_ACCESS_WHEN_TBD", False)),
            # Access-point selection reads corridor sides, which are not
            # visible in the obstacle set — include them in the key.
            tuple(sorted(
                (r["id"], i, s.get("kit_corridor_side", ""), s.get("rt_aisle_side", ""))
                for r in self.layout["racks"]
                for i, s in enumerate(r["segments"])
            )),
        )
        shared = Warehouse._SHARED_ROUTE_CACHES.setdefault(
            geom_key, ({}, {}, {}))
        self._route_cache, self._access_point_cache, \
            self._route_to_position_cache = shared

    def _build_layout(self):
        for rack in self.layout["racks"]:
            rack_id = rack["id"]
            for seg_i, segment in enumerate(rack["segments"]):
                has_kit = _segment_has_kit_access(segment)
                levels = segment["levels"]
                default_width = segment["pallets_per_bay"]
                default_offset = segment.get("position_offset", 0)
                bay_count = segment["bays"]
                bay_start = segment["bay_code_start"]
                overrides = _expand_bay_overrides(segment.get("bay_overrides", []))
                self._segments_by_key[(rack_id, seg_i)] = segment
                for b in range(bay_count):
                    bx, by = _bay_center(segment, b)
                    bay_code = bay_start + b
                    ovr = overrides.get(bay_code, {})
                    width = ovr.get("pallets_per_bay", default_width)
                    offset = ovr.get("position_offset", default_offset)
                    if width <= 0:
                        continue  # bay reserved (e.g. J12 cart) — no pallet positions
                    for lv in range(levels):
                        for p in range(1 + offset, 1 + offset + width):
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
        """Sum of `pallet_count` stamps from each rack PDF — informational only.
        Note this differs from len(positions): PDF stamps count physical pallet
        slots after ÖN/ARKA passage cutouts; positions are derived from per-bay
        widths in layout.json which model material-size-based feeder bays from
        the May 11 site data."""
        return sum(s.get("pallet_count", 0) for r in self.layout["racks"] for s in r["segments"])

    def sap_position_id(self, rack_id: str, bay_code: int, position: int) -> str | None:
        """Return the position_id for the SAP-format coordinate at level 0
        (the SAP storage bin doesn't encode a level). Level 0 chosen so that
        the RealBaselinePolicy places materials at the bottom by default —
        per site report (May 4) the lower 3 levels are operator-reachable."""
        pid = f"{rack_id}-{bay_code:02d}-{position:02d}-L0"
        return pid if pid in self.positions else None

    def sap_position_ids(self, rack_id: str, bay_code: int, position: int) -> list[str]:
        """Return all modeled levels for a SAP rack/bay/position coordinate.

        SAP storage-bin strings encode rack, bay, and horizontal position but
        not rack level. For actual-placement replay, keep rack/bay/position
        exact and assign duplicate materials to the first free level instead
        of incorrectly falling back after level 0 is occupied.
        """
        prefix = f"{rack_id}-{bay_code:02d}-{position:02d}-L"
        ids = [pid for pid in self.positions if pid.startswith(prefix)]
        ids.sort(key=lambda pid: self.positions[pid].level)
        return ids

    def travel_distance(self, pos_a, pos_b):
        ax, ay = self._get_coords(pos_a)
        bx, by = self._get_coords(pos_b)
        return self.route_between_points((ax, ay), (bx, by)).distance

    def distance_to_kitting(self, position_id):
        return self.route_to_position((self.kitting_x, self.kitting_y), position_id).distance

    def can_pick_directly(self, position_id):
        pos = self.positions[position_id]
        return pos.has_kit_corridor and pos.level < config.FAST_MOVER_MAX_LEVEL

    def can_pick_manually(self, position_id):
        """Operator can walk into the RT aisle at low levels without an RT —
        slower than a kit-corridor pick but doesn't queue for a truck."""
        pos = self.positions[position_id]
        return (not pos.has_kit_corridor) and pos.level <= config.MANUAL_PICK_MAX_LEVEL

    def needs_reach_truck(self, position_id):
        if self.can_pick_directly(position_id):
            return False
        if self.can_pick_manually(position_id):
            return False
        return True

    def reach_truck_time(self, position_id):
        pos = self.positions[position_id]
        lift_time = pos.level * config.REACH_TRUCK_LIFT_TIME_PER_LEVEL
        return lift_time + config.REACH_TRUCK_PICK_PLACE_TIME

    def reach_truck_travel_time(self, position_id):
        """Time for an RT to come from the depot to the aisle-side pick point."""
        route = self.route_to_position(
            (config.REACH_TRUCK_DEPOT_X, config.REACH_TRUCK_DEPOT_Y),
            position_id,
            mode="reach_truck",
        )
        dist = route.distance
        return dist / config.REACH_TRUCK_SPEED_M_PER_MIN

    def manual_pick_time(self, position_id):
        return config.OPERATOR_PICK_TIME + config.MANUAL_PICK_TIME_PENALTY

    def assign_material(self, material_id, position_id):
        pos = self.positions[position_id]
        pos.material_id = material_id
        self.material_locations.setdefault(material_id, []).append(position_id)

    def clear_assignments(self):
        for pos in self.positions.values():
            pos.material_id = None
        self.material_locations.clear()

    def _key_dist(self, pos: PalletPosition) -> float:
        return self.route_to_position((self.kitting_x, self.kitting_y), pos.position_id).distance

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

    def _level_bands(self, max_lv: int) -> tuple[int, int]:
        """Return (mid_hi_inclusive, upper_lo_inclusive) for a rack with
        `max_lv` levels. Levels are partitioned into 3 contiguous bands
        with no gap: [0, FAST_MOVER_MAX_LEVEL), [fm_max, mid_hi], [mid_hi+1, max_lv-1].
        Earlier versions left levels 6-7 of a 9-level rack in neither pool;
        this guarantees full coverage."""
        fm_max = config.FAST_MOVER_MAX_LEVEL  # exclusive
        remaining = max_lv - fm_max
        if remaining <= 0:
            return (fm_max - 1, fm_max)  # degenerate; no mid/upper
        # Half of the remaining levels go to mid, the rest to upper.
        mid_count = max(1, remaining // 2)
        mid_hi = fm_max + mid_count - 1
        upper_lo = mid_hi + 1
        return mid_hi, upper_lo

    def get_mid_level_positions(self):
        """Mid band: levels [FAST_MOVER_MAX_LEVEL, mid_hi] per rack height."""
        avail = []
        for p in self.positions.values():
            if p.material_id is not None:
                continue
            max_lv = self._max_level_for_rack(p.rack_id)
            mid_hi, _ = self._level_bands(max_lv)
            if config.FAST_MOVER_MAX_LEVEL <= p.level <= mid_hi:
                avail.append(p)
        avail.sort(key=lambda p: (p.level, self._key_dist(p)))
        return [p.position_id for p in avail]

    def get_upper_level_positions(self):
        avail = []
        for p in self.positions.values():
            if p.material_id is not None:
                continue
            max_lv = self._max_level_for_rack(p.rack_id)
            _, upper_lo = self._level_bands(max_lv)
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

    # ------------------------------------------------------------------
    # Conservative routing model

    def _build_route_model(self) -> None:
        depth = float(self.layout.get("rack_depth_m", 1.3))
        for rack in self.layout["racks"]:
            rack_id = rack["id"]
            for seg_i, segment in enumerate(rack["segments"]):
                sx, sy = segment["start"]
                ex, ey = segment["end"]
                if _segment_axis(segment) == "y":
                    x0 = sx - depth / 2
                    x1 = sx + depth / 2
                    y0, y1 = sorted((sy, ey))
                else:
                    x0, x1 = sorted((sx, ex))
                    y0 = sy - depth / 2
                    y1 = sy + depth / 2
                obstacle = RectObstacle(f"rack:{rack_id}:{seg_i}", "rack", x0, y0, x1, y1)
                if self._segment_is_routing_obstacle(rack_id, seg_i):
                    self.route_obstacles.append(obstacle)
                else:
                    self.non_blocking_storage.append(obstacle)

        for zone in self.layout.get("blocked_zones", []):
            x = float(zone["x"])
            y = float(zone["y"])
            self.route_obstacles.append(
                RectObstacle(
                    f"blocked:{zone.get('id', len(self.route_obstacles))}",
                    "blocked_zone",
                    x,
                    y,
                    x + float(zone["width_m"]),
                    y + float(zone["depth_m"]),
                )
            )

        # Decorations are deliberately not route blockers. They are exported
        # for visual audit so real obstacles can be promoted to blocked_zones
        # later without changing simulation code.
        for dec in self.layout.get("decorations", []):
            if not {"x", "y", "width_m", "depth_m"} <= set(dec):
                continue
            x = float(dec["x"])
            y = float(dec["y"])
            self.visual_obstacles.append(
                RectObstacle(
                    f"visual:{dec.get('id', len(self.visual_obstacles))}",
                    "visual_only",
                    x,
                    y,
                    x + float(dec["width_m"]),
                    y + float(dec["depth_m"]),
                )
            )

        self._safe_x_lines, self._safe_y_lines = self._build_safe_lines()

    @staticmethod
    def _segment_is_routing_obstacle(rack_id: str, seg_i: int) -> bool:
        # J horizontal arms and U are preserved in layout.json for SAP/bin
        # compatibility, but their post-Codex physical topology is unresolved
        # and currently overlaps other rack bodies. Treat them as storage
        # positions, not route blockers, until the site visit resolves geometry.
        if rack_id == "U":
            return False
        if rack_id == "J" and seg_i in (0, 2):
            return False
        return True

    def _build_safe_lines(self) -> tuple[list[float], list[float]]:
        width = float(self.layout["building"]["width_m"])
        depth = float(self.layout["building"]["depth_m"])
        clearance = float(getattr(config, "ROUTE_CLEARANCE_M", 0.6))
        xs = {clearance, width - clearance, self.kitting_x, config.REACH_TRUCK_DEPOT_X}
        ys = {clearance, depth - clearance, self.kitting_y, config.REACH_TRUCK_DEPOT_Y}
        for block in self.route_obstacles:
            xs.add(block.x0 - clearance)
            xs.add(block.x1 + clearance)
            ys.add(block.y0 - clearance)
            ys.add(block.y1 + clearance)
        xs = {round(x, 3) for x in xs if clearance <= x <= width - clearance}
        ys = {round(y, 3) for y in ys if clearance <= y <= depth - clearance}
        return sorted(xs), sorted(ys)

    def _segment_for_position(self, position_id: str) -> dict:
        pos = self.positions[position_id]
        return self._segments_by_key[(pos.rack_id, pos.segment_index)]

    def _candidate_access_sides(self, position_id: str, mode: str) -> list[str]:
        pos = self.positions[position_id]
        segment = self._segment_for_position(position_id)
        axis = _segment_axis(segment)
        if mode == "reach_truck":
            side = segment.get("rt_aisle_side")
        elif self.can_pick_directly(position_id):
            side = segment.get("kit_corridor_side")
        else:
            side = segment.get("rt_aisle_side")

        if _is_valid_side(side):
            return [side]

        # Unknown side: keep the assumption explicit and try both physically
        # plausible aisle faces. This keeps the route valid without declaring
        # the TBD corridor as a measured fact.
        if axis == "y":
            if pos.rack_id == "J":
                return ["west", "east"]
            return ["west", "east"]
        return ["south", "north"]

    def _access_class_for_position(self, position_id: str, mode: str) -> str:
        if mode == "reach_truck":
            return "rt"
        return "kit" if self.can_pick_directly(position_id) else "rt"

    def access_point_for_position(
        self,
        position_id: str,
        mode: str = "operator",
        from_xy: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        pos = self.positions[position_id]
        segment = self._segment_for_position(position_id)
        axis = _segment_axis(segment)
        clearance = float(getattr(config, "ROUTE_CLEARANCE_M", 0.6))
        offset = float(self.layout.get("rack_depth_m", 1.3)) / 2 + clearance

        def _points_for_sides(sides: list[str]) -> list[tuple[float, float]]:
            out: list[tuple[float, float]] = []
            for side in sides:
                if axis == "y":
                    if side == "west":
                        out.append((pos.x - offset, pos.y))
                    elif side == "east":
                        out.append((pos.x + offset, pos.y))
                else:
                    if side == "south":
                        out.append((pos.x, pos.y - offset))
                    elif side == "north":
                        out.append((pos.x, pos.y + offset))
            return out

        sides = self._candidate_access_sides(position_id, mode)
        candidates = _points_for_sides(sides)
        candidates = self._valid_or_escaped_access_points(candidates, axis)

        fallback_sides = ["west", "east"] if axis == "y" else ["south", "north"]
        fallback_candidates = self._valid_or_escaped_access_points(_points_for_sides(fallback_sides), axis)
        for candidate in fallback_candidates:
            if candidate not in candidates:
                candidates.append(candidate)

        if not candidates:
            candidates = fallback_candidates

        if not candidates:
            # Last resort for validation: use the rack centre so the caller
            # raises a loud "inside obstacle" error instead of hiding the bad
            # geometry.
            candidates = [(pos.x, pos.y)]

        if from_xy is None or len(candidates) == 1:
            return candidates[0]

        best = None
        for candidate in candidates:
            try:
                route = self.route_between_points(from_xy, candidate, mode=mode)
            except ValueError:
                continue
            if best is None or route.distance < best[0]:
                best = (route.distance, candidate)
        return best[1] if best else candidates[0]

    def _valid_or_escaped_access_points(
        self,
        points: list[tuple[float, float]],
        segment_axis: str,
    ) -> list[tuple[float, float]]:
        clearance = float(getattr(config, "ROUTE_CLEARANCE_M", 0.6))
        out: list[tuple[float, float]] = []
        for point in points:
            if self._point_inside_building(point) and not self._point_inside_any_obstacle(point):
                out.append(point)
                continue
            x, y = point
            for rect in self.route_obstacles:
                if not self._point_inside_rect(point, rect):
                    continue
                if segment_axis == "y":
                    escaped = [(x, rect.y0 - clearance), (x, rect.y1 + clearance)]
                else:
                    escaped = [(rect.x0 - clearance, y), (rect.x1 + clearance, y)]
                for e in escaped:
                    if self._point_inside_building(e) and not self._point_inside_any_obstacle(e):
                        out.append((round(e[0], 3), round(e[1], 3)))
        # Keep order stable while removing duplicates.
        unique: list[tuple[float, float]] = []
        for p in out:
            p = (round(float(p[0]), 3), round(float(p[1]), 3))
            if p not in unique:
                unique.append(p)
        return unique

    def route_to_position(
        self,
        from_xy: tuple[float, float],
        position_id: str,
        mode: str = "operator",
    ) -> RouteResult:
        origin = (round(float(from_xy[0]), 3), round(float(from_xy[1]), 3))
        pos = self.positions[position_id]
        access_key = (
            mode,
            self._access_class_for_position(position_id, mode),
            origin,
            pos.rack_id,
            pos.segment_index,
            pos.bay_code,
        )
        target = self._access_point_cache.get(access_key)
        if target is None:
            target = self.access_point_for_position(position_id, mode=mode, from_xy=origin)
            self._access_point_cache[access_key] = target
        key = (mode, origin, target)
        if key in self._route_to_position_cache:
            return self._route_to_position_cache[key]
        result = self.route_between_points(origin, target, mode=mode)
        self._route_to_position_cache[key] = result
        return result

    def route_between_points(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        mode: str = "operator",
    ) -> RouteResult:
        start = (round(float(start[0]), 3), round(float(start[1]), 3))
        end = (round(float(end[0]), 3), round(float(end[1]), 3))
        key = (mode, start, end)
        if key in self._route_cache:
            return self._route_cache[key]
        if start == end:
            result = RouteResult(0.0, (start,), ())
            self._route_cache[key] = result
            return result
        if not self._point_inside_building(start) or not self._point_inside_building(end):
            raise ValueError(f"Route endpoint outside building: {start} -> {end}")
        if self._point_inside_any_obstacle(start) or self._point_inside_any_obstacle(end):
            raise ValueError(f"Route endpoint inside rack/blocked zone: {start} -> {end}")

        best: RouteResult | None = None
        # Manhattan lower bound: every rectilinear path is at least
        # |dx|+|dy| long, which is exactly the length of the two L-bend
        # candidates. If either L-bend is obstruction-free it is globally
        # optimal — skip generating the ~600 detour candidates entirely
        # (2026-06-09 perf fix; the common aisle-to-aisle hop is an L).
        for path in (self._clean_path([start, (end[0], start[1]), end]),
                     self._clean_path([start, (start[0], end[1]), end])):
            if not self.route_intersections(path):
                best = RouteResult(self._path_length(path), tuple(path), ())
                break
        if best is None:
            # Candidates are sorted by length, so the FIRST obstruction-free
            # path is the shortest feasible one — stop there.
            for path in self._route_candidates(start, end):
                if self.route_intersections(path):
                    continue
                best = RouteResult(self._path_length(path), tuple(path), ())
                break
        if best is None:
            direct = self._clean_path([start, (start[0], end[1]), end])
            intersections = tuple(self.route_intersections(direct))
            raise ValueError(
                f"No obstruction-free rectilinear route from {start} to {end}; "
                f"direct intersections={list(intersections)}"
            )
        self._route_cache[key] = best
        self._route_cache[(mode, end, start)] = RouteResult(
            best.distance,
            tuple(reversed(best.path)),
            best.intersections,
        )
        return best

    def _route_candidates(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> list[list[tuple[float, float]]]:
        xs = self._nearby_lines(start[0], end[0], self._safe_x_lines)
        ys = self._nearby_lines(start[1], end[1], self._safe_y_lines)
        paths: list[list[tuple[float, float]]] = [
            self._clean_path([start, (end[0], start[1]), end]),
            self._clean_path([start, (start[0], end[1]), end]),
        ]
        for y in ys:
            paths.append(self._clean_path([start, (start[0], y), (end[0], y), end]))
        for x in xs:
            paths.append(self._clean_path([start, (x, start[1]), (x, end[1]), end]))
        for x in xs:
            for y in ys:
                paths.append(self._clean_path([start, (x, start[1]), (x, y), (end[0], y), end]))
                paths.append(self._clean_path([start, (start[0], y), (x, y), (x, end[1]), end]))
        # Short routes first; validation still checks every segment.
        unique: dict[tuple, list[tuple[float, float]]] = {}
        for p in paths:
            unique[tuple(p)] = p
        return sorted(unique.values(), key=self._path_length)

    @staticmethod
    def _nearby_lines(a: float, b: float, lines: list[float], limit: int = 18) -> list[float]:
        midpoint = (a + b) / 2
        forced = {round(a, 3), round(b, 3)}
        if lines:
            forced.add(lines[0])
            forced.add(lines[-1])
        candidates = set(lines) | forced
        ordered = sorted(candidates, key=lambda v: (min(abs(v - a), abs(v - b), abs(v - midpoint)), v))
        out = []
        for v in list(forced) + ordered:
            if v not in out:
                out.append(v)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _clean_path(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for x, y in points:
            p = (round(float(x), 3), round(float(y), 3))
            if out and out[-1] == p:
                continue
            out.append(p)
        compact: list[tuple[float, float]] = []
        for p in out:
            compact.append(p)
            while len(compact) >= 3:
                a, b, c = compact[-3], compact[-2], compact[-1]
                if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
                    compact.pop(-2)
                else:
                    break
        return compact

    @staticmethod
    def _path_length(path: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> float:
        total = 0.0
        for a, b in zip(path, path[1:]):
            total += abs(a[0] - b[0]) + abs(a[1] - b[1])
        return total

    def route_intersections(self, path: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> list[str]:
        hits: list[str] = []
        for a, b in zip(path, path[1:]):
            for block in self.route_obstacles:
                if self._axis_segment_intersects_rect(a, b, block):
                    hits.append(block.obstacle_id)
        return sorted(set(hits))

    def visual_intersections(self, path: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> list[str]:
        hits: list[str] = []
        for a, b in zip(path, path[1:]):
            for block in self.visual_obstacles:
                if self._axis_segment_intersects_rect(a, b, block):
                    hits.append(block.obstacle_id)
        return sorted(set(hits))

    @staticmethod
    def _axis_segment_intersects_rect(
        a: tuple[float, float],
        b: tuple[float, float],
        rect: RectObstacle,
    ) -> bool:
        eps = 1e-7
        ax, ay = a
        bx, by = b
        if abs(ax - bx) < eps:
            x = ax
            y0, y1 = sorted((ay, by))
            return rect.x0 + eps < x < rect.x1 - eps and max(y0, rect.y0 + eps) < min(y1, rect.y1 - eps)
        if abs(ay - by) < eps:
            y = ay
            x0, x1 = sorted((ax, bx))
            return rect.y0 + eps < y < rect.y1 - eps and max(x0, rect.x0 + eps) < min(x1, rect.x1 - eps)
        # The router only emits Manhattan segments. Treat diagonal segments as
        # invalid by reporting an intersection-like failure.
        return True

    def _point_inside_building(self, p: tuple[float, float]) -> bool:
        x, y = p
        return 0 <= x <= self.layout["building"]["width_m"] and 0 <= y <= self.layout["building"]["depth_m"]

    def _point_inside_any_obstacle(self, p: tuple[float, float]) -> bool:
        for rect in self.route_obstacles:
            if self._point_inside_rect(p, rect):
                return True
        return False

    @staticmethod
    def _point_inside_rect(p: tuple[float, float], rect: RectObstacle) -> bool:
        x, y = p
        eps = 1e-7
        return rect.x0 + eps < x < rect.x1 - eps and rect.y0 + eps < y < rect.y1 - eps

    def _overlapping_rack_geometry(self) -> list[dict]:
        racks = [r for r in self.route_obstacles if r.kind == "rack"] + list(self.non_blocking_storage)
        overlaps: list[dict] = []
        for i, a in enumerate(racks):
            for b in racks[i + 1:]:
                x0 = max(a.x0, b.x0)
                x1 = min(a.x1, b.x1)
                y0 = max(a.y0, b.y0)
                y1 = min(a.y1, b.y1)
                if x1 <= x0 or y1 <= y0:
                    continue
                area = (x1 - x0) * (y1 - y0)
                if area <= 0.01:
                    continue
                overlaps.append({
                    "a": a.obstacle_id,
                    "b": b.obstacle_id,
                    "overlap_area_m2": round(area, 3),
                    "rect": {
                        "x0": round(x0, 3),
                        "y0": round(y0, 3),
                        "x1": round(x1, 3),
                        "y1": round(y1, 3),
                    },
                })
        return overlaps

    def _position_ids_for_route_validation(
        self,
        *,
        full: bool,
        sample_per_segment: int,
    ) -> list[str]:
        by_segment: dict[tuple[str, int], dict[int, str]] = {}
        for pid, pos in self.positions.items():
            if pos.level != 0:
                continue
            if pos.position != 1:
                continue
            key = (pos.rack_id, pos.segment_index)
            by_segment.setdefault(key, {}).setdefault(pos.bay_code, pid)

        selected: list[str] = []
        n = max(1, int(sample_per_segment))
        for key in sorted(by_segment):
            bay_map = by_segment[key]
            bays = sorted(bay_map)
            if not bays:
                continue
            if full or len(bays) <= n:
                chosen_bays = bays
            else:
                indexes = {0, len(bays) - 1}
                if n >= 3:
                    indexes.add(len(bays) // 2)
                while len(indexes) < n:
                    # Evenly add more samples only when the caller asks for them.
                    frac = len(indexes) / max(1, n - 1)
                    indexes.add(min(len(bays) - 1, round(frac * (len(bays) - 1))))
                chosen_bays = [bays[i] for i in sorted(indexes)]
            selected.extend(bay_map[b] for b in chosen_bays)
        return sorted(set(selected))

    def validate_route_model(
        self,
        *,
        full: bool = False,
        sample_per_segment: int = 3,
        max_sample_paths: int = 60,
    ) -> dict:
        issues: list[str] = []
        warnings: list[str] = []
        width = self.layout["building"]["width_m"]
        depth = self.layout["building"]["depth_m"]
        for pid, pos in self.positions.items():
            if not (0 <= pos.x <= width and 0 <= pos.y <= depth):
                issues.append(f"{pid}: slot coordinate outside building ({pos.x:.2f},{pos.y:.2f})")

        for rack in self.layout["racks"]:
            for i, seg in enumerate(rack["segments"]):
                if not self._segment_is_routing_obstacle(rack["id"], i):
                    warnings.append(
                        f"{rack['id']} segment {i}: storage segment excluded from route blockers due unresolved CAD/layout overlap"
                    )
                if seg.get("kit_corridor_side") == "TBD":
                    warnings.append(f"{rack['id']} segment {i}: kit_corridor_side is TBD; direct kit access disabled")
                if seg.get("rt_aisle_side") == "TBD":
                    warnings.append(f"{rack['id']} segment {i}: rt_aisle_side is TBD; routing uses nearest valid face")

        overlaps = self._overlapping_rack_geometry()
        if overlaps:
            warnings.append(
                f"overlapping rack geometry remains unresolved "
                f"({len(overlaps)} overlap(s)); geometry was not changed to make validation pass"
            )

        sampled_paths: list[dict] = []
        seen_access: set[tuple[str, str, tuple[float, float]]] = set()
        tested_positions = self._position_ids_for_route_validation(
            full=full,
            sample_per_segment=sample_per_segment,
        )
        for pid in tested_positions:
            pos = self.positions[pid]
            for mode, start in (
                ("operator", (self.kitting_x, self.kitting_y)),
                ("reach_truck", (config.REACH_TRUCK_DEPOT_X, config.REACH_TRUCK_DEPOT_Y)),
            ):
                try:
                    route = self.route_to_position(start, pid, mode=mode)
                except ValueError as exc:
                    issues.append(f"{mode} route to {pid}: {exc}")
                    continue
                access = route.path[-1]
                key = (pos.rack_id, mode, access)
                if key not in seen_access and len(sampled_paths) < max_sample_paths:
                    seen_access.add(key)
                    sampled_paths.append({
                        "mode": mode,
                        "position_id": pid,
                        "rack": pos.rack_id,
                        "distance_m": round(route.distance, 3),
                        "path": [list(p) for p in route.path],
                        "visual_only_intersections": self.visual_intersections(route.path),
                    })

        return {
            "status": "FAIL" if issues else ("WARN" if warnings else "PASS"),
            "issues": issues,
            "warnings": warnings,
            "rack_obstacles": [r.as_dict() for r in self.route_obstacles if r.kind == "rack"],
            "non_blocking_storage": [r.as_dict() for r in self.non_blocking_storage],
            "blocked_zones": [r.as_dict() for r in self.route_obstacles if r.kind != "rack"],
            "visual_only_zones": [r.as_dict() for r in self.visual_obstacles],
            "corridor_lines": {
                "x": self._safe_x_lines,
                "y": self._safe_y_lines,
            },
            "validation_scope": "full" if full else "sample",
            "validated_positions": len(tested_positions),
            "validated_routes": len(tested_positions) * 2,
            "overlapping_rack_geometry": overlaps,
            "sample_paths": sampled_paths,
            "notes": [
                "Simulation routes use rack bodies + explicit blocked_zones as blockers.",
                "decorations are exported as visual_only_zones and do not affect KPIs unless promoted to blocked_zones in layout.json.",
            ],
        }

    def write_route_debug(self, path: str, payload: dict | None = None) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = payload or self.validate_route_model()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
