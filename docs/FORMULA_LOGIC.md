# Logika Formula Alert Bandarmology Bot

Setiap alert menampilkan Top 5 saham berdasarkan formula masing-masing.
Dokumen ini menjelaskan apa yang dihitung, bagaimana cara kerjanya, dan kondisi apa yang membuat sebuah saham masuk Top 5.

---

## 1. 🐳 WHALE ACCUMULATION (WAS)

**Pertanyaan yang dijawab:** Broker besar mana yang paling agresif akumulasi hari ini?

**Diranking berdasarkan:** Skor WAS (0–1), gabungan 3 komponen:

### Komponen

| Komponen | Bobot | Cara Hitung |
|----------|-------|-------------|
| Konsentrasi | 40% | Net buy Top 3 broker ÷ total nilai transaksi semua broker hari ini |
| Persistence | 40% | Berapa hari dari 5 hari terakhir broker yang sama masuk Top 3 |
| Net Value | 20% | Log₁₀(total net buy rupiah) ÷ 12 |

### Cara Masuk Top 5
Saham dengan skor WAS tertinggi. Skornya naik kalau:
- **3 broker dominan beli besar** dan broker lain kecil-kecil (konsentrasi tinggi)
- **Broker yang sama** terus masuk Top 3 selama beberapa hari berturut-turut (persistence tinggi)
- **Nilai net buy hari ini besar** secara absolut (ratusan miliar ke atas)

### Tanda 🐳 Whale
Muncul emoji paus kalau `WAS > 0.60` DAN `konsentrasi > 0.65` — artinya benar-benar ada 1–3 broker yang borong dalam jumlah besar dan mendominasi.

---

## 2. 💧 MONEY FLOW (FS)

**Pertanyaan yang dijawab:** Saham mana yang net buy-nya paling tidak normal dibanding hari biasanya?

**Diranking berdasarkan:** Net buy rupiah hari ini (hanya yang positif ditampilkan)

### Cara Hitung
1. Hitung rata-rata net buy 10 hari terakhir sebagai baseline
2. Hitung rasio anomali: `net_buy_hari_ini ÷ rata-rata_10_hari`
3. Masukkan ke fungsi sigmoid untuk normalisasi 0–1
4. Kalau asing ikut net buy, skor naik +0.08

### Cara Masuk Top 5
Saham dengan net buy rupiah hari ini terbesar (hanya saham yang net buy-nya positif). Anomali `(+1.5x)` artinya net buy hari ini 1.5× lebih besar dari rata-rata 10 hari.

> **Catatan:** Anomali +1.0x = sama dengan rata-rata. Makin tinggi, makin tidak biasa.

---

## 3. 📈 SINYAL TEKNIKAL (TCN)

**Pertanyaan yang dijawab:** Saham mana yang paling banyak sinyal bullish dari indikator teknikal hari ini?

**Diranking berdasarkan:** Jumlah sinyal yang aktif (dari maksimal 10)

### 10 Sinyal yang Diperiksa

| Sinyal | Poin | Kondisi |
|--------|------|---------|
| MA | 1 | Harga di atas MA20 |
| Trend | 1 | MA20 di atas MA50 (uptrend) |
| Candle | 1 | Candle hijau (close > open) |
| RSI | 1 | RSI antara 50–70 (momentum bullish, belum overbought) |
| MACD | 1 | MACD line di atas signal line |
| Volume | **2** | Volume hari ini ≥ 1.5× rata-rata 5 hari (spike) |
| Support | 1 | Low hari ini tidak tembus support (low 20 hari) |
| Body | 1 | Candle body kuat — close dekat high (body ratio > 60%) |
| Stochastic | 1 | Stoch %K > %D dan belum overbought (< 80) |

### Cara Masuk Top 5
Saham dengan sinyal aktif terbanyak. Volume spike dapat 2 poin, jadi saham dengan volume meledak lebih mudah masuk.

---

## 4. 🔍 STEALTH ACCUMULATION (SAD)

**Pertanyaan yang dijawab:** Saham mana yang diam-diam diakumulasi broker selama 5 hari terakhir, tapi harganya belum bergerak banyak?

**Ini sinyal pre-breakout** — harga masih sideways tapi ada aktivitas beli tersembunyi.

### Kondisi Wajib (Semua Harus Terpenuhi)

| Kondisi | Nilai |
|---------|-------|
| Range harga 5 hari | < 10% (harga sideways, tidak kemana-mana) |
| Volume rata-rata 5 hari vs 20 hari | > 60% (masih ada aktivitas, tidak sepi) |
| Hari net buy positif dari 5 hari | ≥ 2 hari |

### Cara Masuk Top 5
Saham yang **lolos ketiga kondisi di atas**, diranking berdasarkan gabungan streak hari (persistence dari WAS) dan total net buy kumulatif 5 hari. Saham dengan streak panjang dan net buy konsisten ada di atas.

> **Mengapa sering kosong?** Di market bearish/trending turun, harga saham aktif bergerak (range > 10%) sehingga tidak memenuhi syarat sideways. SAD paling banyak sinyal di market sideways atau konsolidasi.

---

## 5. 🎯 WATCHLIST (CFS)

**Pertanyaan yang dijawab:** Saham mana yang paling layak diperhatikan hari ini — gabungan semua sinyal?

**Diranking berdasarkan:** Composite Final Score (CFS), gabungan tertimbang semua formula

### Bobot

| Formula | Bobot |
|---------|-------|
| WAS (Whale) | 35% |
| FS (Flow) | 30% |
| TCN (Teknikal) | 25% |
| SAD (Stealth) | 10% |

### Pre-filter (Saham Dikeluarkan Jika)
- Volume rupiah hari ini < 500 juta → saham terlalu sepi
- Harga < Rp100 → saham gorengan / tidak liquid

### Label
| Label | CFS |
|-------|-----|
| 🟢 STRONG BUY | ≥ 0.65 |
| 🔵 BUY | ≥ 0.50 |
| ⚪ WATCH | ≥ 0.40 |

### Cara Masuk Top 5
Saham yang lolos pre-filter dengan CFS tertinggi. Saham ideal: ada aksi beli besar dari broker (WAS tinggi), net buy anomali (FS tinggi), dan sinyal teknikal mendukung (TCN tinggi). Bonus kalau SAD aktif (⭐ Stealth).

---

## Ringkasan Cepat

| Alert | Pertanyaan Utama | Diranking By |
|-------|-----------------|--------------|
| 🐳 WAS | Broker mana yang borong? | Skor WAS (konsentrasi × persistence × nilai) |
| 💧 FS | Net buy hari ini anomali? | Net buy rupiah terbesar |
| 📈 TCN | Berapa sinyal bullish aktif? | Jumlah sinyal (maks 10) |
| 🔍 SAD | Akumulasi tersembunyi? | Streak + net buy kumulatif 5 hari |
| 🎯 CFS | Gabungan terbaik? | Skor gabungan 35/30/25/10 |

> **Disclaimer:** Semua sinyal ini bersifat kuantitatif berbasis data historis dan broksum. Bukan rekomendasi beli/jual. DYOR.
