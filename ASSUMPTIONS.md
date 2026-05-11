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
| B  | linear | 12 | B1–B12 | 2.70 m (assumed) | 9 | 3 | **288** | ✅ B.pdf (36 missing positions) |
| C  | linear | 12 | C1–C12 | 2.70 m (assumed) | 9 | 3 | **297** | ✅ C.pdf (27 missing) |
| D  | linear | 12 | D1–D12 | 2.70 m (assumed) | 9 | 3 | **300** | ✅ D.pdf (24 missing) |
| E  | linear | 12 | E1–E12 | 2.70 m (assumed) | 9 | 3 | **294** | ✅ E.pdf (30 missing) |
| F  | linear | 12 | F1–F12 | 2.70 m (assumed) | 9 | 3 | **303** | ✅ F.pdf (21 missing) |
| G  | linear | 12 | G1–G12 | 2.70 m (assumed) | 9 | 3 | **288** | ✅ G.pdf (36 missing) |
| H  | linear (vert) | 11 | H1–H11 | 2.70 m (assumed) | **8** | 3 | **240** | ✅ H.pdf — heights 41/138/206/322/438/554/670/700 cm |
| I  | linear (vert) | 11 | I1–I11 | 2.70 m (assumed) | **8** | 3 | **252** | ✅ I.pdf |
| J  | polyline ("[") | **18** | J1–J18 | 2.70 m (assumed) | **8** | 3 | **381** | ✅ J.pdf — bottom 4 + vertical 10 + top 4 (84+213+84) |
| U  | linear (horiz) | **14** | U1–U14 | 2.70 m (assumed) | **7** | 3 | **263** | ✅ U.pdf — heights 118/222/346/455/564/676/700 cm + "KÜÇÜK RF" notes |

**Total: 3 203 pallets** (was estimated 3 564 / 3 000 in older notes).

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

## 6. J rack — polyline "[" bracket on the far west

✅ **Confirmed May 6** from user's top-down sketch.

- **Bottom arm:** (10.0, 10.0) → (20.8, 10.0), 4 bays J1–J4, 84 pallets.
- **Vertical:** (10.0, 10.0) → (10.0, 37.0), 10 bays J5–J14, 213 pallets.
- **Top arm:** (10.0, 37.0) → (20.8, 37.0), 4 bays J15–J18, 84 pallets.
- **Total: 18 bays × 8 levels = 381 pallets** (matches J.pdf stamp).
- **G ↔ J bottom-arm junction (~20.8, 10): CLOSED.** No traffic flow. Modelled as
  visual proximity only — operators and reach trucks cannot cross.
- **U ↔ J top-arm junction (~20.8, 37): CLOSED.** Same — visual only.
- ⚠ Per user instruction May 6 ("j'yi uzatıp da double yapma orayı"), do **not** extend
  J or duplicate it. The bracket has exactly 2 corners and stops at the closed
  junctions.
- Kit/RT sides on all 3 segments: `TBD` until May 20.

## 7. U rack — single horizontal at north end

✅ **Confirmed May 6** from user's top-down sketch.

- Single linear segment: (20.8, 37.0) → (58.6, 37.0), 14 bays U1–U14, 7 levels.
- 263 pallets (matches U.pdf stamp).
- West end meets J's top arm at the **CLOSED** junction (~20.8, 37).
- East end is open (no rack continues past A).
- Kit/RT sides: `TBD` until May 20.
- ⚠ Per user instruction May 6 ("bu layout dışında şeklin dışında çıkan başka raf
  YOK"), no rack extends past the drawn footprint — U is a single horizontal,
  not a polyline.

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
- `KITTING (GAM)` (on the west edge — runs along J's vertical arm)

Putaway (RT) aisles are labelled `PUTAWAY` in between.

⏳ **Not yet wired into `config/layout.json`.** The image orientation is
rotated relative to our (x, y) convention and the exact rack-to-corridor
assignment needs to be confirmed on May 20. Once confirmed, add a
`production_line` field to each segment's `kit_corridor_side`. This unlocks
**line-aware milkrun routing** in `src/simulation.py` (each milkrun tour can
target one line's kit corridor by name, joining material → MRP-C → line →
corridor).

---

## How to update after the May 4 visit

1. Open `config/layout.json`.
2. For each rack, update `segments[].start`, `segments[].end`, `segments[].compartments`,
   and the `rt_aisle_sides` / `kit_corridor_sides` arrays.
3. Re-run `python -m src.main` to see new KPIs and `python -m http.server 8000`
   then `web/index.html` for the updated 3D viz. No code changes required.
4. Update timing parameters in `src/config.py` as needed.
5. Strike through resolved TODOs in this file.
