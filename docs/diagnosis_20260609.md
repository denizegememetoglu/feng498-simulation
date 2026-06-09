# Teşhis Raporu — FENG 498 Simülasyon Fix Pass (2026-06-09)

Hazırlayan: Claude (HANDOFF.md Faz 1). Kaynak: 3 keşif + 3 derin audit
taraması + ham ZWM92 verisi üzerinde doğrudan doğrulama. Her madde:
**ne yanlış → IE tezi olarak neden zarar veriyor → eminlik → düzeltme**.

---

## KRİTİK — düzeltilmeden teslim edilmemeli

### K1. Talep yükü ~4.5x düşük: batch arrival yapısı modellenmemiş

**Ne yanlış:** ZWM92'de kit-order'lar tek tek değil **batch halinde**
dispatch ediliyor. Timestamp'li 18 164 order'da 3 885 batch var
(aynı-saniye kümeleri): ortalama **4.68 kit/batch**, medyan 2, maks 79.
Fit edilen Exp(5.36 dk) IAT aslında **batch-arası** süre; driver bunu
**order-arası** kullanıyor → sim ~87 order/gün üretiyor. Gerçek:
40 804 order / 103 aktif gün ≈ **396 order/gün**. Saat profili
(07:00–16:00) tek vardiyalık operasyonu doğruluyor; yani 480 dk'lık sim
günü doğru pencere, ama içine ~4.5x az iş akıyor.

**Neden zarar veriyor:** Danışmanın istediği 4 KPI'dan ikisi (waiting
time, RT utilization) bu yüzden anlamsız: bekleme tüm politikalarda 0.0,
RT utilization %3.7–7.5. "Beklemesiz, %4 dolulukta depo" tablosuyla
slotting politikası kıyaslamak, kuyruk etkilerinin hiç olmadığı bir
rejimde kıyaslamaktır — politika farkları yalnızca yürüme mesafesinden
ibaret kalır ve savunmada "bu depo neden bomboş?" sorusu kaçınılmaz.

**Eminlik:** Yüksek. Ham veriden doğrulandı (3 885 batch, %91.2'sinde
IAT=0 olan ardışık çift oranı, gün başına hacim).

**Düzeltme:** Inter-batch IAT ~ Empirical (pozitif within-shift gap'ler,
mean 5.36, CV 2.04 — Exp varsayımı CV=1 gerektirdiğinden empirik daha
dürüst) + batch-size ~ Empirical (mean 4.68). Bu ikili, kalibrasyon
hedefini ölçeklemesiz tutturuyor: 480/5.36 × 4.68 ≈ 419 order/gün ≈
gerçek 396 (+%5.8, ±%10 bandında). "Sim günlük hacmi ≈ ZWM92 günlük
hacmi" eşleşmesi validate.py'ye pozitif operasyonel geçerlilik kanıtı
olarak eklenir.

### K2. Deney tasarımı: N=1 same-seed → sıfır varyans, hipotez testi yok

**Ne yanlış:** `config.py:129-131` `N_REPLICATIONS=1,
SAME_SEED_FOR_ALL_REPS=True`; yorum bunu "advisor decision" diye
atfediyor. Toplantı tutanakları tam tersini söylüyor (≥20 replikasyon).
Tüm `_std` alanları 0.0, CI'lar NaN, ANOVA/Tukey/Welch `None`; analiz
tek bir paired-by-order Wilcoxon'a düşmüş.

**Neden zarar veriyor:** Politika farklarına dair hiçbir istatistiksel
iddia kurulamıyor; %6-8'lik yürüme farkı gürültü mü sinyal mi
bilinmiyor. Danışmanın 1 numaralı kabul kriteri karşılanmıyor; ekip
Minitab'de test koşamıyor çünkü replikasyon-bazlı veri yok.

**Eminlik:** Kesin.

**Düzeltme:** N=20 (runtime izin verirse 30), bağımsız seed
(`RANDOM_SEED + rep`). Seed yalnızca rep index'ine bağlı olduğundan
politikalar arası **common random numbers** bedavaya geliyor — ama K3'teki
RNG paylaşımı düzelmeden CRN gerçek değil. `analyze.py`'deki
ANOVA/Tukey/Welch/CI makinesi zaten yazılmış; N≥2 veriyle otomatik
aktive oluyor. Tidy `kpi_by_replication.csv` (satır=policy×rep) Minitab
exportu olarak eklenir. Yanlış atıflı config yorumu silinir.

