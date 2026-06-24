PRD: IDX Bandarmology Screening Bot
Version: 1.0 | Status: Draft | Stack: Python 3.11 | SQLite | cron | Telegram Bot API | GCP e2-micro (free)

1. Overview
Bot screening saham otomatis berbasis Bandarmology yang berjalan setiap hari Senin-Jumat. Scraping data broker summary (broksum) dari sumber gratis setelah data final tersedia jam 18.30 WIB, kalkulasi scoring engine, lalu kirim laporan terstruktur ke Telegram jam 19.00 WIB.
Tujuan: Membantu trader retail mendeteksi jejak akumulasi institusi/bandar di saham BEI secara otomatis, gratis, dan konsisten setiap malam.

2. Arsitektur Sistem
[18.30 WIB] Cron trigger → scrape_and_score
     ↓
[IDX hidden API]  → OHLCV, Foreign Flow, daftar emiten (~952 saham)
[RTI.co.id]       → Broker Summary per saham (scraping)
[yfinance]        → Data historis 60 hari (MA, RSI, MACD, Stochastic)
     ↓
[SQLite]  → Simpan rolling 10 hari
     ↓
[Scoring Engine] → Kalkulasi WAS, FS, TCN, SAD, WTF, CFS
     ↓
[19.00 WIB] Cron trigger → send
     ↓
[Telegram Bot API] → 7 pesan terstruktur ke channel/group

3. Struktur Folder
bandarmology-bot/
├── scraper/
│   ├── idx_scraper.py       # OHLCV + foreign flow dari IDX
│   ├── rti_scraper.py       # Broker summary dari RTI
│   └── universe.py          # Daftar emiten aktif
├── engine/
│   ├── scoring.py           # Semua formula: WAS, FS, TCN, SAD, WTF, CFS
│   ├── indicators.py        # RSI, MACD, MA, Stochastic
│   └── market_regime.py     # Deteksi kondisi IHSG
├── bot/
│   ├── telegram_bot.py      # Kirim laporan
│   └── formatter.py         # Format teks + angka
├── data/
│   └── broksum.db           # SQLite database
├── config.py                # Token bot, chat ID, settings
└── main.py                  # Entry point: scrape_and_score | send

4. Sumber Data (Semua Gratis)
4.1 IDX Hidden API
Endpoint internal website idx.co.id, tidak perlu API key. Gunakan header User-Agent browser biasa.
# Daftar semua emiten aktif
GET https://idx.co.id/api/cluster/StockData/GetStockList

# OHLCV + summary per saham
GET https://idx.co.id/api/cluster/StockData/GetStockSummary?code=BBRI&language=id

# Foreign flow harian
GET https://idx.co.id/api/cluster/Stock/GetTradingSummary?indexCode=COMPOSITE&period=1D

# Market summary IHSG
GET https://idx.co.id/api/cluster/Composite/GetCompositeIndex
4.2 RTI Broker Summary
Scraping dari rti.co.id. Inspect Network tab browser (F12) jika endpoint berubah. Tambahkan delay 1-2 detik antar request.
GET https://www.rti.co.id/ver2/rti_brokersummary_new.php
    ?act=getbsbycode&code=BBRI&sdate=20260623&edate=20260623

# Response JSON fields:
# broker_code, buy_lot, sell_lot, net_lot, net_value (rupiah)
4.3 yfinance (Indikator Teknikal)
pythonimport yfinance as yf
df = yf.download("BBRI.JK", period="60d", interval="1d")
# Suffix .JK untuk saham BEI
# Gratis, tidak perlu API key

5. Format Angka (Wajib Konsisten di Semua Output)
Gunakan format Inggris: titik sebagai desimal, koma sebagai thousand separator. Suffix B/M/T untuk nilai rupiah.
pythondef format_rupiah(value_rupiah):
    abs_val = abs(value_rupiah)
    sign = "+" if value_rupiah >= 0 else "-"

    if abs_val >= 1_000_000_000_000:
        return f"{sign}{abs_val / 1_000_000_000_000:.1f}T"
    elif abs_val >= 1_000_000_000:
        return f"{sign}{abs_val / 1_000_000_000:.1f}B"
    elif abs_val >= 1_000_000:
        return f"{sign}{abs_val / 1_000_000:.1f}M"
    else:
        return f"{sign}{abs_val:,.0f}"

