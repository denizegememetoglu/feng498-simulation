# CLAUDE.md — project memory for Claude Code sessions

Read me first. This file is the across-session memory; without it the model
loses every prior decision after a compaction. When something durable
changes, update the relevant section here.

---

## Project

FENG 498 senior project — SimPy discrete-event simulation of the Schneider
Electric Manisa medium-voltage switchgear warehouse. Compares 5 slotting
policies against a SAP-baseline placement on KPIs (walk distance, lead
time, RT/operator utilization). Real-world data: özet (SAP material master),
zppq11 (consumption), rack PDFs, partner CAD floor-plan image.

## User

Deniz Ege Memetoğlu · denizegememetoglu@gmail.com
**Ignore** the `userEmail` context if it shows `aliozan242@...` — wrong.

---

## Status snapshot (2026-05-18)

### Validation (vs SAP, src/validate.py)
- Chi-square per-rack RESTRICTED: χ²=48.5, dof=10, **p<0.0001** — reject H0
- Chi-square per-rack ALL sim picks: χ²=13003 — biased, kept for context
- Paired t-test log(daily picks/material): t≈-83.6, **p<0.0001** — reject H0
- Gap is real and expected; closes with site-visit data (BOM, MB51, WMS).

### Policy comparison (src/analyze.py, N_REPLICATIONS=5)
- Walk distance/order: ANOVA p<0.0001, **Travel-distance Optimized wins** (61.06 vs Heuristic 75.67 m, Cohen's d≈-17.7)
- RT utilization: ANOVA p<0.0001, **Travel-distance Optimized wins** (18.7% vs 9.7%)
- Lead time / prep time / op-queue wait / op util / orders: ANOVA p > 0.89 — **no detectable policy effect** (operator queue saturated at 99.3%)
- Headline: slotting moves geometry, not throughput, until operator bottleneck is relieved.

### Preprocessing stats (output/preprocess_stats.json)
- 5941 active materials · 3804 with bin · 781 with decoded rack/bay/pos · 2872 in Kardex
- 4349 bins total · 833 decoded · 3481 Kardex · 412 malformed · 386 multi-bin
- 3110 modelled pallet positions (vs 3148 PDF capacity)

---

## DO NOT TOUCH WITHOUT ASKING

1. **`config/layout.json` geometry** — was broken by commit `4df29b5`
   (CAD x-axis flip + J/B/U geometry rewrite). User said "sıçmış, eski hali
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
- `config.py` — all tuneable knobs. Time constants on lines 25–42 are
  placeholder, replaced by May-20 time-study. `N_REPLICATIONS=5`.
- `data_loader.py` — loads özet/zppq11, decodes SAP bin codes
  `BRA-02-02` → (rack, bay, position). `LAST_LOAD_META` exposes counts.
- `warehouse.py` — Warehouse class, position model, level bands,
  `can_pick_manually`, `reach_truck_travel_time`, `manual_pick_time`.
- `slotting.py` — 5 policies: Heuristic, RealBaseline (SAP), UsageBasedABC,
  DoubleABC, TravelDistance. RealBaseline is the validation ground truth.
- `simulation.py` — SimPy processes. Operators + RTs + Kardex resource.
  Multi-bin nearest-pick. Per-line kitting. Position locks. Shift breaks.
- `kpi.py` — OrderRecord with op_queue_wait + lead_time + prep_time.
  picks_by_rack + picks_by_material counters. CSV writers.
- `main.py` — runs N_REPLICATIONS per policy. Writes `replications.json` +
  `policy_summary.json` + per-policy CSVs.
- `validate.py` — chi-square (restricted + biased) + paired t-test against
  SAP. Writes `validation_report.{json,txt}`.
- `analyze.py` — ANOVA + Tukey HSD + 95% CIs + Welch t + Cohen's d across
  replications. Writes `policy_stats.{json,txt}`.
- `visualize.py`, `animate.py` — matplotlib + mp4 outputs.

### Config / data
- `config/layout.json` — racks, kit corridors, kitting points, Kardex
  stations, production lines. Currently in 70760c8 state (pre-CAD-flip).
- `data/Malzeme Girişleri_010126-170326.xlsx` — özet + zppq11 (76 days).
- `data/rack-drawings/*.pdf` — per-rack pallet layouts (A,B,C,D,E,F,G,H,I,J,U).
- `ASSUMPTIONS.md` — narrative of every modelling assumption.

### Web viewer
- `web/index.html` — Three.js viewer. Mirror at `docs/index.html` for GH Pages.
- `docs/layout.json` — copy of config/layout.json for GH Pages.

---

## Deliverables produced this session (2026-05-18)

- `/home/dege/Downloads/site-visit-data-needs.md` — markdown checklist
- `/home/dege/Downloads/site-visit-data-needs.docx` — Word version with
  pre-filled "what we already know" (Bölüm 0) for the colleague going to Manisa
- `/home/dege/Downloads/feng498-V&V-plan.docx` — V&V report planning doc
  (Sargent framework, chi-square + ANOVA + sensitivity)
- `/home/dege/Downloads/feng498-policy-analysis.docx` — write-up of
  analyze.py results with per-KPI tables + Tukey + Welch + interpretation
- `src/analyze.py` — ANOVA / Tukey / CI / Welch / Cohen's d (NEW)
- `src/validate.py` — chi-square + paired t-test (NEW earlier)
- Generators (regenerate Word docs from data): `/tmp/build_vv_report.py`,
  `/tmp/build_site_visit_doc.py`, `/tmp/build_analysis_doc.py`

---

## Pending / open

1. **Layout** — user wants the layout closer to their drawn CAD example.
   Current state is `70760c8` (pre-flip). Need a careful pass that
   matches the CAD without breaking the SAP join. Don't redo the flip
   blind — bring CAD reference + user approval.
2. **N_REPLICATIONS bump** — 5 is the lower bound for ANOVA. 20–30 would
   tighten CIs (especially lead-time CV≈0.27). Not yet done; user wasn't
   asked.
3. **Sensitivity / tornado** — `src/sensitivity.py` mentioned in V&V plan,
   not yet implemented.
4. **Site visit (May 20)** — data needs list in Downloads/. Until then:
   timing constants placeholder, BOM missing, no real order timestamps.
5. **Many uncommitted changes** — `git status` shows 11 modified + 4
   untracked files. Risk if compaction loses context. Suggest user
   commit in sensible chunks before next big task.

---

## How to run

```bash
# Full pipeline
python -m src.main              # 5 reps × 5 policies → replications.json
python -m src.validate          # chi-square + t-test vs SAP
python -m src.analyze           # ANOVA + Tukey + CIs + Welch

# 3D viewer
python -m http.server 8000      # then http://localhost:8000/web/

# Regenerate Word docs (after data changes)
python /tmp/build_analysis_doc.py
python /tmp/build_site_visit_doc.py
python /tmp/build_vv_report.py
```

---

## Conventions

- User writes Turkish, expects Turkish replies. Brief, no fluff, no emojis.
- Don't ask for permission for read/edit. DO ask for git pushes,
  destructive ops, layout-geometry changes, sending external messages.
- Don't run extra "let me verify" reads after Edit/Write — harness errors
  on failure.
- Prefer Edit over Write for existing files.
- Commits only when user asks. Co-author tag: `Claude Opus 4.7
  <noreply@anthropic.com>`.
