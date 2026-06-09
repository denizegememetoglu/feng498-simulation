"""TimelineRecorder — opt-in JSONL event log for sim_v2.html playback (AD-2).

Activated via `config.RECORD_TIMELINE = True` (or `--record-timeline` CLI flag).
Writes one JSON object per line to `output/sim_timeline_<policy>.jsonl`.

Event types (see plan AD-2):
  order_start   {t, type, order_id, line, items_n}
  op_grant      {t, type, order_id, op_id, queue_wait_min}
  op_move       {t, type, order_id, op_id, from:[x,y], to:[x,y], dist_m}
  rt_dispatch   {t, type, order_id, rt_id, pos_id, queue_wait_min}
  pick          {t, type, order_id, op_id, rack, bay, level, position, pos_id, material}
  kardex_pick   {t, type, order_id, op_id, station:[x,y], material}
  order_done    {t, type, order_id, walk_m, lead_min, prep_min, n_picks}
  kpi_snapshot  {t, type, orders, avg_walk, avg_lead, rt_util_pct, op_util_pct}

All coordinates are in layout meters (warehouse.positions[pid].x / .y). Times
in SimPy minutes. `op_id` and `rt_id` are stable per-order placeholders; the
recorder does not model individual resource identity (SimPy uses anonymous
Resource slots) — playback can disambiguate by `order_id`.

Recorder is fail-safe: missing fields default to None, file handle errors are
caught and logged once. Keeps the sim running even when disk fills up.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any


class TimelineRecorder:
    """Opt-in JSONL event recorder. Use as a no-op when policy doesn't need it."""

    __slots__ = ("_fh", "_policy", "_path", "_n_events", "_n_orders", "_n_picks",
                 "_kpi_last_t", "_kpi_interval", "_first_t", "_errored", "_meta")

    def __init__(self, policy_name: str, output_dir: str = "output",
                 kpi_interval_min: float = 10.0):
        from src import config  # local to avoid top-level cycle
        os.makedirs(output_dir, exist_ok=True)
        safe = (policy_name.lower()
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                .replace("-", "_"))
        self._policy = policy_name
        self._path = os.path.join(output_dir, f"sim_timeline_{safe}.jsonl")
        self._fh = open(self._path, "w", encoding="utf-8", buffering=1 << 16)
        self._n_events = 0
        self._n_orders = 0
        self._n_picks = 0
        self._kpi_last_t = 0.0
        self._kpi_interval = float(kpi_interval_min)
        self._first_t: float | None = None
        self._errored = False
        # Manifest header (line 0) lets the playback engine know what it loaded.
        self._meta = {
            "type": "header",
            "policy": policy_name,
            "schema_version": "1.1",
            "coord_system": "layout_m",
            "wall_clock_started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "config": {
                "NUM_REACH_TRUCKS": int(getattr(config, "NUM_REACH_TRUCKS", 0)),
                "NUM_OPERATORS": int(getattr(config, "NUM_OPERATORS", 0)),
                "NUM_KARDEX_UNITS": int(getattr(config, "NUM_KARDEX_UNITS", 0)),
                "SIM_DAYS": int(getattr(config, "SIM_DAYS", 0)),
                "SHIFT_MODE": str(getattr(config, "SHIFT_MODE", "continuous")),
                "RANDOM_SEED": int(getattr(config, "RANDOM_SEED", 0)),
            },
        }
        self._emit_raw(self._meta)

    @property
    def path(self) -> str:
        return self._path

    @property
    def n_events(self) -> int:
        return self._n_events

    def _emit_raw(self, obj: dict[str, Any]) -> None:
        if self._errored or self._fh is None:
            return
        try:
            self._fh.write(json.dumps(obj, ensure_ascii=False, default=str))
            self._fh.write("\n")
            self._n_events += 1
        except (OSError, ValueError) as exc:
            self._errored = True
            print(f"[recorder] WARN: write failed for {self._path}: {exc}")

    def _emit(self, t: float, evt: dict[str, Any]) -> None:
        if self._first_t is None:
            self._first_t = t
        evt["t"] = round(float(t), 4)
        self._emit_raw(evt)

    # ── Event emitters ────────────────────────────────────────────────────
    def order_start(self, t: float, order_id: int, line: str | None,
                    items_n: int) -> None:
        self._n_orders += 1
        self._emit(t, {"type": "order_start", "order_id": int(order_id),
                       "line": line, "items_n": int(items_n)})

    def op_grant(self, t: float, order_id: int, op_id: int,
                 queue_wait_min: float) -> None:
        self._emit(t, {"type": "op_grant", "order_id": int(order_id),
                       "op_id": int(op_id),
                       "queue_wait_min": round(float(queue_wait_min), 4)})

    def op_move(self, t: float, order_id: int, op_id: int,
                from_xy: tuple[float, float], to_xy: tuple[float, float],
                dist_m: float, path=None, start_t: float | None = None) -> None:
        payload = {"type": "op_move", "order_id": int(order_id),
                   "op_id": int(op_id),
                   "t_start": round(float(start_t if start_t is not None else t), 4),
                   "t_end": round(float(t), 4),
                   "from": [round(from_xy[0], 3), round(from_xy[1], 3)],
                   "to":   [round(to_xy[0], 3),   round(to_xy[1], 3)],
                   "dist_m": round(float(dist_m), 3)}
        if path:
            payload["path"] = [[round(p[0], 3), round(p[1], 3)] for p in path]
        self._emit(t, payload)

    def rt_dispatch(self, t: float, order_id: int, rt_id: int, pos_id: str,
                    queue_wait_min: float, path=None,
                    travel_time_min: float | None = None,
                    service_time_min: float | None = None,
                    return_time_min: float | None = None) -> None:
        payload = {"type": "rt_dispatch", "order_id": int(order_id),
                   "rt_id": int(rt_id), "pos_id": str(pos_id),
                   "queue_wait_min": round(float(queue_wait_min), 4),
                   "t_start": round(float(t), 4)}
        if travel_time_min is not None:
            payload["travel_time_min"] = round(float(travel_time_min), 4)
            payload["t_arrive"] = round(float(t + travel_time_min), 4)
        if service_time_min is not None:
            payload["service_time_min"] = round(float(service_time_min), 4)
        if travel_time_min is not None or service_time_min is not None:
            payload["t_end"] = round(float(t + (travel_time_min or 0.0) + (service_time_min or 0.0)), 4)
        if return_time_min is not None:
            # Depot return leg (truck unavailable until t_home).
            payload["return_time_min"] = round(float(return_time_min), 4)
            if "t_end" in payload:
                payload["t_home"] = round(payload["t_end"] + float(return_time_min), 4)
        if path:
            payload["path"] = [[round(p[0], 3), round(p[1], 3)] for p in path]
        self._emit(t, payload)

    def pick(self, t: float, order_id: int, op_id: int, pos, material: str) -> None:
        """pos is a PalletPosition with rack_id, bay_code, level, position, x, y."""
        self._n_picks += 1
        self._emit(t, {
            "type": "pick", "order_id": int(order_id), "op_id": int(op_id),
            "rack": pos.rack_id, "bay": int(pos.bay_code),
            "level": int(pos.level) + 1, "position": int(pos.position),
            "pos_id": pos.position_id, "material": str(material),
            "xy": [round(pos.x, 3), round(pos.y, 3)],
        })

    def kardex_pick(self, t: float, order_id: int, op_id: int,
                    station_xy: tuple[float, float], material: str) -> None:
        self._n_picks += 1
        self._emit(t, {"type": "kardex_pick", "order_id": int(order_id),
                       "op_id": int(op_id),
                       "station": [round(station_xy[0], 3), round(station_xy[1], 3)],
                       "material": str(material)})

    def order_done(self, t: float, order_id: int, walk_m: float,
                   lead_min: float, prep_min: float, n_picks: int) -> None:
        self._emit(t, {"type": "order_done", "order_id": int(order_id),
                       "walk_m": round(float(walk_m), 3),
                       "lead_min": round(float(lead_min), 4),
                       "prep_min": round(float(prep_min), 4),
                       "n_picks": int(n_picks)})

    def maybe_kpi_snapshot(self, t: float, kpi) -> None:
        """Emit a kpi_snapshot every `kpi_interval` sim-min, sampled from the
        live KPICollector. Cheap to call every tick; emits only when due."""
        if t - self._kpi_last_t < self._kpi_interval:
            return
        self._kpi_last_t = t
        orders = len(kpi.orders) if hasattr(kpi, "orders") else 0
        if orders > 0 and hasattr(kpi, "orders"):
            avg_walk = sum(o.walk_distance for o in kpi.orders) / orders
            avg_lead = sum(o.lead_time for o in kpi.orders) / orders
        else:
            avg_walk = 0.0
            avg_lead = 0.0
        from src import config  # local import keeps recorder standalone
        rt_busy = getattr(kpi, "_rt_busy_time", 0.0)
        op_busy = getattr(kpi, "_op_busy_time", 0.0)
        rt_cap = t * max(1, int(getattr(config, "NUM_REACH_TRUCKS", 7)))
        op_cap = t * max(1, int(getattr(config, "NUM_OPERATORS", 8)))
        rt_util = (rt_busy / rt_cap) * 100 if rt_cap > 0 else 0.0
        op_util = (op_busy / op_cap) * 100 if op_cap > 0 else 0.0
        self._emit(t, {"type": "kpi_snapshot", "orders": int(orders),
                       "avg_walk": round(avg_walk, 3),
                       "avg_lead": round(avg_lead, 4),
                       "rt_util_pct": round(rt_util, 2),
                       "op_util_pct": round(op_util, 2)})

    def footer(self) -> None:
        """Optional summary line at EOF for debugging."""
        self._emit_raw({"type": "footer", "n_orders": self._n_orders,
                        "n_picks": self._n_picks, "n_events": self._n_events,
                        "first_t": self._first_t})

    def close(self) -> None:
        if self._fh is None:
            return
        try:
            self.footer()
            self._fh.flush()
            self._fh.close()
        except OSError:
            pass
        self._fh = None

    # Context-manager hooks for `with TimelineRecorder(...) as rec:`
    def __enter__(self) -> "TimelineRecorder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
