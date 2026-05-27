# AGENTS.md — project memory for Codex sessions

Read me first. This file is the across-session memory; without it the model
loses every prior decision after a compaction. When something durable
changes, update the relevant section here.

---

## Project

FENG 498 senior project — SimPy discrete-event simulation of the Schneider
Electric Manisa medium-voltage switchgear warehouse. Compares 5 slotting
policies against a SAP-baseline placement on KPIs (walk distance, lead
time, RT/operator utilization). Real-world data: özet (SAP material master),
zppq11 (consumption), ZWM92 WM-dispatch log (4 months, 9 product families,
40 804 kit-orders incl. as-dispatched BOM), F400 video time-motion study
(2 319 micro-events), rack PDFs, AutoCAD floor-plan DWG.

## User

Deniz Ege Memetoğlu · denizegememetoglu@gmail.com
**Ignore** the `userEmail` context if it shows `aliozan242@...` — wrong.

---

## Status snapshot (2026-05-27 — Codex CAD APPLIED to layout.json, pipeline rerun done)

### Codex preview entegrasyonu (2026-05-27)

User Codex (başka bir AI) ile yan-yana 3D CAD preview üretti
(`/home/dege/se_manisa_ambar_3d_preview/index.html`) ve user-facing
directive: "dizayn layoutu doğru codexin yaptığı. ona entegre et her
şeyi". Codex'in 16 rack-row + 19 label verisi authoritative kabul edildi.

**Önemli topology keşfi**: Codex CAD'inde rack'ler EAST-WEST (horizontal,
codex_x = long axis); layout.json'da NORTH-SOUTH (vertical, layout_y =
long axis). Yani 90° rotation. Codex truth; layout sim-convention.

Bu session'da yapılanlar:

- `output/dwg_codex_geometry.json` — Codex'in 16 rack + 19 label + ÇÖP +
  column + flow-arrow verisi structured JSON olarak export edildi
  (authoritative CAD source for the project).
- `web/index.html` — **tamamen yeniden yazıldı** Codex'in Three.js
  CAD-fidelity rendering style'ı ile (uprights + beams 9 levels +
  cross-beams + pallets/cartons + KITTING/PUTAWAY floor zones +
  ÇÖP KOVASI 3D box + structural column + 7 incoming-flow arrows +
  floor labels + floating rack-letter sprites). Inline data fallback
  and `./dwg_codex_geometry.json` fetch. Iso / Top / Plan / Labels
  butonları. Eski sim viewer → `web/sim.html` taşındı (KPI viz için
  legacy).
- `web/dwg_codex_geometry.json` + `docs/dwg_codex_geometry.json` mirror.
- `docs/index.html` = Codex viewer mirror; `docs/sim.html` = eski sim
  viewer mirror.
- `config/rack_mapping_dwg_to_sap.json` **v4** — Codex idx → letter:
  idx 2=A, 3=B, 4=C, 5=D, 6=E, 7=F, 8=G, 9=I, 10=H, 11=U. J = idx 12
  (vertical leg) + idx 13 (south-arm stub) + idx 0 (south-arm fragment).
  V03/V04 candidate = idx 15. Axis-swap affine: slope=-0.010998,
  intercept=53.5270 (essentially identical to v3 — same DWG, different
  extractor). Max residual 1.6m at B; mean 0.73m.
