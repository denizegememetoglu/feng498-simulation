# IMPROVEMENT_BACKLOG.md

Honest assessment of model limitations and follow-up work, captured for
the next sessions. Compiled 2026-05-26 from the code-audit plan §9.

The point of this file is not to apologise for the model — it is a real
defensible simulation against four months of real SAP data — but to keep
a written record of every "we know, but it's out of scope right now"
decision so reviewers don't catch us off-guard and we don't lose track.

Sorted into four buckets:

1. **Structural** — known limitations that cannot be removed without
   re-scoping the project (advisor pivot decisions; data limitations).
2. **Modelling** — concrete improvements we could implement in a future
   session.
3. **V&V report gaps** — places where the Sargent write-up should be
   sharper.
4. **Repo hygiene** — process/infra items.

---

## 1. Structural limitations

These are baked in by advisor decisions or data scope. They should be
acknowledged in the report's Limitations section but not "fixed" — fixing
them changes the scope of the project.

### 1.1 N=1 same-seed → statistical power = 0

`N_REPLICATIONS=1`, `SAME_SEED_FOR_ALL_REPS=True` by advisor instruction
(reproducibility-first Arena pivot). Wilcoxon paired-by-order is the only
defensible inferential test. ANOVA / Tukey / Welch are mathematically
undefined (zero between-rep variance). A reviewer asking "where is the
Monte Carlo variance estimate?" gets the answer "advisor-mandated
reproducibility". Fix: add N≥10 different-seed runs (a `MULTI_SEED_MODE`
flag plus a 30-minute pipeline tweak), but only after advisor sign-off.

### 1.2 χ² never gives p > 0.05 (structural)

The simulation's slotting policy is architecturally unable to reproduce
SAP's exact bin assignment without re-implementing SAP's placement
rules. The chi-square test is therefore a face-validity *distribution-
shape* indicator, not a pass/fail success criterion. The V&V report
should state explicitly: "χ² rejection is expected behaviour; the
distribution correlation (Spearman) is the more informative face-validity
metric."

### 1.3 F400 → 9-family extrapolation (largest data limitation)

F400 is one of nine product families. The video study (2,319 events,
296.6 min) covers F400 only. The ±20% OAT sensitivity sweep bounds the
extrapolation risk for the headline KPIs, but a reviewer is right to
ask "why no video for the other 8 lines?" Fix: per-line video on
future site visits.

### 1.4 `config/layout.json` CAD-synced (Codex integration applied 2026-05-27)

**2026-05-27 güncelleme — APPLY EDİLDİ:** Codex (başka AI) `/home/dege/se_manisa_ambar_3d_preview/`
altında CAD-fidelity 3D preview üretti (16 rack, 19 label, ÇÖP KOVASI,
structural column, flow-arrows). User direktifi: "dizayn layoutu doğru
codexin yaptığı. ona entegre et her şeyi." Tam entegrasyon yapıldı:

- `output/dwg_codex_geometry.json` — Codex 16 rack-row + 19 label +
  special objects structured JSON.
- `web/index.html` **yeniden yazıldı** (Codex Three.js CAD-fidelity:
  uprights, 9-level beams, cross-beams, pallets, KITTING/PUTAWAY floor
  zones, ÇÖP KOVASI 3D box, structural column, 7 flow arrows, floor
  labels, floating rack letters). Eski sim viewer → `web/sim.html`.
- `config/rack_mapping_dwg_to_sap.json` **v4** (Codex idx 2..10 = A,B,C,
  D,E,F,G,I,H; idx 11 = U; idx 12+13+0 = J bracket; idx 1,14,15 UNMAPPED).
- `config/layout_dwg_rebuilt.json` Codex koord + axis-swap'lı rebuild,
  pallet canary 3203 ✓.
- **`config/layout.json` APPLY EDİLDİ** (`cp layout_dwg_rebuilt.json
  layout.json`, backup `.bak_pre_codex_apply`). Pallet canary 3203 ✓.
- Pipeline rerun done: `main` (5 policies, KPI shift +1-5m walk),
  `validate`, `analyze`, V&V Word report yeniden derlendi.

Açık alt-öğeler (Codex sonrası):

