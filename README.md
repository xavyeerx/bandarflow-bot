# IDX Bandarmology Screening Bot 🐳

Bot screening saham otomatis berbasis **Bandarmology** untuk BEI (Bursa Efek Indonesia).
Berjalan setiap hari Senin–Jumat, scraping data broker summary setelah jam 18.30 WIB,
kalkulasi scoring, dan kirim laporan terstruktur ke Telegram jam 19.00 WIB.

---

## Arsitektur

```
[18.30] Cron → scrape_and_score
                ├── IDX hidden API  → OHLCV + Foreign Flow (~952 saham)
                ├── RTI.co.id       → Broker Summary (delay 1.5s/saham ≈ 24 menit)
                ├── yfinance        → Historis 60 hari (MA, RSI, MACD, Stochastic)
                └── SQLite          → Rolling 10 hari

[19.00] Cron → send
                └── Telegram Bot API → 7 pesan terstruktur
```

## Formula Scoring

| Formula | Keterangan | Bobot CFS |
|---------|-----------|-----------|
| **WAS** | Whale Accumulation Score — konsentrasi & persistence broker besar | 35% |
| **FS**  | Flow Score — lonjakan net buy vs baseline 10 hari + foreign booster | 30% |
| **TCN** | Technical Confluence Number — 10 indikator teknikal bullish | 25% |
| **SAD** | Stealth Accumulation Detector — Wyckoff, harga sideways + broker diam beli | 10% |
| **WTF** | Wash Trade Filter — filter pump & dump sebelum masuk scoring | pre-filter |
| **CFS** | Composite Final Score — gabungan semua formula | ranking |

---

## Struktur Folder

```
bandarmology-bot/
├── scraper/
│   ├── universe.py        # Daftar ~952 emiten aktif dari IDX
│   ├── idx_scraper.py     # OHLCV + foreign flow dari IDX hidden API
│   └── rti_scraper.py     # Broker summary dari RTI.co.id
├── engine/
│   ├── scoring.py         # Semua formula: WAS, FS, TCN, SAD, WTF, CFS
│   ├── indicators.py      # RSI, MACD, MA, Stochastic via yfinance
│   └── market_regime.py   # Deteksi kondisi IHSG
├── bot/
│   ├── telegram_bot.py    # Kirim laporan ke Telegram
│   └── formatter.py       # Format 7 pesan + format_rupiah()
├── data/
│   ├── db.py              # SQLite manager
│   └── broksum.db         # Database (auto-created)
├── config.py              # Semua konfigurasi
├── main.py                # Entry point
├── requirements.txt
├── .env.example           # Template environment variables
└── bandarmology.log       # Log file (auto-created)
```

---

## Setup & Instalasi

### 1. Clone / copy folder ke VM

```bash
# Di GCP e2-micro atau server Linux
git clone <repo> /home/user/bandarmology-bot
cd /home/user/bandarmology-bot
```

### 2. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Konfigurasi Telegram Bot

1. Buka [@BotFather](https://t.me/BotFather) di Telegram
2. Buat bot baru: `/newbot`
3. Salin **Bot Token**
4. Tambahkan bot ke channel/group
5. Dapatkan **Chat ID**:
   - Untuk channel: `@nama_channel` atau ID numerik (contoh: `-1001234567890`)
   - Untuk grup biasa: ID numerik negatif
   - Cara cek Chat ID: kirim pesan ke group, lalu buka `https://api.telegram.org/bot<TOKEN>/getUpdates`

### 4. Buat file `.env`

```bash
cp .env.example .env
nano .env
```

Isi dengan nilai yang benar:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
TELEGRAM_CHAT_ID=-1001234567890
```

### 5. Test manual

```bash
# Test scraping + scoring
python3 main.py scrape_and_score

# Test kirim ke Telegram
python3 main.py send

# Keduanya sekaligus (untuk testing)
python3 main.py all
```

---

## Setup Cron (Produksi)

```bash
# Pastikan timezone VM sudah benar
sudo timedatectl set-timezone Asia/Jakarta

# Edit crontab
crontab -e
```

Tambahkan baris berikut:

```cron
# 18.30 WIB — scraping + scoring (data broksum sudah final)
30 18 * * 1-5 cd /home/user/bandarmology-bot && python3 main.py scrape_and_score >> /home/user/bandarmology-bot/cron.log 2>&1

# 19.00 WIB — kirim laporan ke Telegram
00 19 * * 1-5 cd /home/user/bandarmology-bot && python3 main.py send >> /home/user/bandarmology-bot/cron.log 2>&1
```

---

## Format Output Telegram

Bot mengirim **7 pesan** berurutan ke channel/group:

| # | Pesan | Konten |
|---|-------|--------|
| 1 | Header | Tanggal, universe, market regime IHSG |
| 2 | Top 5 WAS | Whale Accumulation (konsentrasi broker besar) |
| 3 | Top 5 FS | Flow Score (lonjakan net buy vs baseline) |
| 4 | Top 5 TCN | Technical Confluence (10 indikator bullish) |
| 5 | Top 5 SAD | Stealth Accumulation (kandidat pre-breakout) |
| 6 | WTF Warning | Saham dengan indikasi wash trade — HINDARI |
| 7 | Watchlist CFS | Ranking final + sinyal STRONG BUY / BUY / WATCH |

---

## Troubleshooting

### RTI endpoint berubah

Inspect Network tab browser (F12) di `rti.co.id`, cari request ke `rti_brokersummary_new.php`.
Update `RTI_BROKSUM_URL` di `config.py`.

### IDX API berubah

Cek Network tab di `idx.co.id`, update endpoint yang berubah di `config.py`.

### Data DEGRADED

Jika < 80% emiten berhasil di-scrape, header menampilkan `⚠️ DEGRADED`.
Cek `bandarmology.log` untuk detail error per saham.

### yfinance timeout

yfinance sesekali lambat. Bot akan skip indikator teknikal dan TCN=0 untuk saham tersebut.
Tidak mempengaruhi WAS, FS, SAD.

---

## Catatan Penting

> ⚠️ **Bukan rekomendasi beli/jual. DYOR.**
> Bot ini hanya alat bantu analisis teknikal + bandarmologi. Keputusan investasi sepenuhnya tanggung jawab pengguna.

---

## Dependencies

| Library | Versi | Fungsi |
|---------|-------|--------|
| requests | ≥2.31 | HTTP scraping IDX + RTI |
| pandas | ≥2.1 | Manipulasi data |
| numpy | ≥1.26 | Kalkulasi statistik |
| yfinance | ≥0.2.40 | Data historis 60 hari |
| pandas-ta | ≥0.3.14b | MACD, Stochastic |
| python-telegram-bot | 20.* | Kirim pesan Telegram |
| python-dotenv | ≥1.0 | Load .env |
| sqlite3 | bawaan Python | Database |
