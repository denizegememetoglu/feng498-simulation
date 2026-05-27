# Visual reference — Schneider Manisa MV switchgear warehouse

**Kaynak:** `data/factory-photos-2026-05-26/` (9 WhatsApp foto, 2026-05-26 saha
ziyareti). HANDOFF.md Phase 1.75 V1-V5 için referans tablosu; M2
(`web/sim_v2.html`) entity ve material seçimleri bu fotoğraflara birebir
sadık kalır.

## Genel paleti (tüm karelerden derlenmiş)

| Surface | Renk (hex tahmini) | Notlar |
|---|---|---|
| Rack upright (post) | Mavi `#1c3d6e` ~ `#22467a` | Schneider mavisi, mat boya |
| Rack beam (yatay travers) | Sarı/turuncu `#f5a623` ~ `#f08c1f` | Logoyla aynı sarı |
| Beam tip / safety strip | Sarı-siyah çapraz `#fbd34a` + `#1a1a1a` | Çift renk şerit |
| Column protector (alın koruyucu) | Sarı-siyah dikey şerit `#fbd34a` + `#111` | Yer-zemin teması |
| Floor (ana koridor) | Açık gri `#c8cdd2` (beton-epoksi karışım) | Yer yer parlak |
| Floor lane marking | Sarı `#f5c731` solid | "FORKLİFT YOLU" decal aynı sarı |
| Ceiling truss | Galv çelik `#aab1b8` | Açık gri, alttan beyaz reflektör |
| Ceiling lights | Beyaz lineer LED (~5000 K) | Tube fluorescent görünümlü |
| Carton (kit / KLT) | Bej karton `#d8b690` | "HFA ELEKTRİK", "SEMART", "HENRİK" yazılı |
| Kit tote (mavi konteyner) | Lacivert `#1f3c7a` | Plastic stackable tote |
| Pallet (ahşap) | Doğal ahşap `#c8a878` | Standard EUR pallet |
| Reach-truck gövde | Sarı `#f5a623` | Counterweight + lacivert mast |
| Reach-truck mast | Lacivert `#1a4ea0` | Çift veya üç-bölmeli, fork sarı |
| Mesh safety panel | Galvanize çelik tel `#b8bcc2` | Rack arkası "drop-net" |
| Operator vest | Floresan sarı `#e6f266` + reflektör şerit | Lacivert tulum üstüne |
| Fire extinguisher | Kırmızı `#c83a2e` | Sütun dibinde |

## Sarı bilgi placardları (face-validity için kritik)

Her rafın başında sarı zemin + siyah yazı placard. Tipik içerik:

- **Üst placard (line label):** "F400", "SM6 & 36", "PREMSET", "PRISMA",
  "GOSET", "GHA", "MITT" — production-line eşleştirmesi.
