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

**Total: 3 110 modelled positions** (3 203 raw PDF-stamp capacity; difference
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
- ⏳ **BOM still pending** — once received, can synthesize per-line kit content from
  production schedule × BOM.

## 15. Routing

- Operator picks: Manhattan distance + nearest-neighbor ordering inside an order.
- Reach-truck dispatch: nearest available RT to the pick location.
- **TODO May 4:** observe how operators actually route between picks — do they cluster
  by aisle, by zone, by line? The current model assumes pure NN, which may be wrong.

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

---

## How to update after the May 4 visit

1. Open `config/layout.json`.
2. For each rack, update `segments[].start`, `segments[].end`, `segments[].compartments`,
   and the `rt_aisle_sides` / `kit_corridor_sides` arrays.
3. Re-run `python -m src.main` to see new KPIs and `python -m http.server 8000`
   then `web/index.html` for the updated 3D viz. No code changes required.
4. Update timing parameters in `src/config.py` as needed.
5. Strike through resolved TODOs in this file.