# Contoh:
# 45,700,000,000       → +45.7B
#    840,000,000       → +840.0M
# 28,400,000,000,000   → +28.4T

6. Formula Scoring
Formula 1: WAS — Whale Accumulation Score
Tujuan: Deteksi konsentrasi akumulasi oleh 1-3 broker besar (bandar).
Input data:

broksum_5d → data broker summary 5 hari terakhir per saham dari RTI
Fields per baris: broker_code, buy_lot, sell_lot, net_lot, net_value

Kalkulasi:
pythonimport math

# Step 1: Konsentrasi — top 3 broker net buy hari ini
top3_net_buy  = sorted(net_buy_per_broker, reverse=True)[:3]
net_buy_top3  = sum(top3_net_buy)
total_net_all = sum(abs(net) for net in net_buy_per_broker)
konsentrasi   = net_buy_top3 / total_net_all  # 0-1

# Step 2: Persistence — broker yang sama muncul di top 3 berapa hari?
# Bandingkan set top3 broker hari ini vs hari sebelumnya (5 hari)
persistence = jumlah_hari_top3_broker_sama / 5  # 0-1

# Step 3: Net value log-normalized
net_value_norm = math.log10(max(net_buy_total_rupiah, 1)) / 12  # 0-1

# Step 4: Final
WAS = (konsentrasi * 0.40) + (persistence * 0.40) + (net_value_norm * 0.20)

# Tag
is_whale = (WAS > 0.60 and konsentrasi > 0.65)
Output per saham:
WAS: 0.82
Konsentrasi: 81%
Persistence: 5/5 hari (streak 5d)
Net Buy: +45.7B
Broker: ZP AK BK
Tag: [WHALE]

Formula 2: FS — Flow Score
Tujuan: Ukur tekanan beli bersih hari ini vs baseline historis 10 hari. Deteksi lonjakan akumulasi yang abnormal.
Input data:

net_buy_today → net buy rupiah hari ini dari broksum RTI
net_buy_10d[] → array net buy 10 hari terakhir dari SQLite
foreign_net_buy → net buy asing hari ini dari IDX API

Kalkulasi:
pythonimport math
import numpy as np

# Step 1: Baseline
avg_net_10d = np.mean(net_buy_10d)

# Step 2: Rasio anomali hari ini vs baseline
if avg_net_10d != 0:
    anomali = net_buy_today / abs(avg_net_10d)
else:
    anomali = 1.0 if net_buy_today > 0 else -1.0

# Step 3: Normalisasi sigmoid ke 0-1
FS = 1 / (1 + math.exp(-anomali))

# Step 4: Booster jika asing juga net buy
if foreign_net_buy > 0:
    FS = min(FS + 0.08, 1.0)
Output per saham:
FS: 0.80
Net Buy Hari Ini: +45.7B
Avg Net 10d: +18.3B
Anomali: +2.5x baseline
Foreign: NET BUY (+booster aktif)

Formula 3: TCN — Technical Confluence Number
Tujuan: Hitung berapa banyak indikator teknikal yang align bullish sebagai konfirmasi sinyal bandarmology.
Input data:

close, open, high, low, volume → dari IDX API atau yfinance
MA20, MA50 → simple moving average 20 dan 50 hari
RSI → Relative Strength Index 14 hari
MACD, MACD_signal → dari pandas-ta
stoch_k, stoch_d → Stochastic %K dan %D
avg_vol_5d → rata-rata volume 5 hari
support_level → low terendah 20 hari

Kalkulasi:
pythonscore = 0

# Trend (3 poin)
if close > MA20:                     score += 1
if MA20 > MA50:                      score += 1
if close > open:                     score += 1  # candle hijau

# Momentum (2 poin)
if 50 < RSI < 70:                    score += 1  # zona sehat, bukan overbought
if MACD > MACD_signal:               score += 1  # golden cross

# Volume (2 poin)
if volume > avg_vol_5d * 1.5:        score += 2  # volume spike signifikan

