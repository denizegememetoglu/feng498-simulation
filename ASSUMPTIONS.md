# Layout & Modeling Assumptions

> **Status (May 11, 2026 — post per-bay correction):** Rack inventory + per-bay
> pallet widths confirmed from `data/rack-drawings/*.pdf`, May 11 WhatsApp from
> site report, and SAP `özet` cross-check. Total **3 137 positions** (down from the
> 3 203 PDF-stamp grand total because per-bay reductions are now modelled
> explicitly via `bay_overrides` in `config/layout.json`). Top-down topology
> committed May 6 from the user's hand-drawn sketch. Exact rack-to-rack
> distances, kit-corridor sides for J, H, U, and the **kit corridor → production
> line** map (from the May 11 CAD image — see §17) still need the **May 20
> site visit**.
>
> Confirmed items marked ✅. Open items still TODO.

Original "11 linear modules with alternating 3 m RT / 1.6 m kit aisle" model was fictional.
Real layout (May 6 commit) is **10 vertical racks running south→north left-to-right
(J, H, I, G, F, E, D, C, B, A) plus U as a single horizontal rack across the north
end**. J is a polyline "[" bracket on the far west (bottom arm + vertical + top arm,
2 corners). G ↔ J's bottom arm and U ↔ J's top arm are **CLOSED junctions** (no
traffic flow — modelled as visual proximity only, not a passable corridor).
Source of truth is `config/layout.json`; this file documents the assumptions
behind those numbers.

---

## 1. Rack inventory

✅ **All 11 PDFs decoded May 6 from `data/rack-drawings/*.pdf`. PDF stamp
grand total 3 203 ("3203 PALET KAPASİTE" on U.pdf).**

✅ **Per-bay widths corrected May 11** from the site report (May 11), then
cross-checked against the SAP `özet` sheet (every reduced bay's WhatsApp
width matches the max position seen in SAP). Many bays are "feeder" bays
of width 1 or 2 instead of the default 3 — pallets per bay vary with the
material size that lives there. Encoded as `bay_overrides` per segment in
`config/layout.json`; the simulation now materialises **3 137 positions**.
The 66-position delta vs the PDF stamp total is the cumulative effect of
those per-bay reductions; the PDF stamp is kept as `pallet_count` for
fidelity reporting (`Warehouse.pallet_capacity_from_pdf`).

| Rack | WA-confirmed exceptions | Default width | Levels |
|------|-------------------------|---------------|--------|
| A | (none) | 3 | 9 |
| B | (none) | 3 | 9 |
| C | bays 10–12 → 2 | 3 | 9 |
| D | bay 8 → 2; bays 11, 12 → 1 | 3 | 9 |
| E | bay 4 → 1 | 3 | 9 |
| F | bays 5, 6 → 2 | 3 | 9 |
| G | (none) | 3 | 9 |
| H | (none) | 3 | 8 |
| I | bay 4 → 1; bays 5–9 → 2 | 3 | 8 |
| J | bottom-arm bay 4 → 2; vertical bays 10, 11, 13, 14 → 2; **bay 12 → 0 (cart)**; top-arm bays 15–18 → 2 | 3 | 8 |
| U | bay 8 → `position_offset=1` (positions 2, 3; "1 yok") | **2** | 7 |

U is the only rack whose **default** is width 2 — every bay holds two
pallets (positions 1, 2) except U8, which is width 2 but addressed at
positions 2, 3 (its position 1 is physically absent). U14 is a "KÜÇÜK RF"
small rack with non-standard SAP positions {3, 5, 6}; modelled as width 2
for now and flagged for May 20.

| ID | Shape | Bays | Bay codes | Bay width | Levels | Pallets/bay | Pallets | Source |
|----|-------|------|-----------|-----------|--------|-------------|---------|--------|
| A  | linear | 11 | A2–A12 | **2.70 m** | 9 | 3 | **297** | ✅ A.pdf (270 cm stamped) |
| B  | **split** | 6+5 | B1–B6 + B8–B12 | 2.61 m | 9 | 3 | **261** (was 288) | ✅ B.pdf (B7 absent — physical gap) |
| C  | linear | 12 | C1–C12 | 2.61 m | 9 | 3 | **297** | ✅ C.pdf (27 missing) |
| D  | linear | 12 | D1–D12 | 2.61 m | 9 | 3 | **300** | ✅ D.pdf (24 missing) |
| E  | linear | 12 | E1–E12 | 2.61 m | 9 | 3 | **294** | ✅ E.pdf (30 missing) |
| F  | linear | 12 | F1–F12 | 2.61 m | 9 | 3 | **303** | ✅ F.pdf (21 missing) |
| G  | linear | 12 | G1–G12 | 2.196 m | 9 | 3 | **288** | ✅ G.pdf (36 missing) |
| H  | linear (vert) | 11 | H1–H11 | 2.305 m | **8** | 3 | **240** | ✅ H.pdf — heights 41/138/206/322/438/554/670/700 cm |
| I  | linear (vert) | 11 | I1–I11 | 2.305 m | **8** | 3 | **252** | ✅ I.pdf |
| J  | **5-section polyline** | **18** | J1–J18 | mixed | **8** | 3 | **381** | ✅ J.pdf — [J1] [J2-J12] [J13 KÜÇÜK RF] [J14] [J15-J18] |
| U  | **split** | 13+1 | U1–U13 + U14 KÜÇÜK RF | 1.73 m / 2.0 m | **7** | 2 | **263** | ✅ U.pdf — U14 detached small rack at west end |

**Total: 3 137 modelled positions (2026-06 state; was 3 110 pre-§18-fix)** (3 203 raw PDF-stamp capacity; difference
is feeder-bay reductions and the B7 physical gap).

The 0–87 "missing positions" per a–g rack come from ÖN/ARKA passage cutouts
where pallets cannot sit (visible as red ÖN/ARKA markers in each PDF). They
are real, not modelling errors.

