# Savunma Notları — Beklenen Jüri Soruları ve Hazır Cevaplar (2026-06-10)

Sayılar: N=20 CRN, distinct-ağırlıklı talep modeli (son koşu 2026-06-10).

## Sonuç tablosu (ezbere)

Line-aware 7.89 ± 0.50 dk lead (SAP 14.08'e karşı **−%44**, paired-t
p=4×10⁻¹²) · bekleme 5.02 dk · picking RT util %1.2 · throughput
398.6/gün · hacim kalibrasyonu gerçek günlük hacmin **%1.1** içinde.

---

## 1. "İleri (alt seviye) slotları kim dolduruyor?" — EN KRİTİK SORU

Model **yalnız picking** simüle eder; putaway/replenishment kapsam dışı
(ASSUMPTIONS §24.7a). Cevap üç adım:
1. Kapsam altı politika için de aynı — karşılaştırma içsel olarak adil.
2. Mesafe-odaklı politikaları batıran mekanizma (operatörün pick
   sırasında RT beklerken kilitli kalması) replenishment'tan bağımsız;
   dolum vardiya dışına/araya planlanabilir, pick anındaki kuyruğu
   üretmez.
3. "%1.2 RT" rakamı PICKING iş yüküdür, toplam RT iş yükü değil —
   slayttta böyle etiketli. Slot kapasitesi + tükenme modeli gelecek iş.

## 2. "χ² reddediyor — modeliniz geçersiz mi?"

n≈5 900 pick'le test gücü çok yüksek; anlamlılık değil **etki
büyüklüğü** okunmalı: Cramér's V = 0.216 (küçük-orta). Pozitif
kanıtlar: günlük hacim CI kapısı PASS (%1.1), bağımsız F400 timing
kaynağı, rota/yüz geçerliliği, tekrarlanabilirlik. Ayrıca expected
vektörü driver'ın fit edildiği AYNI veriden — bu bilinçli olarak
"iç tutarlılık testi" diye etiketli; ikinci gözlem dönemi yok (veri
sınırı, dürüstçe beyan).

## 3. "%44 iyileşme gerçek mi? Aşırı iyimser değil mi?"

Üst sınırdır ve öyle sunuyoruz: slotting aynı 4 aylık talep geçmişine
optimize edildi (in-sample). Temporal holdout: ilk-yarı/ikinci-yarı
malzeme sıraları Spearman ρ=0.73; ilk-yarı top-1050, ikinci-yarı
pick'lerinin %79.8'ini kapsıyor → konuşlandırmada kazanç küçülür ama
mekanizma kalır. İkinci kanıt: 2x yük stres testinde avantaj 6.2→20.7
dk'ya BÜYÜYOR (SAP 34.1 dk / RT %42.9'a karşı LA 13.5 dk / RT %2.4) —
kazanç, kalibre edilmiş orana bağlı bir artefakt değil, yapısal.

## 4. "Baseline'ınız gerçek SAP yerleşimi mi?"

Kısmen: 750 malzeme gerçek özet bininde, 2 872'si Kardex (politika-
bağımsız), 2 319'u FMR-heuristik fallback — yani "SAP + FMR hibrit"
(raporda böyle). ZWM92 adresleri paylaşımlı bölge kodları olduğundan
(%63 slot çakışması) tekil yerleştirme kaynağı olamadı — denendi,
ölçüldü, reddedildi.

## 5. "Neden Exponential değil empirik IAT? Neden batch?"

ZWM92'de ardışık orderların %91'i aynı-saniye (batch release); 3 885
batch, ort. 4.68 kit. Pozitif gap'lerin CV'si 2.04 — Exp (CV=1)
reddedilir. Empirik gap + empirik batch-size, ölçeklemesiz olarak
gerçek günlük hacmi üretir (%1.1 sapma). Malzeme ağırlıkları DISTINCT
kit satırı bazlı (sim'in pick semantiğiyle birebir; qty-expanded
ağırlık bulk malzemeleri 2x şişiriyordu — düzeltildi ve sonuç değişmedi:
marj 6.35→6.19 dk vs SAP, yön aynı → sonuç bu seçime dayanıklı).

## 6. "Terminating model + 30 dk warm-up yeterli mi?"

Sistem her gün boş başlayıp boş bitiyor (07:00–16:00 tek vardiya,
ZWM92 saat profili) → terminating; steady-state warm-up analizi
gerekmez (Law, ch.9). 30 dk warm-up/cooldown kenar etkilerini kırpar;
KPI'lar arrival-time filtreli.

## 7. "CRN altında Tukey geçerli mi?"

Geçerli ve konservatif: CRN politikalar arası pozitif korelasyon
yaratır (lead, SAP↔LA r≈0.89); bağımsız-örneklem Tukey bu korelasyonu
kullanmaz → güç kaybı ama tip-I hata kontrolü bozulmaz. Birincil test
CRN'i sömüren paired-by-replication t-testi (Minitab'daki eşli testin
birebir karşılığı; kpi_by_replication.csv'den tekrarlanabilir).

## 8. "ABC politikaları neden işe yaramıyor?"

Distinct-ağırlıklı düzeltme sonrası küçük ama anlamlı iyileşme
sağlıyorlar (Usage −0.63 dk, Double −0.25 dk vs Heuristic) — yani ABC
yanlış değil, yetersiz: seviye-körü havuzlar sık malzemeleri RT-katlı
slotlara da koyuyor. Sıralama: mesafe-körü < ABC < seviye+hat farkındalı.
Travel-distance'ın çöküşü (26.9 dk; 20 rep'te 682 kesilmiş sipariş vs
SAP 284) bu mekanizmanın doygunluk kanıtı.

## 9. "Viewer'daki animasyon veriyle tutarlı mı?"

KPI'lar sim çıktısından (JSONL timeline + JSON özetler); animasyon
display-layer'da yeniden rotalanır (çizilen raf kutularına karşı,
kesişen aday yol kabul edilmez — 4 000 rastgele rota + 1 459 gerçek
dispatch'te 0 çakışma). Mesafe/süre KPI'ları sim'den gelir, görsel
rota onları değiştirmez (raporda not).

## 10. "3 ay daha olsa ne yapardınız?"

(1) Replenishment + slot kapasitesi modeli; (2) holdout dönemi
(yeni 2-3 aylık ZWM92 çekimi ile out-of-sample doğrulama); (3) saha
ölçümleri (yürüme/lift hızları, U-J topolojisi, koridor yönleri);
(4) Line-aware'in kademeli uygulanması için top-20 taşıma listesinin
(X14 paneli) pilotu.

---

## Tek slaytlık özet cümle

"Gerçek dispatch log'undan kalibre edilmiş yük altında, mesafe-odaklı
slotting reach-truck kuyruğu yüzünden lead time'ı ikiye katlıyor;
hat-farkındalı, RT'siz-seviye-öncelikli yerleştirme aynı yürüme
mesafesiyle lead time'ı %44 düşürüyor ve bu kazanç 2x yükte daha da
büyüyor."
