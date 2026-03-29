# FENG 498 - Schneider Electric Warehouse Optimization

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

### Physical Layout
- **Rack modules:** 11
- **Total capacity:** ~3,000 pallet positions
- **Pallet type:** P12 standard euro pallet (80 x 120 cm)
- **Rack dimensions:** width ~30m, depth ~130cm, height ~7.5m
- **Rack structure:** 8-9 rows (vertical/levels), 12 compartments (horizontal) per module
- **Compartment:** fits 3 euro pallets width-wise
- **Aisle width:** ~3m (reach truck operation)
- **Kit corridor:** 1.6m wide
- **Access:** Most racks single-sided; fast mover racks are double-sided

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

**File:** `data/Malzeme Girişleri_010126-170326.xlsx`

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
| ABC-FMR Analizi (SE) | Schneider Electric's own ABC-FMR classification |
| 2026 Tüketim Adetleri | 2026 consumption quantity |
| ABC (İEÜ) | Team's ABC classification |
| Pareto | Cumulative Pareto percentage |
| ABC | ABC category (A/B/C) |
| Toplam Tüketim Adedi | Total consumption count |

#### 4. ABC Analizi (6,011 rows, 8 columns)
Detailed ABC analysis with Pareto cumulative values and comparison.
| Column | Description |
|--------|-------------|
| ABC-FMR Analizi (SE) | Schneider's classification |
| 2026 Tüketim Adetleri | Consumption quantity (sorted descending) |
| ABC (İEÜ) | Team's classification |
| Pareto | Cumulative Pareto % |
| ABC | ABC class |
| ABC (SE) | Schneider's ABC class |
| ABC Karşılaştırma | Match flag (0=mismatch, 1=match) |

**Top materials by consumption:**
| Material | Consumption | SE Class | Note |
|----------|------------|----------|------|
| HUA11397 | 1,158,440 | BF | Top consumer, classified B by SE but A by volume |
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
| Plant | TR01 or TR04 (Schneider Turkey) |
| ABC Indicator | SAP ABC indicator (1-9) |
| Purchasing Group | e.g., S02, S07, S11, S13, S17, S24 |
| MRP Controller | e.g., 199, 300, 418, 563, 963, 964, 965 |
| Material Description | Human-readable description |

#### 7. zppq11 (6,022 rows, 2 columns)
Material-level total consumption summary.

---

## Key Data Insights
- **~8,674 unique materials** actively managed
- **ABC-FMR mismatch detected:** Schneider classifies top consumers (HUA11397, HUA12053, HUA11450) as "B" (medium significance) while volume-based analysis puts them as "A" — this is the core analytical problem the project addresses
- **Plant codes:** TR01, TR04 — Schneider Electric Turkey manufacturing facilities
- **SAP ABC indicators (1-9)** need mapping to standard A/B/C categories
- The comparison column in ABC Analizi shows significant mismatches (mostly 0), validating the project's hypothesis that SE's classification is inaccurate

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
├── PROJECT.md                          # This file - complete project knowledge base
├── data/
│   └── Malzeme Girişleri_010126-170326.xlsx  # Schneider Electric material entry dataset
├── docs/
│   ├── SONPROPOSAL.docx                       # Latest project proposal (final version)
│   └── Warehouse Layout.pdf                   # Warehouse layout (2D, 3D, MHE table, rack system)
└── src/                                       # Simulation code (to be developed)
```
