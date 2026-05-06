# FENG 498 - Warehouse Optimization

## Project Overview
- **Course:** FENG 498 Senior Project
- **Topic:** Data-driven warehouse layout optimization and simulation

## Report Structure
1. Abstract
2. Introduction (2.1 Problem Statement, 2.2 Motivation)
3. Literature Review (3.1 Routing Optimization, 3.2 Simulation-Based Analysis, 3.3 Layout Optimization, 3.4 AS/RS)
4. Methodology (4.1-4.5)
5. Results and Discussion
6. Conclusions (+ UN SDGs)
7. References
8. Appendix

**Format:** Times New Roman, 12pt, 1.5 spacing (0pt), tables captioned above, figures below.

---

## Warehouse Specifications

### Physical Layout (May 4, 2026 — verified from technical drawings in `data/rack-drawings/`)
- **Rack modules:** 11 — A, B, C, D, E, F, G (main rows), H, I (interior pair), J (polyline w/ hook), U (3-segment polyline)
- **Total capacity:** ~3,000 pallet positions (rack A: 297 confirmed; full count derivable from PDFs)
- **Pallet type:** P12 standard euro pallet (80 × 120 cm)
- **Rack A reference dimensions** (from `data/rack-drawings/A.pdf`):
  - 11 horizontal compartments (A2–A12), bay width **270 cm**
  - 9 vertical levels (level heights from floor: 41, 138, 206, 291, 370, 461, 540, 631, 700 cm)
  - 3 pallets per compartment per level → 11 × 9 × 3 = **297 pallets/rack** (was assumed 324)
  - Total height: **7.0 m** (was assumed 7.5 m)
  - Total length: ~29.7 m (was assumed 30 m — close)
  - 24 raf ayağı, 176 travers
- **Rack depth:** ~130 cm (P12 pallet)
- **Rack structure:** 9 levels confirmed; lower 3 levels human-reachable (Sümeyra, May 4)
- **Aisle width:** ~3 m (reach truck), kit corridor ~1.6 m — to be verified May 20
- **Access:** Single-sided standard, double-sided fast-mover (PROJECT spec)
- **MHE access constraints (May 4 site clarification):**
  - **Reach trucks operate ONLY between rack rows** (RT-only aisles)
  - **Milkrun trains DO NOT enter rack aisles** — they stay on main corridors and serve production lines
  - Operators (kit pickers) walk in kit corridors and reach lower 3 levels manually

### Storage Zones
| Zone | Description | Access |
|------|-------------|--------|
| Standard racks | Multi-level, high storage | Single-sided, reach truck |
| Fast mover racks | Ergonomic height, high-frequency items | Double-sided (front: reach truck replenishment, rear: operator picking via kit aisle) |
| Kardex units | Small goods automated storage | Automated |
| Trolleys area | Trolley staging | Tow truck |

### Material Flows
```
Euro Pallets → Kardex → IQC → ETP
Euro Pallets → Kardex → Skip-Lot → ETP
Euro Pallets → Racks → IQC → Reach Truck
Euro Pallets → Racks → Skip-Lot → Reach Truck
Euro Pallets → Urgent → (any of the above paths)
Trolleys → Tow Truck
Non-Euro Pallets → Racks → Reach Truck
Non-Euro Pallets (not suitable for racks) → Forklift
SM6-36 Frames → Waterspider
LV Boxes → Waterspider
Kitting → Waterspider
Trolley → Waterspider
Box/Card → Waterspider
```

### Material Handling Equipment (MHE)
| Type | Model | Count | Used In |
|------|-------|-------|---------|
| Forklift | EFG 220 | 2 | General handling |
| Forklift | EFG 430 | 1 | Heavy loads |
| Forklift | EFG 535k | 1 | Heavy loads |
| ETP | EJC 112 | 1 | Pallet transport |
| ETP | EJC 212 | 7 | Pallet transport |
| ETP | (general) | 5 | Pallet transport |
| ETP | EJC 216 | 5 | Pallet transport |
| ETP | EJE 120 | 5 | Pallet transport |
| Milkrun | EZG 130 | 8 | Production line replenishment |
| Reach Truck | ETV 216 | 5+1 | Rack operations |
| Tow Truck | EZS 010 | 1 | Trolley transport |

