# FENG 498 — Warehouse Layout Optimization via Discrete-Event Simulation

SimPy discrete-event simulation of the **Schneider Electric Manisa**
medium-voltage switchgear warehouse. The model compares six slotting
policies — including the partner's actual SAP placement and a proposed
congestion-aware policy — on the four advisor-mandated KPIs: **kitting
lead time, waiting time, reach-truck utilization, throughput**.

Built on four months of real operational data:

| Source | Content |
|---|---|
| SAP ZWM92 | 167,784 WM-dispatch rows → 40,804 kit-orders with as-dispatched BOM |
| SAP özet / zppq11 | material master (5,941 active materials) + consumption |
| F400 video time-motion study | 2,319 micro-events → stochastic pick-time distributions |
| AutoCAD floor plan + rack PDFs | rack geometry (3,137 modelled pallet positions, canary 3,203) |

## Headline results — N = 20 CRN replications × 6 policies

| Policy | Lead (min) | Wait (min) | RT util | Throughput (orders/day) | Walk (m) |
|---|---:|---:|---:|---:|---:|
| **Line-aware Slotting (proposed)** | **7.89 ± 0.50** | **5.02** | **1.2%** | 398.6 | 100.7 |
| Baseline (Actual SAP) | 14.08 ± 1.28 | 9.86 | 22.8% | 398.5 | **100.4** |
| Usage-based ABC | 14.76 ± 1.31 | 10.42 | 24.0% | 398.5 | 104.2 |
| Double ABC | 15.14 ± 1.34 | 10.75 | 25.6% | 398.4 | 103.3 |
| Baseline (Heuristic) | 15.39 ± 1.41 | 10.96 | 24.3% | 398.4 | 105.0 |
| Travel-distance Optimized | 26.86 ± 4.16 | 21.10 | 44.6% | 395.7 | 102.4 |

Lead ± column = 95% CI half-width (N=20). ANOVA p < 10⁻⁸ on
lead/wait/utilization; CRN paired-by-replication t-test: Line-aware
−7.49 min vs the Heuristic control (p = 4.1×10⁻¹²), −44% lead time vs
the actual SAP placement.

**Mechanism finding.** Under a realistically calibrated demand load
(simulated arrivals within **1.1%** of the real ~396 kit-orders/working
day), pure distance-optimized slotting *loses*: it stacks high-frequency
materials into reach-truck-served positions near the wrong origin, the
operator then holds both the order and a truck, and queueing doubles the
lead time (RT-utilization ↔ lead-time correlation **r ≈ 0.965** across
the six policy means). Travel-distance Optimized is also the only policy
that visibly saturates — 682 kits still in flight at run cut-off across
20 replications vs 284 for the SAP baseline, with RT utilization peaking
above 50%. The proposed **Line-aware Slotting** places each production
line's frequent materials at *no-reach-truck levels* nearest to *that
line's* kitting corridor, cutting picking RT dependence to ~1%.

**Robustness.** Under a 2× arrival-rate stress test
(`scripts/stress_test.py`, 3 seeds × 3 days): SAP placement degrades to
34.1 min lead (RT util 42.9%) while Line-aware holds at 13.5 min (RT
util 2.4%) — the advantage *grows* from 6.2 to 20.7 min, so the win is
not an artifact of the calibrated arrival rate. Disclosed limitations:
the slotting is optimized in-sample on the same 4-month demand history
(first/second-half Spearman ρ = 0.73 — the improvement is an upper
bound), and the model simulates **picking only** (forward-slot
replenishment is out of scope for all policies; the 1.2% figure is
picking RT workload, not total).

## Quickstart

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt \
    -r requirements-vv.txt

# Full pipeline (requires the gitignored SAP/ZWM92 source data)
python -m src.zwm92        # ZWM92 cache + fitted distributions
python -m src.main         # 6 policies × N=20 CRN replications
python -m src.analyze      # ANOVA / Tukey / Welch / CRN paired-t
python -m src.validate     # scoped chi-square + calibration gates
python -m src.sensitivity  # OAT tornado sweeps

