# NEXT_SESSION_PROMPT.md

Bir sonraki Claude Code session'ı bu dosyayla başlasın. Önce
[HANDOFF.md](HANDOFF.md) + [CLAUDE.md](CLAUDE.md) +
[IMPROVEMENT_BACKLOG.md](IMPROVEMENT_BACKLOG.md) okunsun. Üçü güncel.

---

## Bu session (2026-05-27) ne yaptı

Önceki session Codex'in CAD-fidelity 3D preview'ını projeye entegre
etmişti ama `config/layout.json`'a **apply edilmemişti** (SAP join
risk gerekçesiyle defer). Bu session'da user verbatim:

> "olum zaten dedik ki 3dyi her şeyie implemente et nasıl yani önceki
> promptta bnu demedim mi"

Apply onayı verildi. Sırasıyla yapıldı:

- `cp config/layout.json config/layout.json.bak_pre_codex_apply`
- `cp config/layout_dwg_rebuilt.json config/layout.json`
- Pallet canary 3203 ✓ (SAP join intact).
- Pipeline rerun:
  - `python -m src.main` → 5 policies, KPI shift +1-5m walk vs prior.
  - `python -m src.validate` → χ² + paired-t reject as expected.
  - `python -m src.analyze` → Wilcoxon paired-by-order.
  - `python -m src.sensitivity` → background.
- V&V Word report yeniden derlendi
  (`/home/dege/Downloads/feng498-final-VV-report.docx`).
- `docs/layout.json` + `web/layout.json` mirror refreshed.
- MD'ler güncel: CLAUDE.md status snapshot, HANDOFF.md, BACKLOG §1.4.

### Headline KPIs (post-apply)

| Policy | Orders | Prep (min) | Walk (m) | RT util |
|---|---:|---:|---:|---:|
| Baseline (Heuristic) | 428 | 4.80 | 79.5 | 6.9% |
| Baseline (Actual SAP) | 437 | 3.12 | 80.5 | 2.3% |
| Usage-based ABC | 428 | 4.45 | 83.9 | 5.9% |
| Double ABC | 442 | 4.94 | 90.2 | 7.0% |
| Travel-distance | 442 | 4.43 | 84.5 | 6.0% |

---

## Açık sorular (user dönünce sor)

1. **Commit?** Bu session'da büyük diff var:
   - `config/layout.json` (apply), `.bak_pre_codex_apply` (backup).
   - `config/rack_mapping_dwg_to_sap.json` v4 + backup.
   - `config/layout_dwg_rebuilt.json` + 3 backup.
   - `output/dwg_codex_geometry.json` (yeni).
   - `web/index.html`, `web/sim.html` (yeni), mirror'lar.
   - `docs/*` mirror.
   - 4 MD update.
   - Output artefacts (replications.json, policy_*.json, validation_*).
2. **Saha ziyareti çıktısı** — açık idx 3+4 (back-to-back?), idx 6
   (E rack 12 vs 14 bays), idx 14 (phantom?), idx 15 (V03/V04?).
3. **90° topology reconciliation** — sim modeli hâlâ axis-swapped.
   Full rotation flip 1-2 hafta iş, advisor sign-off gerekir.
4. **Kit-aware slotting policy** — BACKLOG §2.1, top priority,
   `zwm92.kit_bom()` zaten hazır.

---

## Olası senaryolar — user dönünce

### Senaryo A: Commit + push onayı

- `git add -A` (kontrollü, .env / wa-logs.txt değil).
- Commit message: "Apply Codex CAD layout + pipeline rerun".
- Co-author tag: `Claude Opus 4.7 <noreply@anthropic.com>`.

### Senaryo B: Saha ziyareti çıktısıyla mapping refine

- Codex idx 3+4 back-to-back kararını kesinleştir.
- idx 14, 15'i fiziksel olarak ne — onayla.
- E rack 12 mi 14 mi bay — PDF mi gerçek mi?
- Kararları `config/rack_mapping_dwg_to_sap.json` v5'e işle.
- Layout regenerate + apply + pipeline rerun.

### Senaryo C: 90° topology reconciliation

Büyük iş. Full layout.json rewrite (rack orientation flip), tüm
walk-distance hesaplamaları değişir. Advisor sign-off gerekir.

### Senaryo D: Kit-aware slotting (BACKLOG §2.1)

Codex işi kapansın, kit co-pick matrix'ten yeni policy yaz. ~4 saat.
Beklenen kazanım: 15-25% walk-distance reduction.

---

## DO NOT TOUCH (değişen kısımlar var)

1. **`config/layout.json` geometry** — Codex apply done bu session.
   Backup `.bak_pre_codex_apply`. Yeni geometry edit için user
   explicit onayı yine şart.
2. **`Warehouse.sap_position_id` join key** — bay codes + rack ID'ler.
3. **`SAME_SEED_FOR_ALL_REPS=True`, `N_REPLICATIONS=1`** — advisor.
4. **`whatsapp_export/`, `wa-logs.txt`** — kişisel veri.
5. **`/tmp/feng498-cleanup-quarantine/`** — 1 hafta sonra sil.

---

## Hızlı sanity-check komutları

```bash
# Repo durumu
git status --short
git log --oneline -10

# SAP join canary (post-apply layout.json)
python -c "import json; d=json.load(open('config/layout.json')); \
  print(sum(s['pallet_count'] for r in d['racks'] for s in r['segments']))"
# → 3203

# Codex viewer
python -m http.server 8000
# → http://localhost:8000/web/        (Codex CAD viewer)
# → http://localhost:8000/web/sim.html (eski sim viewer)

# Sensitivity log check (background run)
ls -la output/sensitivity*
```

---

## Bitirince güncelle

- `HANDOFF.md` "What just shipped" bölümüne yeni iş ekle.
- `CLAUDE.md` "Status snapshot" güncelle.
- `IMPROVEMENT_BACKLOG.md` ilgili maddesi.
- `NEXT_SESSION_PROMPT.md` — yeniden yaz.