**Totals:** 7 reach trucks, 3 forklifts, 7 milkrun trains, 2 electric pallet trucks

### Operational Parameters
- **Milkrun cycle:** 45-minute fixed cycles
- **Tours per day:** 9
- **Buffer tolerance:** 20% margin per station
- **Kit preparation:** Job-based (order-based), should be daily-plan-based
- **Receiving process:** Materials enter → assigned to storage by stock levels & operational decisions
- **Storage logic:** High-frequency → fast mover racks (lower levels); Low-frequency → upper rack levels

---

## Key Problems to Solve
1. **Insufficient capacity:** Warehouse cannot meet storage demand, external facilities required
2. **Suboptimal space utilization:** Layout doesn't maximize available space
3. **Inaccurate ABC/FMR classification:** Current tool treats all materials as single homogeneous group, ignoring product complexity across production lines
4. **Scattered kitting materials:** Materials for single kitting order stored in multiple locations
5. **Bottleneck in kit corridor:** Manual operators wait for reach truck in 3m aisles
6. **Traffic congestion:** Multiple milkrun vehicles conflict in main corridors, threatening 45-min cycle stability
7. **No dynamic decision-making tools**

## Project Approach
1. **Refined ABC analysis** (value-based) — reclassify materials considering production line differences
2. **FMR analysis** (frequency-based) — identify true fast/medium/rare movers
3. **Optimized slotting** — position high-frequency materials in ergonomic, lower-level locations
4. **Simulation model** — validate proposed changes with discrete-event simulation
5. **Layout redesign** — data-driven warehouse layout optimization
6. **Goal:** No additional resource investment, purely system design improvement

---

## Dataset: Malzeme Girişleri (01.01.2026 - 17.03.2026)

**File:** `data/Malzeme Girişleri_010126-170326.xlsx` (May 4, 2026 expanded version)
**Previous version:** `data/Malzeme Girişleri_010126-170326.v1-2026-04-25.xlsx.bak`

**Sheets added in May 4 version:** `özet` (storage bin map), `mrpc` (MRP-C → line mapping), `zmm400` (material master with Storage Bin), `br unique`, several aggregation sheets.

### Sheet Descriptions

#### 1. Ana Veri (11,281 rows)
All material entry records. Single column: Material code.

#### 2. Unique (8,678 rows)
Unique material codes (pivot from Ana Veri).

#### 3. Veri (8,674 rows, 8 columns)
ABC-FMR analysis results per material.
| Column | Description |
|--------|-------------|
| Row Labels | Material code |
| ABC-FMR Analizi (SE) | The partner's existing ABC-FMR classification (from SAP) |
| 2026 Tüketim Adetleri | 2026 consumption quantity |
| ABC (İEÜ) | Team's ABC classification |
| Pareto | Cumulative Pareto percentage |
| ABC | ABC category (A/B/C) |
| Toplam Tüketim Adedi | Total consumption count |

#### 4. ABC Analizi (6,011 rows, 8 columns)
Detailed ABC analysis with Pareto cumulative values and comparison.
| Column | Description |
|--------|-------------|
| ABC-FMR Analizi (SE) | Partner's existing classification |
| 2026 Tüketim Adetleri | Consumption quantity (sorted descending) |
| ABC (İEÜ) | Team's classification |
| Pareto | Cumulative Pareto % |
| ABC | ABC class |
| ABC (SE) | Partner's existing ABC class |
| ABC Karşılaştırma | Match flag (0=mismatch, 1=match) |

**Top materials by consumption:**
| Material | Consumption | SE Class | Note |
|----------|------------|----------|------|
| HUA11397 | 1,158,440 | BF | Top consumer, classified B by partner but A by volume |
| HUA12053 | 711,610 | BF | |
| HUA11450 | 537,832 | BF | |
| 21130006 | 208,694 | CR | |
| 56950190 | 154,200 | CF | |

**Total consumption:** ~11,245,715 units

#### 5. ABC İndika (19 rows)
ABC-FMR indicator definitions:
| Code | Meaning |
|------|---------|
| A | Significant Material |
| B | Medium Significance Material |
| C | Low Significance Material |
| F | Fast mover |
| M | Medium mover |
| R | Rare/slow mover |
| D | Dead stock |