### K3. Paylaşılan RNG stream'i CRN'i bozuyor

**Ne yanlış:** `simulation.py:276` tek `np.random.default_rng(seed)`
hem arrival hem servis süreleri için kullanılıyor. Politika değişince
pick-time çekiliş sayısı değişiyor → aynı seed'le bile arrival akışı
kayıyor (Heuristic 434 order, SAP 467 order — aynı seed!).

**Neden zarar veriyor:** Politikalar aynı talebi görmüyor; "paired"
kıyaslar aslında eşleşmiyor, throughput farkları kısmen artefakt.

**Eminlik:** Yüksek (order sayısı farkı bunun kanıtı).

**Düzeltme:** `arrival_rng` ve `service_rng` ayrımı (seed, seed+offset).
Arrival akışı politikadan bağımsızlaşır; gerçek CRN.

### K4. RT depoya dönüş yolu modellenmemiş

**Ne yanlış:** `simulation.py:444-465` — RT depot→raf gidiyor, pick
yapıyor, resource bırakılıyor; raf→depot dönüşü ne zaman ne busy-time
olarak var. RT ışınlanıyor.

**Neden zarar veriyor:** RT busy time yapısal olarak eksik (dispatch
başına ~tek yön travel kadar). K1 düzelince yük artacak; dönüş yolu
olmadan RT kapasitesi olduğundan büyük görünür, utilization ve kuyruk
KPI'ları iyimser sapar.

**Eminlik:** Kesin (kod akışı net).

**Düzeltme:** Pick sonrası dönüş travel'ı resource hold içinde yield +
`add_rt_busy`; recorder'a dönüş segmenti.

---

## YÜKSEK

### Y1. Validation totolojik + t-testi kısa sim yüzünden reddediyor