Bin code convention confirmed: SAP `BR<R>-<bay:02d>-<position:02d>`
(e.g., `BRA-02-02` = rack A, bay A2, position 2). Verified against PDF bay
labels A2–A12, B1–B12, …, J1–J18, U1–U14. **TODO May 20:** confirm bay
widths for B–U match A's 270 cm; measure the actual segment break-points
of the J and U polylines.

## 2. Building footprint

- **80 m × 50 m.** Eyeballed from a 3D rendering shared by the partner; not measured.
- Kitting at front-center, Kardex front-left, trolley staging front-center next to kitting.
- **TODO May 4:** measure exterior walls; confirm dock-door positions on north wall.

## 3. Rack geometry (refined May 4 from A.pdf, assumed uniform pending other PDFs)

- Rack depth: **1.3 m** (per project KB, P12 euro pallet) — TODO confirm
- Rack height: ✅ **7.0 m** (was 7.5 m — A.pdf shows top beam at 700 cm)
- Levels: ✅ **9** (level heights from floor: 41, 138, 206, 291, 370, 461, 540, 631, 700 cm)
- Pallets per compartment: ✅ **3**
- Bay (compartment) width: ✅ **2.70 m** for rack A (11 bays × 2.70 m = 29.7 m total)
  - Other racks: TBD from their PDFs; assume 2.70 m until verified
- **TODO May 20:** measure rack depth physically; verify other racks match A's geometry.

## 4. Kit-corridor / RT-aisle assignment