# Price Action (2 poin)
if low >= support_level:             score += 1  # tidak tembus support
body_ratio = (close - low) / (high - low) if (high - low) > 0 else 0
if body_ratio > 0.6:                 score += 1  # close kuat di atas

# Stochastic (1 poin)
if stoch_k > stoch_d and stoch_k < 80: score += 1

TCN = score / 10  # normalisasi 0-1
Output per saham:
TCN: 0.70
Skor: 7/10
✅ MA  ✅ Trend  ✅ Candle  ✅ RSI(58)  ✅ MACD  ✅ Vol(1.8x)  ✅ Body
❌ Support  ❌ Stochastic

Formula 4: SAD — Stealth Accumulation Detector
Tujuan: Deteksi pola Wyckoff Accumulation — harga sideways tapi broker besar diam-diam beli. Sinyal pre-breakout untuk swing trade 3-10 hari.
Input data:

close_5d[] → harga close 5 hari terakhir
volume_5d[] → volume 5 hari terakhir
avg_vol_20d → rata-rata volume 20 hari
net_buy_5d[] → net buy broksum per hari, 5 hari terakhir (dari SQLite)

Kalkulasi:
pythonimport numpy as np

# Step 1: Harga sideways?
price_range = (max(close_5d) - min(close_5d)) / min(close_5d)

# Step 2: Volume tetap tinggi?
avg_vol_5d = np.mean(volume_5d)
vol_ratio  = avg_vol_5d / avg_vol_20d

# Step 3: Net buy konsisten?
positive_days  = sum(1 for nb in net_buy_5d if nb > 0)
cum_net_buy_5d = sum(net_buy_5d)

# Step 4: Semua kondisi harus terpenuhi (binary)
SAD = 1 if (
    price_range < 0.04 and    # harga gerak < 4% → sideways
    vol_ratio > 1.2 and        # volume naik vs rata-rata
    positive_days >= 4 and     # net buy minimal 4 dari 5 hari
    cum_net_buy_5d > 0         # kumulatif net positif
) else 0
Output per saham:
SAD: 1 (DETECTED)
Price Range 5d: 2.1% (< 4% ✅)
Vol Ratio: 1.9x avg (> 1.2 ✅)
Net Buy Days: 5/5 (>= 4 ✅)
Cum Net Buy: +29.9B ✅
→ Wyckoff Accumulation Phase B-C

Formula 5: WTF — Wash Trade Filter
Tujuan: Deteksi transaksi mencurigakan (wash trade / pump & dump). Saham dengan WTF risk HIGH dikeluarkan dari watchlist dan ditampilkan sebagai warning.
Input data:

broksum_today → data broksum hari ini semua broker dari RTI
Fields: broker_code, buy_lot, sell_lot

Kalkulasi:
pythontotal_volume = sum(b.buy_lot + b.sell_lot for b in broksum_today)
wash_volume  = 0

for broker in broksum_today:
    if broker.buy_lot > 0 and broker.sell_lot > 0:
        smaller = min(broker.buy_lot, broker.sell_lot)
        larger  = max(broker.buy_lot, broker.sell_lot)
        if smaller / larger > 0.30:  # broker bolak-balik > 30%
            wash_volume += (smaller * 2)

wash_score = wash_volume / total_volume if total_volume > 0 else 0

if wash_score < 0.15:    risk = "LOW"       # aman, lanjut scoring
elif wash_score < 0.30:  risk = "MODERATE"  # hati-hati
else:                    risk = "HIGH"      # difilter, masuk warning
Output per saham:
WTF Risk: LOW (wash_score: 0.08)   → lolos ke scoring

# atau:
WTF Risk: HIGH (wash_score: 0.41)  → difilter, masuk WARNING section

Formula Final: CFS — Composite Final Score
Tujuan: Gabungkan semua formula menjadi satu skor untuk ranking akhir Watchlist.
Pre-filter (wajib lolos semua sebelum masuk scoring CFS):
pythonlolos = (
    risk != "HIGH" and              # bukan wash trade tinggi
    volume_rupiah_hari_ini > 0.5e9 and  # min 0.5B (likuid)
    close > 100 and                  # harga > Rp 100
    net_buy_today > 0                # net buy positif hari ini
)
Kalkulasi CFS:
pythonW_WAS = 0.35
W_FS  = 0.30
W_TCN = 0.25
W_SAD = 0.10  # bonus binary