# Quality gates
python -m pytest tests/ -q
python scripts/run_sanity.py     # Q1–Q10
python scripts/run_vv_suite.py   # Sargent V&V bundle → Reports/

# 3D viewer (native window; falls back to browser with --allow-browser-fallback)
./run-sim.sh                      # = python -m src.launcher
```

The committed `web/data`, `docs/data` and `web/timeline` mirrors contain
the latest run outputs, so **the 3D viewer and all dashboard panels work
from a fresh clone without the raw data**. A desktop launcher template is
at `scripts/schneider-simulation.desktop` (searchable as "Simulation").

## 3D viewer (`web/sim_v2.html`)

Three.js CAD-fidelity warehouse with timeline playback of recorded
simulation runs (schema 1.1 JSONL): per-policy operator/reach-truck
animation on a **zero-clipping world router** (agents provably never
pass through rack bodies — 0 crossings over 4,000 randomized routes and
1,459 real dispatches; reach trucks additionally avoid the west kitting
work-cell strip), pick highlights, KPI HUD, a real-warehouse photo dock
(local-only `web/photos/`), and an 11-tab analytics sidebar (policy
comparison with 95% CIs and hypothesis tests, validation, sensitivity
tornado, rack heatmap, arrival-driver evidence, F400 timing,
assignment-based re-slotting action plan, cost/ROI). Chart.js and
Three.js are vendored — fully offline.

## Statistical design

- **N = 20 independent replications**, seed = 42 + replication index —
  common random numbers across policies (between-policy lead-time
  correlation r ≈ 0.89 across replications), with a dedicated arrival
  RNG stream so every policy faces the identical demand trajectory
  within a replication. The CRN paired-by-replication t-test is the
  primary policy contrast; independent-sample Tukey is reported and is
  conservative by construction under CRN.
- **Batch arrivals**: inter-batch gap ~ Empirical (mean 5.36 min,
  CV 2.04) and batch size ~ Empirical (mean 4.68 kits), fitted from the
  18,164 timestamped ZWM92 orders; per-material demand weights use
  DISTINCT kit lines (one pick event per material per kit), matching the
  simulation's pick semantics. Replication-CI calibration gate: PASS at
  1.1% of the real daily volume.
- **Minitab-ready export**: `output/kpi_by_replication.csv`
  (row = policy × replication; mirrored under `web/data/`).
- **Validation** (Sargent framework): scope-corrected restricted
  chi-square (low-expected cells pooled, Cochran satisfied) with
  Cramér's V effect size reported alongside the p-value; per-material
  paired t-test on totals-equalized (shape) rates; daily-volume
  calibration; route-model face validation; reproducibility check.
  The chi-square/t-test expected vectors derive from the same ZWM92
  dataset the driver was fitted on — internal-consistency checks, not
  holdout validation (disclosed). V&V bundles under `Reports/`.

## Repository map

```
src/                  simulation core (SimPy), policies, KPIs, statistics
  simulation.py       processes + ZWM92 batch-arrival distribution driver
  slotting.py         6 policies (LineAwareSlottingPolicy = proposed)
  warehouse.py        position model + corridor-aware rectilinear router
  analyze.py          ANOVA/Tukey/Welch + CRN paired-by-replication t-test
  validate.py         scoped chi-square + calibration gates
scripts/              V&V suite, sanity gate, Word report builder, exporters,
                      stress test, desktop launcher template
web/  docs/           3D viewer + dashboards (docs/ = GitHub Pages mirror)
tests/                pytest suite
config/layout.json    rack geometry (SAP join canary: Σ pallet_count = 3203)
ASSUMPTIONS.md        every modelling assumption + §24 redesign narrative
docs/defense_notes.md anticipated jury questions with prepared answers
```

Raw SAP exports, the ZWM92 XLSX files, the F400 study, the AutoCAD DWG
and site photos are **not** in the repository (NDA'd partner data) —
the fitted caches and run outputs under `web/data` are.

---

*Deniz Ege Memetoğlu — FENG 498 senior project, advisor Dr. Oktay
Karabağ. Simulation date base: Jan–May 2026 ZWM92 window.*