- **idx 3+4 back-to-back pair (30cm gap)** — Codex B+C'yi physically
  bitişik gösteriyor; layout 4.3m apart (kit corridor convention). Real
  geometry hangi? Saha ziyareti çözer.
- **idx 6 (E rack) 14 vs 12 bays** — Codex 3 ekstra east-end post
  (3880, 5417, 5560). Stamp yokluk mu, PDF simplification mı?
- **idx 14** — isolated SE 1-bay post pair (x=5185, y=683). Phantom mı?
- **idx 15 (V03/V04 candidate)** — east-side 4-bay vertical. KÜÇÜK RF mi?
- **U+J orientation** — Codex'te U north-most horizontal, layout'ta
  y=37 horizontal. Axis-swap U'yu west extreme'e atıyor; J bracket aynı.
- **90° topology mismatch** — Codex CAD'inde rack'ler EAST-WEST,
  layout.json'da NORTH-SOUTH. Pragmatik çözüm: visual ground truth Codex
  viewer'da, sim modeli axis-swapped. Full reconciliation (rack rotation
  flip + walk-distance hesabı baştan) defer edildi (1-2 hafta iş,
  advisor sign-off gerekir).

V&V §4 update notu: "Codex CAD-derived layout applied; layout.json
reflects AutoCAD floor plan via Codex's 16-rack-row extraction."

### 1.5 Single 8-hour shift

ZWM92's 4-month log is compressed to a single synthetic shift. Real
warehouse operations span 16+ hours over multiple shifts. Fix:
`SHIFT_DURATION_MIN` increase + multi-shift dynamics modelling (warm-up,
end-of-shift catch-up, shift handover).

---

## 2. Modelling improvements (concrete follow-up work)

These are fixable; estimates are rough but realistic.

### 2.1 Kit-aware slotting policy [HIGHEST IMPACT]

BOM is now extractable via `zwm92.kit_bom()`. A policy that co-locates
frequently co-picked materials should give an additional 15–25% walk-
distance reduction over the current TravelDistance policy. Implementation:
~4 hours. **Top of the backlog.**

### 2.2 Real-trace replay driver

The fitted Exponential IAT smooths the trace's burst patterns. Op-queue
wait is therefore ≈ 0 in all current runs — effectively no queueing
analysis is happening. A real-trace replay mode (replay ZWM92 timestamps
directly without fitting) would expose the genuine queue dynamics.
Implementation: ~2 hours (driver class is already abstracted).

### 2.3 Kardex shuttle pre-stage / inventory-front model

H1 fixed the batch-picking bug, but Kardex's real shuttle + carousel
hybrid behaviour is not modelled. If sensitivity says Kardex time is a
top-3 driver, a more detailed Kardex model is needed.

### 2.4 Operator skill / line preference

All operators are identical. In reality specific operators specialise on
specific production lines.

### 2.5 RT battery / charging model

Reach trucks never die in the current model. Over an 8-h shift each RT
could realistically need 1–2 charge cycles (~20 min each).

### 2.6 Manhattan / aisle-graph travel distance

Currently 2D Euclidean. Real warehouse: aisle-constrained Manhattan with
one-way corridors. C3 fixed the sort key but the distance metric is still
optimistic. Implementation: networkx corridor graph + Dijkstra. ~6 hours.

### 2.7 Multi-bin SAP placement — partial use

`RealBaselinePolicy.assign` places the material in *all* free SAP bins
when there are multiple. The simulation then picks from the nearest
available. Other bins effectively sit unused for the current order — but
in reality SAP duplicates inventory across bins precisely so different
orders can pick from different bins. Not modelled.

### 2.8 `validate.py` paired-t eps=1e-3 hardcoded

Materials with picks=0 use a smoothing constant `eps=1e-3` to avoid
log(0). The sensitivity of the t-statistic to eps is unknown. Academic-
defensiveness fix: eps sweep.

### 2.9 Sensitivity is OAT-only

OAT sensitivity is the bread-and-butter, but joint perturbation (Latin
Hypercube or Sobol indices) catches interaction effects that the tornado
plot misses. ~3 hours.

### 2.10 `SHIFT_MODE="continuous"` + `BREAK_SCHEDULE` dead config

L9 fixed the comment but the underlying question — should break behaviour
be modelled? — remains open.