CFS = (WAS * W_WAS) + (FS * W_FS) + (TCN * W_TCN) + (SAD * W_SAD)

if CFS >= 0.65:    label = "STRONG BUY"
elif CFS >= 0.50:  label = "BUY"
elif CFS >= 0.40:  label = "WATCH"
else:              label = "SKIP"

7. Format Output Telegram
7 pesan dikirim berurutan. Delay 1 detik antar pesan agar tidak kena rate limit.

Pesan 1 — Header
📊 DAILY SCREENING REPORT
📅 2026-06-23 | Universe: 952 emiten
🔬 Flow + TCN + Bandarmology

🌡 Market Regime: BULLISH
IHSG: 7,234 (+0.8%) | Vol: 28.4T
📦 Data: ✅ FULL
🐳 Whale Signals: 6 saham
⚠️ Wash Trade Warning: 3 saham

Pesan 2 — Top 5 WAS
🐳 TOP 5 WHALE ACCUMULATION
Ranked by: WAS = konsentrasi(40%) + persistence(40%) + net value(20%)

1. PGEO  WAS:0.84 | Konsen:94% | Streak:6d | Net:+29.9B | Bkr:DX BK ZP
2. BBRI  WAS:0.82 | Konsen:81% | Streak:5d | Net:+45.7B | Bkr:ZP AK BK
3. MEDC  WAS:0.79 | Konsen:81% | Streak:6d | Net:+35.7B | Bkr:ZP AK HP
4. TLKM  WAS:0.75 | Konsen:76% | Streak:3d | Net:+32.1B | Bkr:YU ZP NI
5. ADMR  WAS:0.72 | Konsen:89% | Streak:6d | Net:+67.7B | Bkr:ZP YU DX

Pesan 3 — Top 5 FS
💧 TOP 5 FLOW SCORE
Ranked by: FS = sigmoid(net_buy_today / avg_10d) + foreign booster

1. ADRO  FS:0.88 | Net:+23.4B | Anomali:3.2x | Foreign:NET BUY ⬆️
2. AKRA  FS:0.85 | Net:+18.9B | Anomali:2.9x | Foreign:NEUTRAL
3. BBRI  FS:0.80 | Net:+45.7B | Anomali:2.5x | Foreign:NET BUY ⬆️
4. PGEO  FS:0.79 | Net:+29.9B | Anomali:2.3x | Foreign:NEUTRAL
5. AALI  FS:0.76 | Net:+19.3B | Anomali:2.1x | Foreign:NEUTRAL

Pesan 4 — Top 5 TCN
📈 TOP 5 TECHNICAL CONFLUENCE
Ranked by: TCN = jumlah sinyal bullish dari 10 indikator

1. KLBF  TCN:0.80 | 8/10 | ✅MA ✅Trend ✅RSI(55) ✅MACD ✅Vol(2.1x) ✅Body
2. MEDC  TCN:0.70 | 7/10 | ✅MA ✅Trend ✅RSI(58) ✅MACD ✅Vol(1.7x)
3. AALI  TCN:0.70 | 7/10 | ✅MA ✅Trend ✅RSI(61) ✅Vol(1.6x) ✅Body
4. BBRI  TCN:0.62 | 6/10 | ✅MA ✅Trend ✅MACD ✅Vol(2.1x)
5. ESSA  TCN:0.60 | 6/10 | ✅MA ✅RSI(53) ✅MACD ✅Vol(1.4x) ✅Body

Pesan 5 — Top 5 SAD
🔍 TOP 5 STEALTH ACCUMULATION
Ranked by: streak terpanjang + cum net buy terbesar
Sinyal pre-breakout — harga sideways, broker diam-diam beli

1. PGEO  Streak:6d | Range:2.1% | Vol:1.9x | CumNet:+29.9B | Days:5/5
2. MEDC  Streak:6d | Range:2.8% | Vol:1.7x | CumNet:+35.7B | Days:5/5
3. ADMR  Streak:6d | Range:3.1% | Vol:1.5x | CumNet:+67.7B | Days:4/5
4. AALI  Streak:5d | Range:3.0% | Vol:1.6x | CumNet:+19.3B | Days:5/5
5. ESSA  Streak:4d | Range:2.4% | Vol:1.4x | CumNet:+11.2B | Days:4/5

