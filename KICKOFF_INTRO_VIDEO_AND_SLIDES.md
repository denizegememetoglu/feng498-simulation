# KICKOFF: FENG 498 Intro Video + Defense Slides

> Bu brief, başka bir Claude Code oturumunda hazırlanmış bir devir teslim dosyasıdır.
> Görev: bu repo'daki FENG 498 projesi ("A Simulation Study of Storage Assignment
> Policies at Schneider Electric Manisa") için **iki çıktı** üretmek.
> Aynı süreç AquaNode adlı başka bir FENG 498 projesi için koşuldu ve çalıştı;
> aşağıdaki teknik reçeteler o oturumda DOĞRULANDI — keşfe token harcama, aynen kullan.

## Çıktılar

1. **`FENG498_Intro.mp4`** — savunma sunumunun başında oynatılacak ~70 saniyelik
   tanıtım videosu (1920×1080 @ 30 fps, H.264, sessiz, İngilizce altyazı bantları).
2. **`FENG498_Defense.pptx`** — ~16–18 slaytlık İngilizce savunma sunumu.

Her ikisi de repo köküne yazılacak.

## SERT SINIRLAR

- `report/`, `src/`, `config/`, `data/`, `docs/` altında HİÇBİR mevcut dosya
  DEĞİŞTİRİLMEZ. Ara dosyalar `/tmp` altında üretilir; sadece iki nihai çıktı +
  (istenirse) bir `handoff_assets/` altı ara klasörü repo'ya yazılır.
- HİÇBİR SAYI UYDURULMAZ. Tüm metrikler şu kaynaklardan birebir alınır:
  `report/sections/05_results.tex`, `report/sections/01_abstract.tex`,
  `docs/data/policy_summary.json`, `docs/data/kpi_by_replication.csv`,
  `report/sections/gen/tab_*.tex`. Hangi politikanın kazandığını ve % iyileşmeyi
  ÖNCE bu dosyalardan çıkar, sonra sahne/slayt yaz.
- Dil: İngilizce (savunma İngilizce). Yazar/danışman/başlık bilgisi
  `report/main.tex` + `report/sections/01_abstract.tex`'ten birebir.
- Bu görev ultracode ile koşulmalı: paralel üretici ajanlar (sahne varlıkları,
  slayt içerikleri) → assemble → adversarial review + düzeltme döngüsü (maks 2 tur).
  AquaNode'da 3-fazlı bu kalıp (Write → Assemble → Review) sorunsuz çalıştı.

## Kaynak haritası (hepsi doğrulandı, mevcut)