### 2.11 Kardex single-station collapse (M6)

All four Kardex units are collapsed onto a single (x, y) point with a
single capacity-4 SimPy `Resource`. Per-station queue dynamics are
underestimated. Fix needs layout-side coordinates per station and is
queued for the layout-geometry session.

### 2.12 Zero-pick orders (H6)

The new `orders_with_no_locations` counter is a face-validity instrument,
not a meaningful throughput metric. In the real warehouse every order has
feasible picks — these orders only exist because the simulation has
incomplete SAP-bin coverage for some materials.

---

## 3. V&V report sharpening

### 3.1 §4 Face validity — DWG omission

DWG extraction exists; the layout rebuild that would let us overlay it on
the simulated geometry was deferred. The V&V report needs an explicit
note: "Phase 1 (DWG-driven layout rebuild) deferred due to manual rack-
mapping requirement (R01..R12 → A..J,U, U absent in DWG)."

### 3.2 §5 Operational validity covers only RealBaseline

The chi-square + paired-t validation is run against the SAP-baseline
policy because that's where ground truth exists. The other four policies
are not directly validated — there is no SAP run with those policies to
compare against. This is academically defensible but a known weak spot.

### 3.3 §7 Sensitivity Holm correction

H3 already applied. The report now quotes `p_holm`; this needs to be
called out explicitly so a reviewer sees that family-wise correction was
applied.

### 3.4 Limitations section — code-audit items not yet folded in

Kardex single-station collapse (M6), zero-pick orders (H6), multi-bin
partial placement (2.7), Manhattan distance gap (2.6) all belong in the
V&V Limitations section. ASSUMPTIONS.md §23 has them; the Word report
needs to mirror.

---

## 4. Repo hygiene / infra

### 4.1 `/tmp/manisa.dxf` not in repo

A build artefact, but `dwg_to_layout.py` references it by hardcoded path.
Fix: env var or `build/` dir.

### 4.2 HANDOFF.md + NEXT_SESSION_PROMPT.md duplication

Both files claim to be the source of truth for the next session.
Consolidate to one.

### 4.3 `scripts/build_vv_report.py` import path

Lives in `scripts/` but does `sys.path` manipulation to import from
`src/`. Refactor to a proper package layout would clean this up.

### 4.4 Zero test coverage

No unit or integration tests. A smoke test (`python -m src.main` exits 0,
KPI ranges sane, no exceptions) would catch a lot of audit-style bugs
before they ship. Not required for the thesis but trivial value-add.

### 4.5 No CI

GitHub Actions with a `python -m src.main` smoke job + lint would catch
regressions on push.

---

## Top-3 next sessions (impact / effort)

1. **Kit-aware slotting policy** (2.1) — new policy class, ~4 h, 15–25%
   walk-distance improvement potential.
2. **Real-trace replay driver** (2.2) — replay ZWM92 timestamps instead
   of fitting, ~2 h, exposes real queue dynamics.
3. **Faz 1 — DWG layout rebuild** (1.4) — manual R01..R12 → A..J,U
   mapping, ~3 h, restores §4 face-validity.

---

## Bug-audit status (this session, 2026-05-26)

| Severity | Total | Fixed this session | Already fixed | Remaining |
| --- | ---: | ---: | ---: | ---: |
| Critical | 3 | 3 (C1/C2/C3) | 0 | 0 |
| High | 7 | 7 (H1–H7) | 0 | 0 |
| Medium | 7 | 5 (M1/M3/M4/M5/M6/M7) | 1 (M2) | 0 |
| Low | 10 | 3 (L1/L8/L9) | 1 (L7) | 6 (deferred — cosmetic) |

Six low-severity items intentionally deferred — they are cosmetic
(unused imports, typo in a docstring) and shipping them now would clutter
the diff. Listed below if anyone needs them:

- L2: unused import in `data_loader.py`.
- L3: stale TODO comment in `slotting.py`.
- L4: f-string with no interpolation in `kpi.py`.
- L5: `print()` left in a hot loop in `simulation.py` (debug remnant).
- L6: inconsistent `Path` vs `os.path` usage.
- L10: README missing the new sensitivity step in the run order.

These are housekeeping; they go in the next cleanup-only commit batch.