Pesan 6 — WTF Warning
⚠️ WASH TRADE WARNING
Saham berikut terdeteksi transaksi mencurigakan — HINDARI

1. MINA  Wash:41% | Risk:HIGH     | Flow:0.50
2. CYBR  Wash:34% | Risk:HIGH     | Flow:0.52
3. ARCI  Wash:28% | Risk:MODERATE | Flow:0.65

⚠️ Flow tinggi + wash tinggi = jebakan pump & dump

Pesan 7 — Watchlist Top 5 CFS (Pesan Terakhir)
🎯 WATCHLIST — TOP 5 RANKING CFS
Bobot: WAS(35%) + FS(30%) + TCN(25%) + SAD(10%)
Pre-filter: wash < 30% | vol > 0.5B | harga > 100 | net buy > 0

━━━━━━━━━━━━━━━━━━━━━━━━━
1. 🐳 BBRI  [STRONG BUY]  CFS:0.745
   WAS:0.82 | FS:0.80 | TCN:0.62 | SAD:✅
   Bkr:ZP AK BK | Vol:2.1x | Net:+45.7B | Streak:5d

2. 🐳 PGEO  [BUY]         CFS:0.720
   WAS:0.84 | FS:0.79 | TCN:0.55 | SAD:✅
   Bkr:DX BK ZP | Vol:1.9x | Net:+29.9B | Streak:6d
   ⭐ Stealth 6d — kandidat breakout

3. 🐳 MEDC  [BUY]         CFS:0.705
   WAS:0.79 | FS:0.69 | TCN:0.70 | SAD:✅
   Bkr:ZP AK HP | Vol:1.7x | Net:+35.7B | Streak:6d

4. 🐳 TLKM  [BUY]         CFS:0.668
   WAS:0.75 | FS:0.74 | TCN:0.58 | SAD:❌
   Bkr:YU ZP NI | Vol:1.8x | Net:+32.1B | Streak:3d

5. 🐳 AALI  [BUY]         CFS:0.649
   WAS:0.68 | FS:0.76 | TCN:0.70 | SAD:✅
   Bkr:ZP YU AG | Vol:1.6x | Net:+19.3B | Streak:5d

━━━━━━━━━━━━━━━━━━━━━━━━━
📌 Bukan rekomendasi beli/jual. DYOR.

8. Logika Pengiriman Bot
pythonasync def send_report(bot, chat_id, data):
    messages = [
        format_header(data),
        format_top5_was(data['was_ranking']),
        format_top5_fs(data['fs_ranking']),
        format_top5_tcn(data['tcn_ranking']),
        format_top5_sad(data['sad_ranking']),
        format_wtf_warning(data['wash_list']),
        format_watchlist_cfs(data['cfs_ranking']),  # selalu terakhir
    ]
    for msg in messages:
        await bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode='Markdown'
        )
        await asyncio.sleep(1)

9. Cron Setup
bash# Edit: crontab -e
# Pastikan timezone VM: sudo timedatectl set-timezone Asia/Jakarta

# 18.30 WIB — scraping + scoring (data broksum sudah final)
30 18 * * 1-5 python3 /home/user/bandarmology-bot/main.py scrape_and_score

# 19.00 WIB — kirim laporan ke Telegram
00 19 * * 1-5 python3 /home/user/bandarmology-bot/main.py send

10. Dependencies
requests
selenium
pandas
numpy
yfinance
pandas-ta
python-telegram-bot==20.*
sqlite3 sudah bawaan Python, tidak perlu install.

11. Error Handling
python# Jika scraping gagal sebagian → flag di header
if emiten_scraped < universe * 0.80:
    data_status = "DEGRADED"  # tampil di header pesan 1
else:
    data_status = "FULL"

# Jika scraping total gagal → kirim notif error ke Telegram
if emiten_scraped == 0:
    await bot.send_message(chat_id, "❌ Scraping gagal total. Cek log VM.")

# Retry logic untuk setiap request
MAX_RETRY = 3
DELAY_BETWEEN_REQUEST = 1.5  # detik, hindari rate limit RTI