✅ **Confirmed May 4** (site visit report): **alternating pattern is real, RT
enters every corridor EXCEPT the 2 m kit corridors** ("Rt genisligi iki metre olan
koridorlar haricindekilere giriyo", "birer birer atlıyodu").

**Alternation between B–G (committed in `config/layout.json`):**

| Between | Aisle type | Width |
|---------|------------|-------|
| B ↔ C   | RT | ~3 m |
| C ↔ D   | kit | **2 m** |
| D ↔ E   | RT | ~3 m |
| E ↔ F   | kit | **2 m** |
| F ↔ G   | RT | ~3 m |
| G ↔ I (across J's bottom arm at the south end, kit) | kit | **2 m** |

Each rack has either zero or one kit-corridor side (per team contact, Apr 1). **TODO May 20:**
measure exact RT aisle widths; confirm kit-corridor sides for J, H, A (currently `TBD`
in `config/layout.json`).

## 5. H and I (vertical racks 2nd and 3rd from west)

- Both H and I are **vertical** (south-north, parallel to G–A), not horizontal.
- H at x ≈ 14.3, runs y = 5 → 34.7 (29.7 m, 11 bays × 2.70 m), 8 levels.
- I at x ≈ 17.6, runs y = 5 → 34.7, 11 bays, 8 levels.
- I's east side is the kit corridor between I and G (matches G's `kit_corridor_side: west`).
- H's neighbours (J on west, I on east): aisle types `TBD` until May 20 measurement.
- **TODO May 20:** confirm H's two corridor sides; confirm exact x positions.

## 6. J rack — 5-section polyline per J.pdf (post May-11 CAD revision)

✅ **Confirmed May 11** from CAD + J.pdf detailed read.

J.pdf shows J as five physically separated sub-sections in elevation, not the
clean 3-segment `[` bracket we modeled on May 6. Updated segmentation
(post-flip coordinates — see §18):

- **J1 bottom arm:** single bay at (59.2, 10) → (61.9, 10), meets G at CLOSED
  junction.
- **J2-J12 main vertical:** 11 bays at x=70, y=6.5 → 36.2 (east wall).
  J4, J10, J11 width=2; J12 width=0 (cart parking slot).
- **J13 KÜÇÜK RF:** detached small rack at (72.0, 22.0) → (73.5, 22.0),
  flagged `small_rack: true`.
- **J14:** single detached bay at (72.0, 27.0) → (74.7, 27.0).
- **J15-J18 top arm:** 4 bays at (59.2, 37) → (70.0, 37), all width=2.
  Meets U at CLOSED junction.
- **Total: 18 bays × 8 levels = 336 modelled positions** (PDF stamp is 381;
  PDF counts pre-feeder-bay slots).
- **G ↔ J1 junction (~59.2, 10): CLOSED.** No traffic flow.
- **U ↔ J15 junction (~59.2, 37): CLOSED.** No traffic flow.
- Closed-junction X marks are now drawn from `closed_junctions[]` in
  `layout.json` (renderer in `web/index.html`).
- Kit/RT sides on all 5 segments: `TBD` until May 20.

## 7. U rack — split: main run + detached U14 KÜÇÜK RF (post May-11)

✅ **Confirmed May 11** from U.pdf detailed read.

U.pdf draws U14 as a stand-alone KÜÇÜK RF small rack at the left of the U
elevation, physically detached from the main U1-U13 run. Updated model
(post-flip coordinates — see §18):

- **Main run U1-U13:** (59.2, 37) → (36.72, 37), 13 bays, 7 levels.
  U8 keeps `position_offset: 1` (positions 2,3 not 1,2 — "U8 hariç, 1 yok").
- **U14 KÜÇÜK RF:** (33.5, 37) → (35.5, 37), 1 bay, 7 levels, `small_rack: true`.
  SAP shows odd positions {3, 5, 6} for U14 — flagged for May 20.
- **East end of main run** meets J's top arm at the CLOSED junction
  (~59.2, 37).
- Kit/RT sides: `TBD` until May 20.

## 8. Kardex

- Modeled as a single 4 m × 14 m zone at x = 0, y = 4.
- Treated as a black box — no per-pallet bins, just a fixed access cost.
- **TODO May 4:** how many Kardex units are present, and what is the average pick time?

## 9. Trolley staging

- 28 m × 4 m strip at x = 22, y = 0 (in front of kitting).
- No pickable positions — visual only.
- **TODO May 4:** confirm size and location.

## 10. Kitting area

- 12 m × 4 m strip at x = 8, y = 0 (front-center).
- Origin point for all order travel-distance calculations.
- **TODO May 4:** confirm location, size, and number of kit prep tables.

## 11. Fast-mover threshold

- ✅ **Confirmed May 4** (site visit): "İlk üç raf insanın ulaşabileceği raflar" — the lower 3
  levels (level < `fast_mover_max_level = 3`) are reachable from the kit corridor without
  a reach truck.
- Assumed uniform across all racks; visual evidence in May 4 photos consistent for a-g, J, U.

## 12. Dock doors

- 3 doors evenly spaced along the north wall.
- **TODO May 4:** count actual doors and record their x-positions.

## 13. Single-position-per-material

- Each material is assigned exactly one bin.
- Real warehouse: ~10 000 SKUs vs ~3 200 slots (team contact, Apr 15) — many SKUs share bins
  or have multiple bins. Not modeled.
- **Storage bin map RECEIVED May 4** (`data/Malzeme Girişleri_*.xlsx` → `özet`,
  `Storage Bin` column). Decoding bin codes (e.g., `BRH-10-02`) into rack/level/position
  is the next step.
- Decision pending: how to handle multi-bin materials in baseline policy. Likely treat
  the SAP Storage Bin as the "primary" location; ignore secondary placements for v1.

## 14. Order generation

- ✅ **May 4 decision: daily aggregate × uniform within shift.** The partner's SAP only
  records date (no hour:minute) for kit prep, so intra-day timing is uniform-by-default.
  Document this as a model limitation in the report.
- Demand per material: derive from `2026 Tüketim Adetleri` (annual) ÷ working days × shifts.
- Material weighting from `ABC Analizi` sheet — **partner's existing ABC + IEU's reclassification**
  both available; comparison is the project's analytical core.
- ✅ **Production line mapping RECEIVED May 4** (`mrpc` sheet) → milkrun routing can now
  be line-aware. Material → MRP-C in `özet`/`zppq16_copy`, MRP-C → line in `mrpc`.
- ✅ **BOM RECEIVED May 26 via ZWM92** (`data/zwm92/*.XLSX`, 9 family exports). The
  dispatch log itself is an as-dispatched BOM: each row records `(Order, KIT No,
  Bileşen Malzeme, Çıkılan Miktar)` and grouping by `(Order, KIT No)` reconstructs
  the full component list of each kit produced. 40,804 kit-orders are extracted in
  `src/zwm92.py:build_orders` and cached at `output/zwm92_orders.json`; per-kit BOM
  sizes are the empirical distribution feeding the Arena-style driver (§21).
  Caveats:
  - "BOM size" here = number of dispatched components, not engineering BOM levels;
    bulk-issue rows with `Çıkılan Miktar` in the thousands (e.g. fasteners) inflate
    the per-kit item count, so the empirical distribution is clipped at 50 items
    to keep the sim numerically stable (`src/zwm92.py:fit_distributions`).
  - Phantom assemblies are not exploded — every `Bileşen Malzeme` is treated as a
    leaf-level pick the warehouse actually fetches, which matches reality from
    the warehouse's perspective.
  - The per-line "kit content" lookup (`zwm92.kit_bom`) is also exposed but not
    yet wired into a kit-aware slotting policy — would be a natural next step
    for a "co-locate kit-mates" heuristic.

## 15. Routing (updated 2026-06-09 — corridor-aware rectilinear)

- Travel paths are **obstacle-avoiding rectilinear routes**
  (`Warehouse.route_between_points`): rack bodies are blockers, candidate
  paths snap to a grid of corridor "safe lines" (rack-edge ± clearance),
  and the shortest obstruction-free path wins. The Manhattan L-bend is a
  proven lower bound, so a clear L-path is returned immediately.
- Operator picks: greedy nearest-neighbor over ROUTED distances inside an
  order; multi-bin materials pick the routed-nearest bin at decision time.
- Reach trucks: depot → access-point routed travel, level-dependent lift,
  stochastic pick/place, and (2026-06-09) an explicit **return-to-depot
  leg** during which the truck remains busy/unavailable.
- Rack-face access points respect `kit_corridor_side` / `rt_aisle_side`;
  "TBD" sides conservatively allow both faces and emit a route-model WARN.
- Not modelled: one-way corridor flow direction; congestion between
  agents in the same aisle.

## 16. Timing parameters (`src/config.py`)

| Parameter | Value | Source |
|-----------|-------|--------|
| Operator walk speed | 50 m/min | PROJECT.md |
| Reach truck travel speed | 100 m/min | PROJECT.md |
| Reach truck lift time per level | 0.25 min | PROJECT.md |
| Reach truck pick/place time | 0.5 min | PROJECT.md |
| Operator pick time | 0.3 min | PROJECT.md |
| Milkrun cycle | 45 min, 9 tours/day | PROJECT.md |
| Shift length | 480 min (8 h) | PROJECT.md |
| Reach trucks | 7 | PROJECT.md |
| Operators | 8 | PROJECT.md |
| Milkrun trains | 7 | PROJECT.md |

**TODO May 4:** time-study these — especially RT lift time per level and operator
walking speed in a loaded warehouse.

## 17. Kit-corridor → production-line map (May 11, partial)

✅ **CAD image received May 11** (`WhatsApp Image 2026-05-11 at 11.25.39.jpeg`).
Each kit corridor is labelled with the production line it feeds:

- `KITTING (MCset-Aksesuar)`
- `KITTING (Blokset-Fasen)`
- `KITTING (SM6-Premset)`
- `KITTING (F400)`
- `KITTING (RI-P7 SD-POLE)`
- `KITTING (GAM)` (along J's vertical arm)

Putaway (RT) aisles are labelled `PUTAWAY` in between.

✅ **Wired into `config/layout.json`** as `production_lines[]` top-level array
plus per-segment `kit_corridor_line` where confident. Confident wires so far:

- **GAM** on J's main vertical (segment J2-J12). Side still `TBD` — the CAD
  shows it adjacent to J but the exact kit/RT side won't be settled until
  May 20.

The other 5 lines are documented in `production_lines[]` with
`"kit_corridor": "TBD May 20"`. Once confirmed, add a `kit_corridor_line`
field to the matching segment's `kit_corridor_side` and unlock **line-aware
milkrun routing** in `src/simulation.py` (each milkrun tour can target one
line's kit corridor by name, joining material → MRP-C → line → corridor).

## 18. CAD orientation — x-axis flipped on May 11

The May 11 CAD image places J at the **bottom-right** of the floor plan; our
pre-May-11 coords placed J at the far west. To bring the model into
alignment with the CAD (so report screenshots match without rotation), every
horizontal coordinate in `config/layout.json` is now mirrored around
x = building.width_m / 2 = 40.

Concrete changes:

- Every rack segment's `start[0]` and `end[0]`: `new_x = 80 - old_x`.
- Every `kit_corridor_side` / `rt_aisle_side`: `east <-> west`. North/south
  unchanged. `TBD` stays `TBD`.
- Kitting block: x went 8 → 60 (south-east corner now).
- Trolley staging: x went 22 → 30.
- Kardex: x went 0 → 76 (east wall now, was west wall).
- Closed junctions: J↔G at (59.2, 10); J↔U at (59.2, 37) — both moved from
  x=20.8 to x=59.2.

SAP bin codes are **NOT** affected — the `(rack, bay, position)` join in
`Warehouse.sap_position_id` ignores spatial coordinates. The simulation
produces the same KPIs (verified May 11) modulo the B7-physical-gap and J
re-segmentation which together drop the model from 3 137 to 3 110 positions.

## 19. Timing constants — F400-derived, extrapolated to all lines (May 26)

The May 20 site visit produced an F400 Kit video time-motion study
(`F400 Kit Cansu Nehir.xlsx`, 2,319 micro-events across 296.6 min of DJI
footage with CNVA/FNVA/NVA classification). Extractor at
`src/timing_study.py` parses the four sheets, classifies each row via Turkish
keyword regex, and writes `the time-study output`. The simulation
now uses these constants instead of the pre-visit placeholders:

| Constant | Old (placeholder) | New (the time-motion study) | Sample |
|----------|------------------:|-----------------:|-------:|
| `OPERATOR_PICK_TIME`         | 0.30 min | **0.113 min** | n=900 (rf_scan + manual_pick) |
| `MANUAL_PICK_TIME_PENALTY`   | 0.50 min | **0.102 min** | n=157 (walk_corridor) |
| `REACH_TRUCK_PICK_PLACE_TIME`| 0.50 min | **0.110 min** | n=69 (rt_pick) |
| `KARDEX_PICK_TIME`           | 0.50 min | **0.113 min** | mirrors operator pick |

These are *at-bin micro-event* times: the video captures only the seconds
the operator spends at the rack face (scan + grab + place), not the full
"travel-to-bin + scan + grab + walk-back" cycle that `OPERATOR_PICK_TIME`
used to represent. Walking is now modelled separately via
`OPERATOR_WALK_SPEED_M_PER_MIN`, so this decomposition is consistent.

**Sargent face-validity limitation:** F400 is the largest line (~48k of
167k ZWM92 dispatch rows) but only one of nine product families. We
extrapolate F400-measured constants to SM6, Okken, Premset, MCSET,
AKS_PAK, Çekmece, DMK, Sepam without per-line verification. The
sensitivity analysis (`src/sensitivity.py`) reports model sensitivity to
each of these constants so the extrapolation risk is bounded.

**2026-05-26 code-audit fixes:**

- **C2 (Excel unit safety net):** `src/timing_study.py::_time_to_seconds`
  treated raw numeric cells as fraction-of-day, but the F400 workbook
  cells are already `datetime.time` objects so the bug was effectively
  dead code. The conversion is now explicit and unit-correct for both
  paths. Numerical constants are unchanged.
- **H4 (`MANUAL_PICK_TIME_PENALTY` definition):** the constant is the
  `walk_corridor` mean from F400 — a conservative **UPPER-bound proxy**
  for the marginal time penalty of a fallback (manual) pick over a
  baseline (correct-slot) pick. The full corridor traversal overstates
  the incremental penalty by ~30% because the operator would walk part
  of the corridor anyway. Documented in `src/config.py` and called out
  here so the reader doesn't mistake the proxy for the true marginal
  cost.

## 20. Trace-driven order arrivals from ZWM92 (May 26 — superseded)

Initial design replayed the raw ZWM92 timestamps order-by-order
(`ZWM92TraceDriver`). Section §21 below documents the May 26 advisor
pivot to fitted distributions, which is what the codebase actually uses
now. The trace replay is still callable for ad-hoc comparison but is
no longer the default driver.

For historical record: the raw-trace driver loaded the cached ZWM92
dispatch log (`output/zwm92_orders.json`, 40,804 orders over
2026-01-02 → 2026-05-18, 9 families) and replayed orders in real
arrival sequence with inter-arrival times equal to the wall-clock
delta between consecutive `Sayim Tarihi + Sayim Zamani` timestamps,
capped at `MAX_TRACE_IAT_MIN = 60 min` so overnight / weekend gaps
didn't waste sim time. Same per-line kitting and material-master join
filter as the fitted driver.

> **SUPERSEDED NOTE (2026-06-09):** §21's same-seed N=1 design and the
> single-order Exponential arrival model are superseded by §24. The
> distribution-fitting approach itself (Arena-style) is unchanged.

## 21. Arena-style fitted distributions + same-seed runs (May 26 — superseded by §24)

Advisor's instruction was that the simulation should mirror Arena's
discrete-event paradigm: don't replay a single recorded trajectory,
fit parametric / empirical distributions to the historical log and
sample fresh on each replication. Combined with a fixed seed across
all replications (`SAME_SEED_FOR_ALL_REPS=True`, `RANDOM_SEED=42`),
every run produces an identical trajectory — which the advisor wanted
so that the experimental contrasts between policies are not confounded
by Monte-Carlo noise and so the run is fully reproducible from the
written report.

Implementation (`src/zwm92.py:fit_distributions`,
`src/simulation.py:ZWM92DistributionDriver`):

| Random quantity      | Distribution                  | Source data                  |
|----------------------|-------------------------------|------------------------------|
| Inter-arrival (min)  | ~~Exponential(mean=4.8)~~ → §24.1 batch-empirical | superseded 2026-06-09 |
| Items per order      | Empirical (clipped at 50)     | observed kit BOM sizes        |
| Production line      | Categorical(weights)          | line frequency in ZWM92       |
| Material per line    | Categorical(weights)          | per-line pick frequencies     |
| Operator pick time   | Lognormal(μ from §19, ~~σ=1.30~~ → 1.245, §24.3) | F400 pooled CV=1.93 |
| RT pick/place time   | Lognormal(~~σ=1.20~~ → 1.047, §24.3) | F400 rt_pick CV=1.41 |
| Manual-pick penalty  | Lognormal(~~σ=1.40~~ → 1.279, §24.3) | F400 walk_corridor CV=2.03 |
| Kardex pick + rotate | Lognormal(~~σ=1.30~~ → 1.245 / 0.30, §24.3) | mirrors operator + book val |

Means of the timing log-normals are preserved (μ = log(mean) −
0.5·σ²) so the expected pick time still matches the §19 deterministic
constants — only the variability is added. Item-count empirical
samples are clipped at 50 because a handful of SAP "Çıkılan Miktar"
entries are bulk-issue quantities (e.g. 134 012) that would crash the
sim if drawn.

**Statistical-test consequence:** with N_REPLICATIONS=1 and identical
seeds, between-rep variance is zero and the Sargent ANOVA / Tukey /
Welch comparisons collapse to a single trajectory each. The validation
plan therefore swaps in a paired-by-order Wilcoxon signed-rank test
(`src.analyze.paired_by_order`) that pairs every order against the
same order under the baseline policy. With ~440 orders per run, this
gives more inferential power than 5 independent reps of 440-order runs
would (paired design eliminates between-order variance entirely).

Validation against ZWM92 actuals still uses real per-rack dispatch
counts (`picks_per_rack_actual` from the loader), not the fit. The fit
is only used at run-time to drive the simulation; the goodness-of-fit
test in `src/validate.py` compares simulated vs. observed rack pick
shares directly.

**2026-05-26 code-audit fixes:**

- **H2 (IAT calendar mean):** `the dispatch summary` now reports
  two means side-by-side — `iat_within_shift_mean` (consecutive-order
  gaps under a 60-min cap, the within-shift cadence) and
  `iat_calendar_mean` (`(last_dt − first_dt) / (n_orders − 1)`, the
  long-run including overnight / weekend gaps). The driver continues
  to use the within-shift mean because the simulation models a single
  8-h shift; the calendar mean is exposed for traceability and
  long-horizon what-ifs. Numbers as of 2026-05-26: within-shift 5.36
  min, calendar 4.80 min.
- **H5 (distinct materials vs total picks):** ZWM92 build now stores
  both lists per kit-order — `distinct_materials` (unique material IDs
  in the kit) and `items` (qty-expanded picks). `n_items_empirical` in
  `fit_distributions` now uses *distinct* counts (mean 4.0 picks/kit),
  which matches the Arena-style "draw N distinct picks per order"
  semantics. Previously `items` (qty-expanded, mean 16.7) was being
  used and a qty=20 row was counted as 20 distinct materials. The
  summary JSON exposes both means so the report can quote either.
- **H1 (Kardex batch picking):** the simulation now holds the Kardex
  resource for a single carousel rotation per order regardless of
  Kardex pick count, then iterates pick times inside that hold. The
  old model paid one full carousel cycle per item, which roughly
  triples the Kardex service time when a kit has 3+ Kardex picks.
- **H6 (zero-pick orders):** if both rack and Kardex pick lists are
  empty for an order (no material has a slot and none is Kardex-
  routed), the order is now counted in `orders_with_no_locations` and
  not in `orders_completed`. Prior runs silently inflated the
  completion count with no-op orders, biasing throughput up by ~0.2%.
- **C3 (TravelDistance sort key):** `TravelDistancePolicy` now sorts
  by *real* per-material pick frequency from `picks_by_material`
  (cached in `the dispatch summary`) when available, falling back to
  the SAP `consumption` proxy only when the cache is missing. Result:
  Travel-distance no longer beats the heuristic on walk distance once
  the sort uses real picks rather than the consumption-weighted proxy
  — the previous "winner" was an artefact.
- **C1 (sensitivity baselines):** `src/sensitivity.py` now reads
  baselines from the live `config` module at import time and sweeps
  ±20% from each, rather than from a hardcoded table that went stale
  after the F400 timing study landed. `IAT_MEAN_MIN_OVERRIDE` is a
  new optional config knob the sweep uses to perturb the arrival
  rate (the runtime IAT mean) without regenerating the ZWM92 cache.
- **M4 (UNKNOWN line orders):** orders whose production line could
  not be resolved from the SAP plant code are now dropped at
  `build_orders` time and the count is reported as
  `orders_dropped_no_line`. The driver no longer needs to deal with
  `line=None` (it was using a noisy fallback).
- **H3 (Wilcoxon multiple-comparison correction):** `src/analyze.py`
  now applies Holm-Bonferroni across the family of paired-by-order
  Wilcoxon tests (3 metrics × (n_policies − 1) tests). Each entry
  carries `p_raw` and `p_holm`; the `significant_at_0.05` flag uses
  `p_holm`. With 12 tests, the prior raw-p reporting was overstating
  significance.
- **M3 (Cochran's rule guard):** the chi-square per-rack test now
  reports `cochran_warning` when any expected cell count is below 5.
  This is a face-validity caveat — the asymptotic distribution drifts
  for sparse cells. The 2026-05-26 run has no low cells (smallest
  expected cell ≈ 8.2).
- **M7 (Wilcoxon skip log):** when fewer than 30 paired orders are
  common between a policy and the baseline, the comparison is now
  logged to stdout instead of silently dropped.

## 22. Resource counts — verbal site report (May 2026)

`NUM_REACH_TRUCKS = 7`, `NUM_OPERATORS = 8`, `NUM_MILKRUN_TRAINS = 7`,
`NUM_KARDEX_UNITS = 4`. Source: verbal report from the May 20 site
visit, recorded in CLAUDE.md and confirmed in the the time-motion study footage
(7 distinct reach-truck driver IDs across 296.6 min). These are
treated as static for the headline run. Sensitivity sweeps the timing
constants but not the fleet sizes — a fleet-sweep is in the
`IMPROVEMENT_BACKLOG.md` future-work list.

## 23. Modelling limitations carried forward to V&V

The 2026-05-26 audit refactored several silent assumptions into
explicit, documented limitations. These remain in the model and are
disclosed in the V&V report's `Limitations` section:

1. **Kardex single-station collapse (M6) — RESOLVED 2026-06-09:**
   `config/layout.json` now carries an additive `kardex_stations` array
   (4 points spread along the Kardex zone); the operator walks to the
   routed-nearest unit. The shared capacity-4 `Resource` queue remains
   (one queue feeding 4 units), which matches the site's single pick-up
   window assumption.
2. **Zero-pick orders (H6):** counted separately from
   `orders_completed`. These are a model artefact (some order's
   materials have no decoded SAP bin and aren't Kardex-routed); the
   real warehouse never sees this case because every order has
   feasible picks. The counter is a face-validity instrument, not a
   throughput penalty.
3. **Holm-corrected significance (H3):** the report should always
   quote `p_holm`, not `p_raw`, for policy-vs-baseline contrasts to
   control family-wise error.
4. **Single-shift model:** ZWM92's 4-month log is compressed into a
   single synthetic 8-h shift. Multi-shift dynamics (warm-up after
   break, end-of-shift catch-up) are not modelled.
5. **Multi-bin partial placement:** if a material has 3 SAP bins, all
   3 are filled when free, but the simulation always picks from the
   nearest available. The other 2 bins effectively sit unused for
   that order — closer to real picking behaviour than a single-bin
   model, but the SAP "duplicate the inventory across bins" policy
   means the operator might in practice pick from a different bin on
   a different order. Not modelled.
6. **Travel-distance metric — RESOLVED (was "2D Euclidean"):** travel
   now uses obstacle-avoiding rectilinear routing along corridor safe
   lines (see §15). Remaining gap: one-way corridor flow directions and
   aisle congestion are still not modelled.
7. **Battery / charging for reach trucks:** not modelled. Over an 8-h
   shift each RT could realistically need 1–2 charge cycles.

---

## 24. 2026-06-09 fix pass — batch arrivals, replications, KPI completeness

Driven by the advisor's written acceptance criteria (≥20 replications,
4 KPIs, Minitab-ready export, hypothesis tests) and an internal audit.

### 24.1 Batch arrivals (replaces §21's single-order Exponential)

ZWM92 kit-orders are dispatched in bursts: among the 18,164 timestamped
orders (Okken, AKS_PAK, F400 — the other family exports lack the
time-of-day column), 3,885 same-timestamp batches exist with mean 4.68
kits/batch (median 2, max 79) and 99.9% of multi-kit batches are
single-line. The previously fitted Exp(5.36 min) IAT is therefore the
**inter-batch** gap; using it per order under-loaded the system ~4.5×
(sim ~87 orders/day vs real 40,804 / 103 active days ≈ 396/day),
which made waiting times identically zero and RT utilization ~4%.

New driver model (`ZWM92DistributionDriver.next_batch`):

| Random quantity | Distribution | Source |
|---|---|---|
| Inter-batch gap | Empirical (3,604 within-shift gaps; mean 5.36 min, CV 2.04) | timestamped subset |
| Batch size      | Empirical (3,885 runs; mean 4.68)                           | timestamped subset |
| Line            | Categorical, sampled ONCE per batch                          | all 40,804 orders  |
| Items per kit   | Empirical distinct-per-kit (unchanged, §21 H5)               | all orders         |

Empirical gaps are kept (CV 2.04 ≫ 1 rules out the Exponential).
Calibration identity: 480 / 5.36 × 4.68 ≈ 419 orders/day vs target 396
(+5.7%, inside the ±10% acceptance band) — `validate.py`
`daily_volume_check` enforces this every run. Limitation: batch sizes
are extrapolated from 3 families to all 8 lines, and batch size is
sampled independently of line (the marginal per-order line mix is
preserved exactly; the line↔size correlation is not).

### 24.2 Replication design (replaces §21's same-seed N=1)

`N_REPLICATIONS=20`, `SAME_SEED_FOR_ALL_REPS=False`, seed = 42 + rep.
The seed depends only on the rep index → **common random numbers**
across policies. Two independent RNG streams per run (`arrival_rng` =
seed, `service_rng` = seed + 1,000,003) keep the demand trajectory
IDENTICAL across policies within a replication — previously one shared
stream let a policy's extra service draws shift every later arrival,
silently breaking CRN (Heuristic saw 434 orders, SAP 467 at the same
seed). The model is **terminating**: each run is SIM_DAYS independent
480-min working days (matching ZWM92's 07:00–16:00 single-shift
dispatch profile), so no steady-state warm-up analysis is needed;
WARMUP/COOLDOWN (30 min each) trim edge effects.

Outputs: `output/kpi_by_replication.csv` (tidy, row = policy ×
replication, the Minitab import), `replications.json`,
`policy_stats.json` with per-policy mean ± 95% CI, ANOVA, Tukey HSD,
Welch, and a CRN **paired-by-replication t-test** vs the Heuristic
baseline (the Python twin of the team's Minitab test).

### 24.3 Timing σ correction

The lognormal log-σ values are now moment-matched from the measured
F400 CVs via σ = √ln(1+CV²): operator 1.245 (pooled rf_scan +
manual_pick, CV 1.93, n=900), RT 1.047 (CV 1.41), manual-penalty 1.279
(CV 2.03), Kardex 1.245 (mirrors operator). The previous values
(1.30/1.20/1.40) were set ad hoc and implied 1.3–1.9× the measured
CVs. Means are still preserved via μ = ln(m) − σ²/2.

### 24.4 RT return leg + resource semantics

After delivering a pallet the reach truck drives back to the depot as a
detached SimPy process that holds the RT resource until arrival — the
operator is blocked only until delivery, but a returning truck cannot
serve the next request. Previously the return leg did not exist (the
truck teleported), structurally under-counting RT busy time.

### 24.5 Per-line kitting + Kardex stations (additive layout keys)

`config/layout.json` gained ADDITIVE keys only (rack geometry
byte-identical, pallet canary 3203): `production_lines` kitting points
for F400 / SM6-36 / PREMSET / MCSET (76% of ZWM92 picks), derived from
the CAD kitting-cell labels via a codex→layout affine fit and snapped
to corridor safe lines; OKKEN/PIX/DMK/SEPAM still fall back to the
central kitting centroid (their CAD labels could not be confidently
matched — site visit). `kardex_stations` spreads the 4 carousels along
the Kardex zone; the operator walks to the routed-nearest unit.

### 24.6 KPI completeness + accounting

- `throughput_orders_per_hr` / `throughput_orders_per_day` (orders
  completed in the active window / window length).
- `avg_total_wait` = operator-queue + RT-queue wait (the advisor's
  "waiting time"); `avg_rt_queue_wait` is the explicit RT-only name.
- `kardex_utilization`; `orders_started` (arrivals; minus completions =
  cut-off in-flight orders, a survivorship telemetry under load).
- `summary()` is idempotent (the old util_overflow list accumulated on
  every recorder snapshot call).
- Utilization numerator AND denominator span the full run window while
  order KPIs use the active window — kept (2.5% effect) and disclosed.

### 24.7 Validation upgrades

- χ² low-expected cells are POOLED (standard Cochran remedy); both
  unpooled and pooled results are reported, the pooled one is headline.
- `daily_volume_check`: sim arrivals/day within ±10% of ZWM92's 396.
- `replication_ci_check`: 95% CI of throughput across the ≥20 reps,
  with arrivals/day compared to the ZWM92 actual.
- Honesty note added to the report: the χ²/t-test "expected" vectors
  derive from the SAME ZWM92 dataset the driver was fitted on — these
  are internal-consistency checks, not holdout validation. Independent
  evidence: the time-motion study timing, daily-volume calibration, face validity.
- "Baseline (Actual SAP)" fidelity is disclosed: 750 materials at true
  SAP rack bins, 2,872 Kardex-routed (policy-invariant), 2,319 via
  heuristic fallback — i.e. the baseline is a SAP+FMR hybrid, and the
  report must present it as such.

### 24.8a Forensics round (2026-06-10) — verified findings & decisions

Adversarially-verified multi-agent forensics (3 finders + 3 independent
re-derivers) on "why don't improvements improve / why does validation
reject":

1. **Restricted χ² scope fix.** The old restricted test compared sim
   picks of the 750 decoded materials against the rack distribution of
   ALL 4,036 ZWM92 materials. Scope-correcting the expected vector
   (decoded materials' own ZWM92 pick counts at their özet racks) drops
   χ² 174 → ~80, V 0.145 → ~0.10. The I/J/U "zero-cell" anomaly is
   explained: 97-100% of their decoded materials are DEAD STOCK (zero
   picks over the 4-month log), so the properly-scoped expectation
   there is ≈0. Implemented in `_expected_picks_by_rack_scoped`.
2. **Observed-bin placement idea REJECTED.** ZWM92 dispatch addresses
   are shared zone codes (≈1,375 unique slots for ≈3,914 materials,
   ~63% of slots multi-material) — not unique pallet positions; using
   them as placement source makes the per-rack shape WORSE.
3. **No multi-bin fairness gap.** Every policy assigns exactly 1
   position per material in the current data (decoded_bins carries one
   tuple per material); the SAP baseline has no structural slot-count
   advantage.
4. **Congestion mechanism (verified).** Cross-policy correlation of RT
   utilization with lead time is r≈0.998; operator-queue wait is 73-80%
   of lead time. Distance-only slotting (TravelDistance) optimizes
   routed distance to the CENTRAL kitting centroid while 77% of demand
   originates at per-line corridor points (+10.7 m weighted penalty),
   and `get_available_positions` ignores levels, so high-frequency
   materials land on RT-served positions: the operator then holds both
   the order and an RT, queueing cascades, lead time doubles. This is
   the thesis's central negative finding about naive slotting
   "improvements" — and the design rationale for the proposed
   `LineAwareSlottingPolicy` (line-origin distance + no-RT level
   preference + natural per-corridor load spreading).
5. **KDX fidelity gap is negligible for the sim.** 329 ZWM92-KDX
   materials are missing from the özet kardex set, but only 1 is in
   the active master (8 pick rows ≈ 0% volume). Disclosed, not coded.

### 24.7a Scope limitation — picking only, no replenishment (jury-critical)

The model simulates ORDER PICKING exclusively. Putaway and forward-slot
replenishment are out of scope: pallets never deplete, so no policy pays
a refill cost. This matters most for the proposed Line-aware policy,
which concentrates high-frequency materials at low (no-reach-truck)
levels — in reality those forward slots would need periodic
replenishment, and replenishment is reach-truck work the model does not
see. Defense framing: (a) the scope is IDENTICAL for all six policies,
so the comparison is internally fair; (b) the queueing mechanism that
sinks distance-only slotting (operator blocked on RT during picks) is
unaffected by replenishment scheduling, which can be shifted off-peak;
(c) the reported "RT util 1.1%" for Line-aware is therefore a
PICKING-ONLY figure, not total RT workload. Quantifying the
replenishment trade-off needs slot-capacity + depletion modelling —
listed as future work.

### 24.8 Naming honesty

`TRACE_DRIVEN=True` is historical naming: the driver SAMPLES fitted
distributions (Arena-style); it does not replay the trace. The thesis
text must say "distribution-driven (ZWM92-fitted)".

---

## 25. 2026-06-10 — Fable5 kör CAD yeniden-çıkarımı ve TAM GEÇİŞ

**Ne oldu:** Claude (Fable 5), repo'daki hiçbir layout dosyasına bakmadan
DWG + 11 raf PDF'i + 9 fabrika fotoğrafı + ZWM92×özet tüketim çapraz
tablosundan layout'u sıfırdan türetti (`output/fable5_layout/` — tüm kanıt
zinciri orada: `RAPOR.md`, `blind_assignment.json`, `comparison_report.json`,
`adversarial_verdicts.json`). Kullanıcı onayıyla ("tam geçiş", 2026-06-10)
`config/layout.json`'a uygulandı: `scripts/apply_fable5_layout.py`.
Geçiş öncesi yedek: `config/layout.json.bak_pre_fable5_20260610`.

**Kritik bulgu — repo iç çelişkisi:** sim'in layout.json'u v4 harf dizilimi
taşıyordu (A=güney, B/C sırt-sırta), viewer + rack_mapping v6 tam tersini.
Kör çıkarım hükmü: v6 büyük ölçüde doğru, ama **E↔F v6'da ters** (F400
tüketimi %75.8 E + F|FORKLIFT YOLU|E fotoğrafı + koridor etiketi); ayrıca
idx0=U14, idx1=J14, "phantom" idx14=**J13 KÜÇÜK RF** (PDF 182 cm ↔ CAD
ölçüsü 184.01). Hiçbir entity unmapped kalmadı.

**Yeni harf↔sıra eşlemesi (CAD güneyden kuzeye):** J-kolu(J12-J2), I, H
(sırt-sırta çift, 25-30 cm), G, E, F, D, C, B, A(kuzey); U = batı dikey kol
(U13-U2) + U14 GB stub + U1 100 cm kuzey kapağı; J = 5-seksiyonlu çevre
dirseği (J1=COL01, J13=X-elemanı, J14=GD stub, J15-J18=doğu kol).

**Sim'e etkisi:**
- SAP join DEĞİŞMEDİ: bay kodları, pallets_per_bay, bay_overrides,
  pallet_count aynen korundu (canary 3203 ✓; seviyesiz (raf,koy,poz)
  anahtar kümesi bire bir; 802 malzeme join'li).
- G seviyesi 9→8 (G KISA raf: zincir 546'da biter, 288=12×8×3 TAM) —
  modellenen pozisyon 3137→3101 (tam −36).
- E'nin kit yönü düzeltildi (eski dosyada kendi konvansiyonuna göre bile
  yanlıştı: kit=west ama F400 koridoru doğu yüzünde).
- H/I'nin bitişik kit koridoru YOK (iki 305 RT arasında sırt-sırta) →
  kit_corridor_side=TBD; davranış `ASSUME_KIT_ACCESS_WHEN_TBD`'ye bağlı.
- Ölçülmüş koridorlar (CAD DIMENSION'lardan): kit=200 (3 adet), RT=320
  (E-F forklift yolu)/300/305, batı 429, doğu 279.7.
- TÜM KPI'lar yeniden baseline'landı (bkz. output/policy_summary.json).

**Bilinçli yumuşak noktalar:** H/I yaprak sırası MEDIUM (H=kuzey yaprak,
v6 ile aynı); A/C/D/F/G/I koy etiketlerinin pusula yönü doğrulanamadı
(E1=doğu, B12=batı, J/U yönleri DOĞRULANDI); B7 söküm-sonrası boşluk CAD'de
kiriş olarak durur (sim'de B7 pozisyonları yaşamaya devam eder — SAP B-07
referansları kırılmasın diye bilinçli korundu); J/U segment pallet_count
bölüşümü tahminîdir (rack toplamları damgalarla bire bir).

---

## 26. Veri kullanım haritası (2026-06-10 — "her veri kullanılmış mı?" denetimi)

| Kaynak | Nerede kullanılıyor | Tez çıktısı |
|---|---|---|
| özet (SAP master, 5941 malzeme) | `data_loader.load_storage_bins/abc` — bin decode, ABC | Sim envanteri + RealBaseline join (802 bin) |
| zppq11 (76 gün tüketim) | ABC/Usage politikaları ağırlıkları | Politika karşılaştırması |
| ZWM92 (9 aile, 40 804 kit) | Driver dağılımları (IAT/batch/n_items/line/material); validation actuals; **hat×raf tüketim çapraz tablosu (yeni — layout harf doğrulaması)** | Driver + χ²/paired-t + layout kanıtı |
| the time-motion study etüdü (2 319 olay) | Timing sabitleri + lognormal CV'ler | Süreç süreleri |
| 11 raf PDF'i | **Fable5: damgalar (3203/137/306/1894), seviye zincirleri, per-bay profiller, ÖN/ARKA, KÜÇÜK RF'ler** | Layout + kapasite + V&V face validity |
| DWG (AutoCAD) | **Fable5: tam entity envanteri + ölçüler (koridorlar!) + portallar + satır analitiği** | Layout geometrisi |
| Fabrika fotoğrafları (9 yer) | **Fable5: harf plakaları (B/C, E/F, J/G), FORKLIFT YOLU, hat tabelaları** | Layout harf kanıtı + viewer paleti |
| hava.zip (9 yüksek çekim, 2026-06-10) | **Foto katalog workflow'u: palet/raf detay paleti + bağımsız çapraz-doğrulama** | Viewer gerçekçiliği + face validity |
| WhatsApp saha verisi (11 Mayıs) | bay_overrides (J12 cart, U8 offset, feeder koyları) | Pozisyon modeli |
| mrpc sheet | MRP controller → hat adı | Hat eşleme |
| Rack mapping/Codex geçmişi | v7'ye evrildi (Fable5 doğrulamasıyla) | Provenance zinciri |

Kullanılmayan veri yok; her kaynağın tezdeki rolü yukarıda izlenebilir.

---

## How to update after the May 4 visit

1. Open `config/layout.json`.
2. For each rack, update `segments[].start`, `segments[].end`, `segments[].compartments`,
   and the `rt_aisle_sides` / `kit_corridor_sides` arrays.
3. Re-run `python -m src.main` to see new KPIs and `python -m http.server 8000`
   then `web/index.html` for the updated 3D viz. No code changes required.
4. Update timing parameters in `src/config.py` as needed.
5. Strike through resolved TODOs in this file.