χ² ve paired-t'nin "beklenen" vektörü, driver dağılımlarının fit
edildiği AYNI ZWM92 verisi — bağımsız kanıt değil iç tutarlılık testi.
Üstelik restricted χ² aslında **reddetmiyor** (p=0.097) ama Cochran
kuralı ihlalli (11 hücrenin 10'unda E<5) → istatistiksel olarak
geçersiz; t-test ise 0.5 günlük validation sim'i per-material rate'leri
stabilize edemediği için reddediyor (p=2.1e-05). **Düzeltme:** validation
sim süresini uzat, düşük-E hücreleri birleştir, K1 sonrası "günlük hacim
eşleşmesi" + "20-rep KPI CI'ları" gibi pozitif kanıtlar ekle, fit≠holdout
sınırını raporda dürüstçe yaz. Eminlik: yüksek.

### Y2. Lognormal σ değerleri beyan edilen CV'lerle tutarsız

`config.py:47-49` σ=1.30/1.20/1.40; doğru dönüşüm σ=√ln(1+CV²) ile F400
CV'lerinden 1.17/1.03/1.24 çıkmalı. Mevcut değerler varyansı ~%10-20
şişiriyor (ortalama korunuyor — μ=ln(m)−σ²/2 doğru). Yorumdaki "CV≈1.7"
de F400 ham verisiyle (rf_scan CV=2.22, manual 1.03) eşleşmiyor.
**Düzeltme:** σ'ları ölçülen CV'lerden yeniden hesapla, yorumu ölçümle
eşle. Eminlik: yüksek.

### Y3. PER_LINE_KITTING ölü + 4 Kardex tek noktada

`PER_LINE_KITTING=True` ama layout.json'da `production_lines` yok → tüm
orderlar global kitting centroid'inden başlıyor; `kardex_stations` yok →
4 karusel tek noktaya çökmüş. Yürüme mesafeleri sistematik sapıyor.
**Düzeltme (kullanıcı onaylı):** layout.json'a SADECE eklemeli
anahtarlar — raf/bay/segment'e dokunmadan, canary 3203 korunarak.
Eminlik: kesin (kod fallback yorumları kendisi itiraf ediyor).

### Y4. Utilization muhasebesi tutarsızlıkları

(a) `util_overflow` listesi her `summary()` çağrısında birikiyor
(recorder periyodik snapshot alıyor → şişme riski); (b) utilization
payı/paydası tam pencere, order KPI'ları aktif pencere — farklı
popülasyon; (c) Kardex utilization hiç izlenmiyor; (d) sim sonunda
kesilen orderlar görünmez (`orders_started` yok) — yük artınca
survivorship bias yapar. **Düzeltme:** dördü de küçük, kpi.py +
simulation.py. Eminlik: yüksek.

### Y5. Sessiz fallback'ler

ZWM92 cache yoksa driver sessizce sentetik Poisson'a düşüyor
(`simulation.py:147-149`) — temiz makinede tez sonuçları fark edilmeden
sentetik olur. **Düzeltme:** [WARN] print + run_manifest'e driver tipi.
Eminlik: kesin.

---

## ORTA

- **O1. "Baseline (Actual SAP)" %12.6 SAP-sadık:** 5 941 malzemenin
  750'si SAP konumunda, 2 872'si Kardex (politika-bağımsız), 2 319'u
  heuristic fallback. Politika adı ground-truth ima ediyor; raporda
  "SAP + FMR hibrit" olarak dürüstçe sunulmalı, fidelity sayıları
  metoda yazılmalı. (Kod davranışı doğru; sunum meselesi.)
- **O2. Throughput KPI alanı yok;** `avg_wait_time` aslında RT kuyruğu
  beklemesi (ad belirsiz). → `throughput_orders_per_hr` + adlandırma.
- **O3. Minitab tidy CSV yok;** `orders_with_no_locations` agregata
  girmiyor; per-policy CSV'ler yalnız son rep (etiketsiz).
- **O4. Sensitivity 5 özdeş rep koşuyor** (same-seed) — sıfır bilgi,
  5x boşa süre. → bağımsız seed.
- **O5. Viewer:** (a) op_move waypoint'leri atılıyor (%80'i >2 nokta) →
  ajanlar rafların İÇİNDEN düz çizgi yürüyor — HANDOFF'taki "doğrusal
  hareket" şikâyetinin gerçek kaynağı bu; sim routing'i zaten
  koridor-saygılı (`warehouse.py:552-662`), ASSUMPTIONS §23.6 bayat.
  (b) Validation sekmesi `paired_t_test` anahtarı arıyor, dosyada
  `t_test_per_material` var → t-test satırı hiç görünmüyor.
  (c) Throughput kartı yok. (d) Shift badge continuous modda yanlış
  "Off-shift" gösteriyor. (e) replications/policy_stats.json viewer'da
  hiç kullanılmıyor (N=20 sonrası CI gösterimi fırsatı).
- **O6. ZWM92 timestamp kapsamı %45:** 22 640 order'da saat yok
  (Mcset/Premset/SM6/DMK/Sepam exportlarında saat alanı eksik). IAT/batch
  yapısı 3 aileden (Okken, AKS_PAK, F400) ekstrapole; hacim kalibrasyonu
  toplam 40 804 üzerinden yapılmalı. ASSUMPTIONS'a yazılacak.
- **O7. TRACE_DRIVEN adı yanıltıcı** (trace replay değil distribution
  sampling) — savunmada yanlış beyan riski; dokümante edilecek.

## DÜŞÜK (hızlı düzeltilir / belgele-geç)

H-tuşu çift handler bayat toast; theme-light dark dönüş rengi;
`_walk_distance_from` ölü kod; IAT std/CV summary'ye yazılmıyor;
pozisyon kilidi yield-try anti-pattern; launcher browser-fallback
kapalı (savunma günü Qt kurulu olduğunu doğrula); RT depot koordinatı
yaklaşık (belgele).

## DÜZELTMEYE DEĞMEZ (deadline öncesi) — rapora limitation yaz