**Combined categories:** AF, AM, AR, BF, BM, BR, CF, CM, CR, AD, BD, CD

#### 6. zppq16_copy (10,452 rows, 6 columns)
SAP material master data:
| Column | Description |
|--------|-------------|
| Material | Material code |
| Plant | TR01 or TR04 (Turkey facilities) |
| ABC Indicator | SAP ABC indicator (1-9) |
| Purchasing Group | e.g., S02, S07, S11, S13, S17, S24 |
| MRP Controller | e.g., 199, 300, 418, 563, 963, 964, 965 |
| Material Description | Human-readable description |

#### 7. zppq11 (6,356 rows, 5 columns)
Material-level total consumption summary. `Material | Description | Plnt | material-plant | TOTAL`.

#### 8. özet (10,458 rows, 9 columns) — STORAGE BIN MAP ⭐
**This is the critical "Lagerort" / current placement data we requested.**
| Column | Description |
|--------|-------------|
| Material | Material code |
| Plant | TR04 |
| MRP Controller | numeric code (joins to `mrpc` sheet) |
| MRP Controller Tanımı | line description (e.g., P7M TRAFO CT) |
| ABC Indicator | SAP indicator (1-9) |
| Storage Bin | **e.g., `BRH-10-02`** — bin convention seems `<RACK><LEVEL>-<COMPARTMENT>-<POSITION>` |
| ABC Indicator tanımı | ABCFMR class (CR, BF, etc.) |
| 2026 tüketim | 2026 consumption count |