- `config/layout_dwg_rebuilt.json` **regenerated from Codex coords**:
  - H/I bay-width 2.305 → 2.763/3.014m (CAD-true — H/I inflation
    question CLOSED, Codex agrees with libredwg's clustered width).
  - Most racks extend ~1.8m past y=37 (the U-line) in CAD — sketch
    underestimated north extent.
  - U and J preserved verbatim from layout.json (their layout
    orientation doesn't map cleanly via axis-swap; site visit needed).
  - **Pallet canary 3203 ✓** (SAP join intact).
- `config/layout.json` **APPLIED** (2026-05-27 PM, user direktifi
  "3dyi her şeyie implemente et"). Backup
  `config/layout.json.bak_pre_codex_apply` (pre-apply, 12.3 KB).
  Pallet canary 3203 ✓ post-apply. SAP join intact.
- Pipeline rerun done (Codex layout):
  - `python -m src.main` — 5 policies, KPI shift +1-5m walk vs prior:
    Heuristic 79.5m, Real SAP 80.5m, Usage 83.9m, Double 90.2m, Travel 84.5m.
  - `python -m src.validate` — χ² + paired-t; both reject as expected.
  - `python -m src.analyze` — Wilcoxon paired-by-order (N=1).
  - V&V Word report yeniden derlendi (~510 KB,
    `/home/dege/Downloads/feng498-final-VV-report.docx`).
  - `python -m src.sensitivity` — running in background.
  - `docs/layout.json` + `web/layout.json` mirrors refreshed.
- Backups: `rack_mapping_dwg_to_sap.json.bak_v3`,
  `layout_dwg_rebuilt.json.bak_v3_pre_codex`,
  `layout.json.bak_pre_codex_apply`.

### Open questions (Codex entegrasyonu sonrası)

- **idx 3+4 back-to-back pair (30cm gap)** — Codex shows B+C as
  physically adjacent. Layout has them 4.3m apart (kit corridor
  convention). Real geometry is 30cm. Site visit will resolve.
- **idx 6 (E rack) 14 vs 12 bays** — Codex caught 3 extra east-end
  posts (3880, 5417, 5560). Stamps not on PDF or PDF simplification?
- **idx 14** — isolated SE 1-bay post pair at x=5185, y=683. Phantom
  or real small column? UNMAPPED.
- **idx 15 (V03/V04)** — east-side 4-bay vertical. KÜÇÜK RF or
  unmapped small-parts shelf? UNMAPPED.
- **layout.json orientation (90° vs CAD)** — biggest open philosophical
  question. Layout.json has rack long-axis = N-S (vertical). CAD says
  long-axis = E-W (horizontal). Reconciling means full pipeline rerun
  and KPI baseline rewrite. Deferred — current sim still uses layout
  orientation, Codex viewer uses CAD orientation. Both coexist.

### Codex's diagnostic of "why Codex got stuck" (2026-05-27, FYI)

User shared Codex's analysis. 6 root causes:

1. "Simulation-accuracy mode lock-in" — every change framed as KPI
   risk vs face-validity gain.
2. `DO NOT TOUCH §1` made me preserve sim model even when CAD truth
   was clear.
3. Rebuilt JSON was generated but never applied to default viewer.
4. Old viewer renders "every level one box" — not CAD-fidelity.
5. DWG beam-counts unreliable for letter disambiguation.
6. "Looks the same" complaint never resolved with console-log check.

Codex's success approach: treat CAD geometry as primary deliverable,
not as sim-input. This session's integration adopts that frame.

### Driver — Arena-style fitted distributions (advisor pivot May 26)

- `ZWM92DistributionDriver` (`src/simulation.py:113`) fits 4 distributions
  from 167 784 real ZWM92 dispatch rows (40 804 kit-orders, 2026-01-02 →
  2026-05-18, 9 product families): IAT~Exp(5.36 min within-shift), n_items
  ~Empirical of distinct picks (mean 4.0, clipped at 50), line~Categorical,
  material~Categorical|line.
- Stochastic pick times: Operator/RT/manual/Kardex are Lognormal around
  the F400 means with σ from F400 video CVs (1.30, 1.20, 1.40, 1.30, 0.30).
- Synthetic Poisson `OrderGenerator` retained as silent fallback.
- `N_REPLICATIONS=1`, `SAME_SEED_FOR_ALL_REPS=True`, `RANDOM_SEED=42`
  (advisor — every rep is the same trajectory, fully reproducible).
- H5 fix (May 26 audit): `n_items_empirical` now samples DISTINCT
  materials per kit (mean 4.0), not qty-expanded picks (mean 16.7). The
  qty-expanded sample treated each unit as a distinct material and
  drastically over-sampled long orders.
- H2 fix: `zwm92_summary.json` now reports both
  `iat_within_shift_mean` (5.36 min, driver default) and
  `iat_calendar_mean` (4.80 min, includes overnight/weekend gaps).
- C1 fix: `IAT_MEAN_MIN_OVERRIDE` config knob lets the sensitivity
  sweep perturb the arrival rate at runtime.

### Timing constants (from F400 video study, May 26)

- `OPERATOR_PICK_TIME = 0.113 min`
- `MANUAL_PICK_TIME_PENALTY = 0.102 min` — H4: documented as
  conservative UPPER-bound proxy; full corridor traversal overstates
  the marginal penalty over baseline pick by ~30%.
- `REACH_TRUCK_PICK_PLACE_TIME = 0.110 min`
- `KARDEX_PICK_TIME = 0.113 min`, `KARDEX_CAROUSEL_TIME = 0.4 min`.
- H1 fix: Kardex now does single carousel + multi-pick inside one
  resource hold (was paying one full carousel cycle per item).
- F400 extrapolated to all 9 families — see ASSUMPTIONS.md §19.

### Resources (verbal report May 2026 — ASSUMPTIONS §22)

- `NUM_REACH_TRUCKS = 7`, `NUM_OPERATORS = 8`,
  `NUM_MILKRUN_TRAINS = 7`, `NUM_KARDEX_UNITS = 4`.

### BOM — RESOLVED via ZWM92 (May 26)
- ZWM92 itself is the as-dispatched BOM: each row carries
  `(Order, KIT No, Bileşen Malzeme, Çıkılan Miktar)` and grouping by
  `(Order, KIT No)` reconstructs every kit's full component list.
- 40 804 kit-orders cached in `output/zwm92_orders.json`; per-kit
  `distinct_materials` + qty-expanded `items` both persisted (H5).
- Per-kit BOM lookup exposed via `src.zwm92.kit_bom()` — not yet wired
  into a kit-aware slotting policy (top of IMPROVEMENT_BACKLOG).
- See ASSUMPTIONS.md §14 for caveats.

### Layout — DWG (May 26)
- `data/SE Manisa Ambar Rafları.dwg` (AC1032) → `/tmp/manisa.dxf` via
  `libredwg-git`'s `dwg2dxf`.
- `src/dwg_to_layout.py` extracts 12 rack rows on a 4 009×3 686 cm floor,
  6 KITTING + 6 PUTAWAY + 6 line labels. Output: `output/dwg_extracted.json`.
- **Read-only on purpose** — `config/layout.json` not overwritten so the
  SAP join (rack, bay, position) keys stay stable.
- M5 fix: `RackRow.bay_count` is a TRAVERS-beam proxy NOT a real bay
  count; do NOT use it to overwrite layout.json.

### Validation (`src/validate.py`)
- Expected vector uses ZWM92 actuals (`picks_per_rack_actual`); chi-square
  rejects (slotting policy can't reproduce SAP's exact bin assignment,
  expected — see ASSUMPTIONS §23).
- M3 fix: Cochran's rule guard (`cochran_warning` when any cell E<5).
  2026-05-26 run has no low cells.

### Policy comparison (`src/analyze.py`) — Holm-corrected
- ANOVA / Tukey / Welch collapse under N=1 same-seed runs (zero variance).
- **Paired-by-order Wilcoxon signed-rank** with Holm-Bonferroni
  correction across the 12-test family (3 metrics × 4 policies):
  - Baseline (Actual SAP) vs Heuristic: prep & lead -1.27 min,
    W=39026.5, **p_holm < 0.0001** (n=465).
  - Travel-distance Optimized: walk +6.26 m (p_holm=0.24, NS) —
    the previous "winner" was an artefact of the wrong sort key (C3).
  - Double ABC: walk +7.42 m (p_raw=0.04, **p_holm=0.37**, NS).
  - Usage-based ABC: no significant effect.
- H6 fix: zero-pick orders now in separate `orders_with_no_locations`
  counter, not silently rolled into `orders_completed`.
- H3 + M7: Holm correction applied; skipped policies logged to stdout.

### Headline KPIs from 2026-05-27 run (post-Codex-apply, 5 policies, N=1 each)

| Policy | Orders | Prep (min) | Lead (min) | Walk (m) | RT util |
|---|---:|---:|---:|---:|---:|
| Baseline (Heuristic) | 428 | 4.80 | 4.80 | 79.5 | 6.9% |
| Baseline (Actual SAP) | 437 | 3.12 | 3.12 | 80.5 | 2.3% |
| Usage-based ABC | 428 | 4.45 | 4.45 | 83.9 | 5.9% |
| Double ABC | 442 | 4.94 | 4.94 | 90.2 | 7.0% |
| Travel-distance | 442 | 4.43 | 4.43 | 84.5 | 6.0% |

Delta vs 2026-05-26 (pre-Codex): walk +1.5–5.0 m across policies,
prep +0.1–0.5 min, orders -20 (KPI shift expected with new geometry).

### Preprocessing stats (output/preprocess_stats.json)

- 5941 active materials · 3804 with bin · 781 with decoded rack/bay/pos · 2872 in Kardex
- 4349 bins total · 833 decoded · 3481 Kardex · 412 malformed · 386 multi-bin
- 3137 modelled pallet positions (vs 3203 PDF capacity)

---

## DO NOT TOUCH WITHOUT ASKING

1. **`config/layout.json` geometry** — Codex CAD geometry applied 2026-05-27
   with user explicit onayı ("3dyi her şeyie implemente et"). Backup at
   `config/layout.json.bak_pre_codex_apply`. Pallet canary 3203 ✓. Further
   geometry edits still need explicit approval.

   Önceki kayıt: commit `4df29b5` CAD x-axis flip + J/B/U rewrite ile
   broken edilmişti, "sıçmış, eski hali
   yakındı". Reverted to `70760c8` state on 2026-05-18. The CAD-flip work
   is **stashed** (`git stash list` → "WIP CAD-flip layout work pre-revert").
   `4df29b5` is still in git history — new commits supersede it. Don't
   re-apply the flip without explicit user request and CAD verification.
2. **`Warehouse.sap_position_id` join key** (src/warehouse.py:125) and
   **`RealBaselinePolicy.assign` join logic** (src/slotting.py:138) —
   joins by `(rack, bay, position)`. Bay codes and rack IDs in layout.json
   MUST stay stable. Coordinates can change, codes cannot.
3. **`whatsapp_export/`, `wa-logs.txt`** — untracked WhatsApp data, NOT for
   commit. Already in .gitignore patterns per `a6d8e45`.

---

## Files & roles

### Simulation core (src/)
- `config.py` — all tuneable knobs. Timing constants now F400-derived
  (§19); `N_REPLICATIONS=1`, `SAME_SEED_FOR_ALL_REPS=True`.
- `data_loader.py` — loads özet/zppq11, decodes SAP bin codes
  `BRA-02-02` → (rack, bay, position). `LAST_LOAD_META` exposes counts.
- `warehouse.py` — Warehouse class, position model, level bands,
  `can_pick_manually`, `reach_truck_travel_time`, `manual_pick_time`.
- `slotting.py` — 5 policies: Heuristic, RealBaseline (SAP), UsageBasedABC,
  DoubleABC, TravelDistance. RealBaseline is the validation ground truth.
- `simulation.py` — SimPy processes. Operators + RTs + Kardex resource.
  Multi-bin nearest-pick. Per-line kitting. Position locks. Shift breaks.
  Hosts `ZWM92DistributionDriver` (Arena-style order source).
- `zwm92.py` — loads ZWM92 dispatch logs, builds kit-orders + BOM, fits
  Exp/Empirical/Categorical distributions for the driver.
- `timing_study.py` — F400 video micro-event extractor → timing constants.
- `dwg_to_layout.py` — DWG → DXF → JSON face-validity extractor (read-only).
- `kpi.py` — OrderRecord with op_queue_wait + lead_time + prep_time.
  picks_by_rack + picks_by_material counters. CSV writers.
- `main.py` — runs N_REPLICATIONS per policy. Writes `replications.json` +
  `policy_summary.json` + per-policy CSVs.
- `validate.py` — chi-square (restricted + biased) + paired t-test against
  ZWM92 actuals (was SAP proxy). Writes `validation_report.{json,txt}`.
- `analyze.py` — paired-by-order Wilcoxon (+ legacy ANOVA path that
  collapses to n/a under N=1 same-seed). Writes `policy_stats.{json,txt}`.
- `sensitivity.py` — OAT tornado sweeps on timing constants.
- `visualize.py`, `animate.py` — matplotlib + mp4 outputs.

### Config / data
- `config/layout.json` — racks, kit corridors, kitting points, Kardex
  stations, production lines. Currently in 70760c8 state (pre-CAD-flip).
- `data/Malzeme Girişleri_010126-170326.xlsx` — özet + zppq11 (76 days).
- `data/zwm92/*.XLSX` — 9 SAP ZWM92 family exports (gitignored).
- `data/F400 Kit Cansu Nehir.xlsx` — F400 video time-study (gitignored).
- `data/SE Manisa Ambar Rafları.dwg` — AutoCAD source (gitignored).
- `data/rack-drawings/*.pdf` — per-rack pallet layouts (A,B,C,D,E,F,G,H,I,J,U).
- `ASSUMPTIONS.md` — narrative of every modelling assumption (§1 layout,
  §14 BOM, §19 timing, §20+§21 driver evolution).

### Scripts
- `scripts/build_vv_report.py` — Sargent V&V Word generator
  (→ `/home/dege/Downloads/feng498-final-VV-report.docx`).
- `scripts/build_flowchart.py` — simulation lifecycle PNG
  (→ `output/sim_flowchart.png`, Figure 2 in the report).

### Web viewer
- `web/index.html` — Three.js viewer. Mirror at `docs/index.html` for GH Pages.
- `docs/layout.json` — copy of config/layout.json for GH Pages.

---

## Deliverables produced this session (2026-05-26)

- `/home/dege/Downloads/feng498-final-VV-report.docx` — final Sargent V&V
  report (~510 KB): face-validity (DWG-extracted layout), conceptual model
  (Arena-style driver narrative + flowchart + pseudocode), data validity
  (ZWM92 4-month log), operational validity (chi-square + paired-t),
  paired-by-order Wilcoxon policy comparison, sensitivity, limitations.
- `output/sim_flowchart.png` — Figure 2 of the report.
- `output/dwg_extracted.json` — DWG face-validity reference.
- `output/zwm92_orders.json` / `zwm92_summary.json` — kit-BOM cache.
- `output/timing_study_f400.json` — F400 micro-event stats.
- `src/zwm92.py`, `src/timing_study.py`, `src/dwg_to_layout.py` — NEW.
- `scripts/build_vv_report.py`, `scripts/build_flowchart.py` — NEW.

---

## Pending / open

1. **Layout — DWG vs config/layout.json reconciliation.** DWG read-only
   extraction is done (`output/dwg_extracted.json`). Decision still
   needed before any geometric edit to `config/layout.json` (SAP join
   risk). Don't redo the flip blind — bring DWG diff + user approval.
2. **Kit-aware slotting policy** — natural next step now that BOM
   (`zwm92.kit_bom()`) is in hand. Would co-locate frequently co-picked
   materials. Not implemented yet. See `IMPROVEMENT_BACKLOG.md` item 1.
3. **Per-line time-motion studies** — F400 extrapolated to 8 other
   families; sensitivity sweep bounds the risk but per-line video would
   retire the limitation.
4. **Commits** — many uncommitted modifications (post-audit fixes).
   User to approve commit chunks.
5. **WhatsApp MCP log nuisance** — `wa-logs.txt` writes to CWD because
   `WHATSAPP_MCP_DATA_DIR` is unset. Permanent fix in `~/.Codex.json` is
   Deniz's call (sensitive global config).
6. **Code-audit fixes from 2026-05-26** — C1/C2/C3, H1–H7, M1/M3/M4/M5/M6/M7,
   L1/L8/L9 are all DONE (this session). M2 / L7 were already fixed earlier.
   Remaining low-severity items see `IMPROVEMENT_BACKLOG.md`.

---

## How to run

```bash
# Full pipeline
python -m src.zwm92             # refresh ZWM92 cache + fitted distributions
python -m src.timing_study      # refresh F400 timing JSON
python -m src.main              # 5 policies × N_REPLICATIONS=1, same seed
python -m src.validate          # χ² + paired t-test vs ZWM92 actuals
python -m src.analyze           # paired-by-order Wilcoxon
python -m src.sensitivity       # OAT tornados (slow — minutes)

# Layout face-validity (read-only)
dwg2dxf "data/SE Manisa Ambar Rafları.dwg" -o /tmp/manisa.dxf
python -m src.dwg_to_layout

# Final V&V report
python scripts/build_flowchart.py
python scripts/build_vv_report.py

# 3D viewer
python -m http.server 8000      # then http://localhost:8000/web/

# SAP join canary — must stay stable
python -c "import json; d=json.load(open('config/layout.json')); print(sum(s['pallet_count'] for r in d['racks'] for s in r['segments']))"
# → 3137
```

---

## Conventions

- User writes Turkish, expects Turkish replies. Brief, no fluff, no emojis.
- Don't ask for permission for read/edit. DO ask for git pushes,
  destructive ops, layout-geometry changes, sending external messages.
- Don't run extra "let me verify" reads after Edit/Write — harness errors
  on failure.
- Prefer Edit over Write for existing files.
- Commits only when user asks. Co-author tag: `Codex Opus 4.7
  <noreply@anthropic.com>`.