1. Tek yönlü koridor akış yönleri (routing'de yön kısıtı yok).
2. Layout 90° orientation sorusu (CAD vs sim convention) — her ikisi de
   kendi içinde tutarlı, reconciliation tam pipeline rewrite demek.
3. Kit-aware (co-pick) slotting politikası — backlog'da kalsın.
4. Per-line time-motion (F400 ekstrapolasyonu) — sensitivity sınırlıyor.
5. Milk-run'ın gerçek kit taşıma modeli (şu an dekoratif, kapalı).
6. op_id'nin fiziksel işçi kimliği olmaması (SimPy anonim resource).
7. idx14/idx15 unmapped raflar — site visit konusu.

## Doğrulanmış-DOĞRU (yeniden şüphelenme)

Bekleme ölçüm noktaları (request öncesi/sonrası timestamp'ler doğru);
lead/prep tanımları; warmup arrival-filtresi; Kardex tek-karusel
amortizasyonu (H1); distinct-kit örnekleme (H5); multi-bin nearest-pick;
lognormal ortalama koruması; bin decoder + canary; web/docs byte-özdeş
mirror + tam offline vendor; routing koridor-saygılı rectilinear.

## EK — 2026-06-10 forensik turu (adversarially-verified, 6 ajan)

Kullanıcının "iyileştirmeler neden iyileştirmiyor / validasyon neden
geçersiz" sorularına sayısal cevaplar; her bulgu bağımsız yeniden-türetme
ile doğrulandı:

1. **χ² kapsam hatası (düzeltildi):** restricted testin expected vektörü
   TÜM ZWM92 malzemelerinden geliyordu, observed sadece 750 decoded
   malzemeden. Kapsam düzeltilince χ² 174→~80, V 0.145→~0.10. I/J/U
   sıfır-pick anomalisi = ölü stok (decoded malzemelerinin %97-100'ü
   4 ayda sıfır pick) — model hatası değil, veri gerçeği.
2. **"İyileştirmeler" neden kaybediyor (mekanizma, doğrulanmış):**
   op-queue bekleme lead'in %73-80'i; RT util ↔ lead korelasyonu
   r=0.998. Mesafe-odaklı politikalar (a) yanlış origin'e optimize
   ediyor (merkez centroid; oysa talebin %77'si hat-koridor
   noktalarından başlıyor — Travel-dist'e +10.7 m ağırlıklı ceza),
   (b) seviye-körü: en yakın pozisyonlar üst-seviye/RT-katlı → sık
   malzemeler RT-pick'e düşüyor → operatör RT beklerken kilitli →
   kuyruk kaskadı → lead 2x. **Tez bulgusu**: saf mesafe optimizasyonu
   congestion'ı ihmal eder; önerilen `LineAwareSlottingPolicy`
   (hat-origin + RT'siz seviye önceliği + koridor-bazlı doğal yük
   dağıtımı) bu mekanizmayı düzeltir (SÜPERSEDE — final N=20 sonuç: lead 8.24 vs SAP 14.59 (−%43, paired-t p=1.8e-9),
   RT util %1.1, tüm 4 danışman KPI'sında kazanan).
3. **Reddedilen fikirler (doğrulama sayesinde):** (a) ZWM92 observed-bin
   yerleştirme — adresler paylaşımlı bölge kodu (%63 slot çakışması),
   yerleştirme kaynağı olamaz; (b) multi-bin adillik düzeltmesi —
   gerçekte tüm politikalar 1 slot/malzeme atıyor, asimetri yok;
   (c) KDX set genişletme — 329 gap malzemesinden sadece 1'i aktif
   master'da (8 satır, ≈%0 hacim).
4. **Özet master staleness:** decoded malzemelerin %6.4'ünün özet rafı
   ZWM92'de en sık görülen raftan farklı (en büyük küme: H→G/F).
   Raporda limitation.

## Uygulama sırası (Faz 2 — onaylı plan)

1. Batch-arrival + kalibrasyon → 2. RT dönüşü + RNG ayrımı + σ →
3. layout eklemeli anahtarlar → 4. N=20 + muhasebe → 5. KPI/tidy CSV/
analyze → 6. validate → 7. viewer → 8. dokümantasyon + tam rerun +
sanity/VV regresyon. Canary 3203 her layout dokunuşunda. Commit yok.
