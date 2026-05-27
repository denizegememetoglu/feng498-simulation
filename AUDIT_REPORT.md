# FENG498 Simulation Correctness Audit

Date: 2026-05-27

## Summary

The model is now more coherent and more conservative without changing
`config/layout.json` geometry or SAP join keys. The biggest correction is that
walking and reach-truck travel no longer move to rack center points with a
plain Manhattan shortcut. They route to aisle-side service points and reject
paths that intersect rack blockers or explicit blocked zones.

The audit still finds one major unresolved layout risk: the post-Codex
`layout.json` has unresolved overlap between old J/U topology and newer rack
extents. Because geometry edits require approval, J horizontal arms and U are
kept as storage positions but excluded from route blockers and flagged in
`route_debug.json`. The latest debug export lists 10 overlapping rack-geometry
rectangles; this is a high-risk assumption, not a solved geometry issue.

## Bugs Found And Fixed

- Direct rack-center travel allowed paths through rack bodies.
  Fixed in `src/warehouse.py` with obstacle-checked rectilinear routing.
- Reach-truck travel used direct depot-to-rack-center distance.
  Fixed to route to aisle-side service points.
- Kardex fallback coordinate used the zone corner.
  Fixed to use the Kardex zone center when station coordinates are absent.
- `TBD` kit-corridor sides were treated as confirmed kit access.
  Changed to conservative behavior: TBD does not grant direct kit access.
- Kardex materials were still consuming rack slots in non-SAP policies.
  Fixed by filtering Kardex materials out of rack slotting policies.
- Fallback slot pools could reuse already-filled slots, causing silent capacity
  overflow. Fixed with `pop_free()` across all slotting policies.
- Missing data directory errors were unclear.
  Fixed with an explicit `DATA_FILE`/data-directory error.
- `web/index.html` used CAD/DWG coordinates instead of simulation coordinates.
  Replaced with an offline schematic viewer driven by `web/layout.json` and
  `web/route_debug.json`.
- Browser mirrors could stay stale after `src.main`.
  `src.main` now mirrors current KPI/debug files into `web/data` and `docs/data`.
- Route validation was too slow for a normal sanity command.
  Fixed with route/service-point caching and a representative default route
  sample; exhaustive route validation is now opt-in.
- ZWM92 order fitting was recomputed several times in one validation process.
  Fixed with in-process cached orders/fits; no sampling behavior changed.

## Assumptions Kept

- `config/layout.json` remains the physical simulation source.
- SAP compatibility remains keyed by `(rack, bay, position)`; no bin codes or
  rack IDs were changed.
- Visual decorations are not KPI blockers unless promoted to `blocked_zones`.
- ZWM92 fitted distribution driver remains the current demand source.
- Milkrun remains disabled; no rack-aisle milkrun routing is invented.

## Downgraded To TODO / Explicit Risk

- **High risk: overlapping rack geometry remains.** `route_debug.json`
  currently reports 10 overlapping rack rectangles, especially around the
  unresolved J/U topology. Geometry was not edited to make validation pass.
  J horizontal arms and U are storage-only route TODOs until a geometry
  decision/site visit resolves it.
- `layout.json` has no explicit `aisles` or `blocked_zones`; the route graph is
  inferred from rack blockers and safe corridor lines.
- `production_lines[]` is absent from the current `layout.json`; per-line
  kitting falls back to the global kitting point.
- 412 storage-bin strings are malformed/non-rack; 9 decoded SAP bins do not map
  to a modeled slot.
- Kardex is still modeled as a shared 4-capacity resource at one station point.
- `sim_v2.html` is secondary; `web/index.html` + `route_debug.json` is the
  route-debug view to trust after this audit.

## Validation Results

Commands run with the repo venv:

```bash
.venv/bin/python -m src.validate
.venv/bin/python -m src.validate --full-routes   # optional exhaustive route check
.venv/bin/python -m src.validate --full-sim      # optional full 5-day statistical check
.venv/bin/python -m src.main
.venv/bin/python -m src.analyze
chromium --headless --disable-gpu --screenshot=/tmp/feng498-index2.png --window-size=1280,800 http://127.0.0.1:8001/web/index.html
```