- **Alt placard (rack-letter):** "F", "G", "J", "C", "D" — büyük tek
  karakter sarı zemin (HANDOFF.md sketchindeki "rack adı yatay sarı
  şerit" budur).
- **Yan placard (capacity):** "RAFIN AZAMİ TAŞIMA KAPASİTESİ XXX KG"
  (525 / 700 / 800 KG değerleri foto-ile karşılaşıldı).
- **Floor decal:** "FORKLİFT YOLU" sarı zemin dikey shaft + ▼ ikonu.

## Foto-foto observation tablosu

| # | Foto (relative path) | Frame içeriği | M2 (`sim_v2.html`) için sonuç |
|---|---|---|---|
| 1 | [..//data/factory-photos-2026-05-26/WhatsApp Image 2026-05-26 at 06.24.42.jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.42.jpeg) | Putaway/Kardex bölgesi, ahşap pallet ön planda, sarı travers + lacivert post, mavi tote stack arka planda, çatı çelik truss | Pallet mesh ölçü: 120×80 cm, 14.4 cm yükseklik (EUR). Mavi tote color `#1f3c7a`. Truss-style çatı çizgileri gri tonlarda. |
| 2 | [...06.24.42(1).jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.42(1).jpeg) | Carton-flow rack (gravity rollers), "HFA ELEKTRİK" yazılı KLT kutular, mesh güvenlik paneli, rulolu altyapı | Carton-flow rack farklı: rollers visible at front. KLT box: ~40×30×22 cm bej karton, lacivert logo + el-yazısı SKU panelleri. |
| 3 | [...06.24.43.jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.43.jpeg) | Ana koridor uzun çekim, üstte "F-400" ve "SM6 & 36" hanging signs, sarı capacity placard "700 KG", mesh ceiling between racks | Hanging-sign asset: sarı zemin siyah yazı `1.4×0.4 m` perpendicular to aisle, ~3.5 m yerden. Aisle mesh-ceiling = drop-prevention net (varlık olarak modellenir, yarı şeffaf). |
| 4 | [...06.24.43(1).jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.43(1).jpeg) | "F" + "PREMSET" + "F400" floating rack-letter signs üst üste, RT mast yarıda yükselmiş, sarı capacity + "FORKLİFT YOLU" zemin decal | Rack-letter sprite asset: sarı kare `1.0×1.0 m`, siyah harf font weight ≥800 sans-serif. RT mast 2-stage telescopic, sarı çerçeve + lacivert direkler. Floor decal: sarı dikey shaft 0.6×3.0 m + ▼ ok ucu. |
| 5 | [...06.24.43(2).jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.43(2).jpeg) | "C" + "D" rack-letter signs yan yana, dense carton storage, "800 KG" capacity, footnote: ahşap pallet konveyör (?) zemin seviyesinde | Capacity placard variant: değer 800 KG (D rafı için). Pallet alma konveyörü = putaway zone marker. |
| 6 | [...06.24.43(3).jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.43(3).jpeg) | "J" + "G" + "F" + "PREMSET" hanging signs side-by-side, sütunlarda sarı "20 21" bay numarası etiketleri, mavi zemin shelf info | Bay-number etiketleri: sarı 15×15 cm kare siyah numaralı, her bay'in cephe postuna yapıştırılmış. M2 entity: bay-number sprite per post (opsiyonel, dashboard'da H key ile toggle). |
| 7 | [...06.24.43(4).jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.43(4).jpeg) | "J" + "G" floating signs, sarı-siyah çapraz şeritli column protectors zemin seviyesinde, "525 KG" capacity placard | Column protector asset: dikey silindir/prizmatik koruyucu, h≈0.8 m, sarı-siyah çapraz şerit pattern. Tüm rack uçlarına yerleştirilir (M2 polish için). |
| 8 | [...06.24.43(5).jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.43(5).jpeg) | "J" floating sign, mavi milk-run trolley + sarı şerit, kırmızı yangın söndürücü sütun dibinde, "SEMART" + "HENRİK" kartonları | Milk-run cart color: lacivert `#1c3d6e` + sarı emniyet şeridi. Fire extinguisher entity: kırmızı silindir h≈0.6 m sütun ayağında. |
| 9 | [...06.24.43(6).jpeg](../data/factory-photos-2026-05-26/WhatsApp%20Image%202026-05-26%20at%2006.24.43(6).jpeg) | Cantilever rack (uzun bar perpendicular pose), mesh-protected, ÇÖP KOVASI / scrap-cart ön planda, sarı yer şerit-shaft markings | Cantilever variant: U rafı için olası reference (perpendicular orientation matches Codex idx 12 = U). Scrap-cart asset: gri tekerlekli kafes kutu, ÇÖP KOVASI label. |

## V1-V5 (Phase 1.75) eylem listesi — M2 başlamadan önce

V1. **Sarı capacity placard sprite** — `web/sim_v2.html` rack başına 1
adet, 700 KG default, value rack capacity'den türetilir (`config/layout.json`
`pallet_count`).

V2. **F400 hanging sign** — koridor üstüne perpendicular, line label
(`config/layout.json` `production_lines` array ile eşle).

V3. **Column protector (sarı-siyah)** — her letter-rack iki ucuna
silindirik mesh.

V4. **FORKLİFT YOLU floor decal** — kit_corridors için zemin sarı shaft +
▼ ok, opacity 0.6.

V5. **KLT box variant** — carton-flow rack için ayrık mesh (operatör pick
target = box değil pallet, M3 recorder bunu bilmeli).

## Notlar

- Operatör uniformu **lacivert tulum + floresan sarı yelek**. M2 op kapsülü
  bu paletle.
- Reach-truck **sarı + lacivert + alüminyum fork** standart Linde/Toyota
  görünümlü; kabin kapalı değil (operatör görünür).
- Çatı 6-8 m clear height; truss spacing ~4 m. Foto-tabanlı kabaca
  derived.
- ÇÖP KOVASI = SE-Manisa local terim (bizim sim'de "trash bin" değil,
  süreç içi component-staging cart). Codex CAD'inde idx?  henüz
  eşlenmedi.