| Ne | Yol |
|---|---|
| LaTeX rapor kaynakları | `report/main.tex`, `report/sections/0*.tex` |
| Rapor figürleri (14 adet) | `report/figures/` (policy_comparison.png, sim_flowchart_detailed.png, layout_topdown.png, heatmap_usage-based_abc.png, sensitivity_tornado_*.png, warehouse_material_flows.png, fabrika fotoğrafları) |
| Üretilmiş tablolar | `report/sections/gen/tab_*.tex` (anova, paired_t, kpi_summary, validation, sensitivity…) |
| KPI verisi (6 politika × 20 replikasyon) | `docs/data/kpi_by_replication.csv` |
| Politika özeti (kazanan, ortalamalar) | `docs/data/policy_summary.json`, `policy_stats.json` |
| Gerçek raf geometrisi (animasyon için) | `config/layout.json` (raflar A–J + U, bay'ler, koridorlar, engeller) |
| 3D ambar görüntüleyici (veri gömülü, bağımsız) | `handoff_assets/warehouse-3d-v2.html` |
| Simülasyon timeline oynatıcı | `docs/sim_v2.html` + `docs/timeline/*.jsonl` + `docs/vendor/` |
| Fabrika fotoğrafları (saha ziyareti) | `data/factory-photos-2026-05-26/` (9 JPEG) |
| Savunma notları (ÖNCE OKU) | `docs/defense_notes.md` |
| Tez teslim gereksinimleri | `docs/Bitirme Tezi Icin Gerekli Bilgiler.docx` |
| 6 politika sınıfı (isimler için) | `src/slotting.py` |

## Çıktı A — FENG498_Intro.mp4 sahne planı

Sahneler (süreler yaklaşık; xfade 0.6 s geçişlerle toplam ~70 s):

1. **Başlık kartı** (5 s) — proje başlığı, öğrenci adı, danışman, "FENG 498 ·
   Izmir University of Economics". Koyu lacivert zemin (#0d1420), aksan #39d0ff.
2. **Problem kartı** (7 s) — kitting lead time / operatör yürüme mesafesi
   motivasyonu; abstract'taki gerçek cümle ve sayılarla.
3. **Ambar 3D turu** (9 s) — `handoff_assets/warehouse-3d-v2.html`'den headless
   Chromium kareleri. Kamera açısını değiştirmek için sayfaya JS inject et
   (`--run-all-compositor-stages-before-draw` gerekmez; birden çok screenshot al,
   her birinde URL hash veya injected script ile farklı açı) — olmazsa tek iyi
   açı + Ken Burns yeterli.
4. **Çalışma prensibi animasyonu** (14 s) — matplotlib kare üretimi (aşağıdaki
   kalıp). `config/layout.json`'dan GERÇEK raf poligonlarını çiz (kuşbakışı),
   bir kit siparişinin pick listesini önce Baseline yerleşiminde sonra kazanan
   politika yerleşiminde rota olarak animasyonla göster; alt bantta kümülatif
   yürüme mesafesi sayacı iki politikada yarışsın. Mesafe oranı gerçek KPI
   ortalamalarıyla tutarlı olsun (`avg_walk_distance` sütunu).
5. **Simülasyon oynatıcı** (7 s) — `docs/sim_v2.html` ekran görüntüsü; JSONL
   fetch'i file:// altında çalışmaz, repo kökünde `python3 -m http.server 8765`
   başlatıp `http://localhost:8765/docs/sim_v2.html` çek.
6. **Sonuç grafiği** (7 s) — `kpi_by_replication.csv`'den video paletinde bir
   karşılaştırma grafiği üret (ör. politika başına lead-time box/bar) — rapor
   figürünü de kullanabilirsin ama koyu temaya uymuyorsa yeniden çiz.
7. **Sonuç kartı** (7 s) — kazanan politika + baseline'a göre % iyileşme
   (kaynaklardan), 6×20 replikasyon, istatistiksel anlamlılık notu.
8. **Kapanış kartı** (5 s) — proje adı + "Supervisor: …" + tarih.

### DOĞRULANMIŞ teknik reçeteler

**Three.js sayfasını headless çekme** (WebGL için swiftshader ŞART, yoksa siyah kare):
```bash
chromium --headless=new --disable-gpu --enable-unsafe-swiftshader \
  --use-angle=swiftshader --window-size=1920,1080 \
  --virtual-time-budget=20000 --screenshot=/tmp/shot.png "URL"
```

**Matplotlib kare üretimi kalıbı:** `figsize=(19.2,10.8), dpi=100` → tam 1080p;
her karede `fig.clf()`, sonda `fig.savefig(f'/tmp/frames/a{f:04d}.png', facecolor=BG)`.
DİKKAT: data-koordinatlı daireler eksen oranı yüzünden elips görünür — ya
`ax.set_aspect('equal')` kullan (kuşbakışı layout için doğal) ya da piksel
yarıçapını eksen ölçeğine çevir.

**Kare dizisi → sahne mp4:**
```bash
ffmpeg -y -framerate 30 -i /tmp/frames/a%04d.png -vf "scale=1920:1080,format=yuv420p" \
  -c:v libx264 -preset medium -crf 18 -r 30 sceneN.mp4
```

**Still görsel → Ken Burns sahnesi** (zoompan'de `:d=1:s=1920x1080:fps=30`
ZORUNLU — eksik bırakılırsa çıktı 1280×720@25 olur ve xfade zinciri
"Nothing was written into output file" hatasıyla ÇÖKER; bu hata bizzat yaşandı):
```bash
ffmpeg -y -loop 1 -i img.png -frames:v 210 -vf "\
scale=1920:1080:force_original_aspect_ratio=decrease,\
pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0d1420,\
zoompan=z='min(1+0.0007*on,1.14)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=30,\
drawtext=fontfile=/usr/share/fonts/liberation/LiberationSans-Bold.ttf:text='CAPTION':\
fontsize=42:fontcolor=0xdce8f5:x=(w-text_w)/2:y=h-115:box=1:boxcolor=0x0d1420@0.7:boxborderw=20,\
format=yuv420p" -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 sceneN.mp4
```

**Sahneleri xfade ile birleştirme:** offset_k = (önceki offset) + (k. klip süresi) − 0.6.
Birleştirmeden ÖNCE her sahneyi `ffprobe -show_entries stream=width,height,r_frame_rate,duration`
ile doğrula (hepsi 1920×1080, 30/1 olmalı). Son zincire
`,fade=t=in:st=0:d=0.5,fade=t=out:st=<son-1.2>:d=1.2,format=yuv420p` ekle,
`-movflags +faststart` ile yaz.

**Doğrulama:** final mp4'ten `ffmpeg -vf "select='eq(n,...)'" -vsync vfr` ile 5-6
kare çıkar ve Read ile GÖRÜNTÜLE (altyazı taşması, siyah kare, bozuk sahne kontrolü).

## Çıktı B — FENG498_Defense.pptx

1. ÖNCE `docs/defense_notes.md` ve `docs/Bitirme Tezi Icin Gerekli Bilgiler.docx`
   oku — format/süre beklentisi varsa ona uy.
2. `pptx` becerisini kullan (Skill tool). 16:9, koyu olmayan temiz akademik tema
   (savunma salonu projektöründe koyu tema kötü görünür), slayt başına ≤4 madde.
3. Akış (~16–18 slayt): başlık → ajanda → problem & motivasyon → sistem tanımı
   (fabrika fotoğrafları + `layout_topdown.png`) → veri (SAP Malzeme Girişleri +
   ZWM92, satır sayıları raporlardan) → simülasyon modeli
   (`sim_flowchart_detailed.png`, SimPy) → 6 slotting politikası
   (`src/slotting.py` sınıf adlarıyla kısa tablo) → V&V (chi-square,
   `tab_validation`) → deney tasarımı (6 politika × 20 replikasyon, CRN, %95 CI)
   → sonuçlar (policy_comparison + ANOVA/paired-t özetleri) → duyarlılık
   (tornado) → öneri & sonuç → gelecek işler → Q&A.
4. Konuşmacı notları ekle (her slayta 2-3 cümle, rapordaki ilgili bölümden).
5. Doğrulama: `libreoffice --headless --convert-to pdf` → `pdftoppm` → birkaç
   slaytı Read ile görüntüle (taşma/figür kırpılması kontrolü).

## Bitiş kriteri

- `FENG498_Intro.mp4`: ffprobe ≈70 s, 1920×1080, izlenen örnek kareler temiz.
- `FENG498_Defense.pptx`: tüm slaytlar PDF önizlemede düzgün; sayılar raporla
  birebir tutarlı (review ajanı rapor PDF'iyle çapraz kontrol etsin).
- Repo'da değişen mevcut dosya YOK (`git status` sadece yeni çıktıları göstermeli).