Key validation statuses:

- Static sanity: WARN, no fatal issue.
- Assignment sanity: PASS; no duplicate slot assignments after the fix.
- Reproducibility check: PASS for the first 10 generated orders with fixed seed.
- Route model: WARN, 0 issues, 16 explicit TODO/warning assumptions,
  representative sample scope, 78 routes checked.
- `python -m src.validate` now runs a 0.5-day quick statistical sample and
  completed in 23.3 s on this machine. Quick-sample p-values are approximate
  because expected chi-square cells are sparse: chi-square p = `0.0697`,
  paired t-test p = `0.0781`.
- Earlier full 5-day validation in this audit still rejected against SAP/ZWM92
  distribution shape: chi-square p = `4.42e-15`, paired t-test p = `1.82e-157`.
- `output/route_debug.json`, `web/route_debug.json`, and
  `docs/route_debug.json` were generated; `web/index.html` loads the debug
  paths and shows `sample / 78 routes / 10 rack overlaps`.

Post-fix KPI summary:

| Policy | Orders | Prep min | Lead min | Walk m | RT util |
|---|---:|---:|---:|---:|---:|
| Baseline (Heuristic) | 421 | 3.95 | 3.95 | 92.1 | 3.8% |
| Baseline (Actual SAP) | 477 | 3.57 | 3.57 | 86.6 | 3.4% |
| Usage-based ABC | 423 | 3.83 | 3.83 | 90.3 | 3.7% |
| Double ABC | 442 | 4.76 | 4.76 | 103.9 | 5.6% |
| Travel-distance Optimized | 469 | 4.69 | 4.69 | 74.2 | 7.5% |

KPI impact versus the old rack-center Manhattan-distance run:

| Policy | Old walk m | New route walk m | Delta |
|---|---:|---:|---:|
| Baseline (Heuristic) | 79.5 | 92.1 | +12.6 |
| Baseline (Actual SAP) | 80.5 | 86.6 | +6.1 |
| Usage-based ABC | 83.9 | 90.3 | +6.4 |
| Double ABC | 90.2 | 103.9 | +13.7 |
| Travel-distance Optimized | 84.5 | 74.2 | -10.3 |

These KPI shifts are expected: the old metric allowed rack-center Manhattan
shortcuts, while the new metric routes to aisle-side service points and also
includes the Kardex/rack-slot sanity fixes. The Travel-distance policy changes
direction because its slot sort key now follows the same service-point route
distance used by the simulation.

## Files Changed

- `src/warehouse.py`
- `src/simulation.py`
- `src/slotting.py`
- `src/validate.py`
- `src/main.py`
- `src/zwm92.py`
- `src/config.py`
- `src/data_loader.py`
- `src/recorder.py`
- `web/index.html`
- `docs/index.html`
- `web/route_debug.json`, `docs/route_debug.json`
- `web/data/*`, `docs/data/*`
- `AUDIT_REPORT.md`

Pre-existing dirty/untracked artifacts were not cleaned or reverted.

## Run Instructions

Use the project venv; system Python is missing `simpy`.

```bash
cd /home/dege/feng498-simulation
source .venv/bin/activate
python -m src.validate              # quick 0.5-day sanity + sampled routes
python -m src.validate --full-sim   # slower full-horizon statistical check
python -m src.validate --full-routes
python -m src.main
python -m src.analyze
python3 -m http.server 8001
```

Then open:

- `http://127.0.0.1:8001/web/index.html`
- `http://127.0.0.1:8001/web/route_debug.json`

If `/web/index.html` returns 404, the server was started from the wrong
directory. Stop it and restart `python3 -m http.server 8001` from
`/home/dege/feng498-simulation`.

Optional: set `MPLCONFIGDIR=/tmp` before plotting commands to avoid the
Matplotlib cache warning from `/home/dege/.config/matplotlib`.