#### 9. mrpc (564 rows, 4 columns) — MRP CONTROLLER → LINE MAPPING ⭐
**The "MRP-C → production line" lookup we requested (Nehir's outstanding ask since March).**
| Column | Description |
|--------|-------------|
| Plant | tr01/tr04 |
| MRP-C | numeric code |
| plant-mrpc | composite key |
| Açıklama | line name (e.g., "SM6-36 IG-Import", "SM6-36 OG-Import", "SM6-36 Local", "SM6-36 SET Amblaj") |

#### 10. zmm400 (10,645 rows, 6 columns) — MATERIAL MASTER w/ Storage Bin
SAP zmm400 export. `Material | Description | Plant | Storage Loc. | (concat) | Storage Bin`.

#### 11. br unique (875 rows) — Unique Storage Bin codes
List of distinct bin labels actually used.

#### 12. ABC Analizi (6,011 rows)
**Includes the partner's existing ABC alongside the IEU team's reclassification** — this is the basis for the project's "Refined ABC" comparison.

---

## Key Data Insights
- **~8,674 unique materials** actively managed
- **ABC-FMR mismatch detected:** the partner's SAP classifies top consumers (HUA11397, HUA12053, HUA11450) as "B" (medium significance) while volume-based analysis puts them as "A" — this is the core analytical problem the project addresses
- **Plant codes:** TR01, TR04 — Turkey manufacturing facilities
- **SAP ABC indicators (1-9)** need mapping to standard A/B/C categories
- The comparison column in ABC Analizi shows significant mismatches (mostly 0), validating the project's hypothesis that the partner's classification is inaccurate

---

## Literature References
1. Koç et al. (2016) - VRP with simultaneous pickup and delivery. European Journal of OR, 257(3), 801-817.
2. Negahban & Smith (2014) - DES in manufacturing systems. Journal of Manufacturing Systems, 33(2), 241-261.
3. Ardiansyah et al. (2024) - Warehouse layout + DES with Double ABC Analysis. Procedia Computer Science, 234, 1753-1760.
4. Roodbergen & Vis (2009) - AS/RS survey.

---

## Files in This Repo
```
feng498-simulation/
├── PROJECT.md                                     # This file - complete project knowledge base
├── ASSUMPTIONS.md                                 # Modeling assumptions w/ TODOs
├── data/
│   └── Malzeme Girişleri_010126-170326.xlsx                     # SAP export — ABC, storage bin, MRP-C (May 4 expanded)
├── docs/
│   ├── SONPROPOSAL.docx                       # Latest project proposal (final version)
│   └── Warehouse Layout.pdf                   # Warehouse layout (2D, 3D, MHE table, rack system)
├── src/                                       # Simulation code
└── web/                                       # Three.js 3D visualization
```

---

## May 4, 2026 — Site Visit Outcomes

Team visited the partner facility in Turkey. Deniz Ege did **not** attend (was in different city); team = Nehir Konya Ekon, Sümeyra IEU, Deniz Etensel Ekon. Coordinated remotely via WhatsApp `Feng498` group.

### Data received (in `data/` and `docs/`)

| Asked for | Status | Where |
|-----------|--------|-------|
| ⭐ Storage bin map (Lagerort) | ✅ **RECEIVED** | `data/Malzeme Girişleri_*.xlsx` → `özet` and `zmm400` sheets |
| ⭐ MRP-C → production line mapping (`MARC-DISPO`) | ✅ **RECEIVED** (long-pending since March) | `data/Malzeme Girişleri_*.xlsx` → `mrpc` sheet |
| Partner's existing ABC-FMR classification | ✅ **RECEIVED** | `data/Malzeme Girişleri_*.xlsx` → `ABC Analizi` sheet |
| 2026 consumption volumes per material | ✅ **RECEIVED** | same file, multiple sheets |
| Rack technical drawings (all 11 racks) | ✅ **RECEIVED** | `data/rack-drawings/*.pdf` |
| BOM (Bill of Materials) | ⏳ Promised by partner contact, not delivered yet | — |
| Daily/transactional production history (intra-day timestamps) | ❌ Not available — only date-level, no time. **Decision: use uniform within-day distribution.** | — |
| Time study (walk speed, RT lift, pick time) | 📅 May 20 site visit (kronometreyle, 10-20 örnek) | — |
| Operator pick routing observations | 📅 May 20 | — |
| Building footprint, door/dock layout | 📅 May 20 (mostly verifiable from Warehouse Layout.pdf) | — |

### Operational rules clarified May 4

1. **Lower 3 rack levels are human-reachable** without reach truck (`fast_mover_max_level = 3` confirmed).
2. **Reach trucks enter every aisle EXCEPT 2 m kit corridors** (Sümeyra: "Rt genisligi iki metre olan koridorlar haricindekilere giriyo"). Alternating RT / kit pattern between a-g rows is confirmed ("birer birer atlıyodu"). Kit corridor width revised 1.6 m → **2.0 m**.
3. **Milkrun trains DO NOT enter rack aisles** — they stay on main corridors and serve production lines. This affects how milkrun routing is modeled (line-side, not rack-side).
4. **Kits are NOT ordered as fixed recipes** — every kit is custom, contents derived from production order × BOM. Hence **BOM + production schedule = synthetic kit log** is the modeling path forward.
5. **Order/kit timestamps are date-only** in SAP (no hour:minute). Modeling decision: aggregate to daily demand, distribute uniformly within shift, note as limitation.
6. **Storage bin convention** (from `özet` sheet): codes like `BRH-10-02`, `BRA-02-02` — appears to be `<rack-letter><area>-<level>-<position>` style. Need to confirm decoding May 20.

### Open data gaps (still needed)

1. **BOM** — partner contact's pending deliverable. With BOM + 2026 consumption (already have) we can synthesize per-line material demand without intra-day timestamps.
2. **Time study constants** — `src/config.py` parameters (walk speed 50 m/min, RT lift 0.25 min/level, etc.) are all PROJECT.md guesses.
3. **Aisle assignment** (which specific aisles are RT-only vs operator-only) — partially known from photos, needs walk-through.
4. **Multi-bin per material policy** — ~10,000 SKUs vs ~3,200 slots (Nehir, Apr 15) means some materials share bins or have multiple. Not modeled; decision pending.
5. **U rack technical drawing** — got `U.pdf` but no site-plan PDF showing kit area / Kardex / dock-door positions relative to racks.

### Modeling implications (translate visit findings to code)

- `simulation.py` order generator: replace synthetic 300/day with `daily_demand[material] = consumption_2026[material] / 365 * working_days_per_year`, then sample uniformly across shift hours.
- `warehouse.py`: add `RT_only_aisles` / `operator_only_aisles` flags per aisle once May 20 walk-through done.
- Milkrun routing: line-side only; do NOT path through rack aisles.
- Storage placement (baseline policy): join `özet.Storage Bin` to rack/level/position via decoded bin code → reproduces the partner's current layout.
