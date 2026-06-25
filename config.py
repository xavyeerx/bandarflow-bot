"""
config.py — Konfigurasi terpusat IDX Bandarmology Bot
Isi file .env dengan nilai yang benar sebelum menjalankan bot.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# ─── Stockbit ─────────────────────────────────────────────────────────────────
# Cara ambil token:
# 1. Buka https://stockbit.com → Login
# 2. F12 → tab Network → klik salah satu request ke exodus.stockbit.com
# 3. Headers → cari 'Authorization: Bearer eyJ...'
# 4. Copy token (tanpa kata 'Bearer ')
STOCKBIT_TOKEN = os.getenv("STOCKBIT_TOKEN", "YOUR_STOCKBIT_TOKEN_HERE")

# ─── Database ─────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/broksum.db")

# ─── Scraping ─────────────────────────────────────────────────────────────────
# Delay antar request RTI (detik) — jangan terlalu cepat, hindari rate limit
DELAY_BETWEEN_REQUEST = float(os.getenv("DELAY_BETWEEN_REQUEST", "1.5"))
MAX_RETRY             = int(os.getenv("MAX_RETRY", "3"))
REQUEST_TIMEOUT       = int(os.getenv("REQUEST_TIMEOUT", "15"))

# Header browser biasa agar tidak diblokir IDX / RTI
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://idx.co.id/",
}

# ─── IDX API Endpoints ────────────────────────────────────────────────────────
IDX_BASE_URL = "https://idx.co.id/api/cluster"
IDX_STOCK_LIST_URL      = f"{IDX_BASE_URL}/StockData/GetStockList"
IDX_STOCK_SUMMARY_URL   = f"{IDX_BASE_URL}/StockData/GetStockSummary"
IDX_TRADING_SUMMARY_URL = f"{IDX_BASE_URL}/Stock/GetTradingSummary"
IDX_COMPOSITE_URL       = f"{IDX_BASE_URL}/Composite/GetCompositeIndex"

# ─── RTI Broker Summary ───────────────────────────────────────────────────────
RTI_BROKSUM_URL = "https://www.rti.co.id/ver2/rti_brokersummary_new.php"

# ─── yfinance ─────────────────────────────────────────────────────────────────
YFINANCE_PERIOD   = "60d"
YFINANCE_INTERVAL = "1d"
YFINANCE_SUFFIX   = ".JK"   # suffix saham BEI di yfinance

# ─── Scoring Thresholds ───────────────────────────────────────────────────────
# WAS
WAS_WHALE_THRESHOLD       = 0.60
WAS_KONSENTRASI_THRESHOLD = 0.65

# FS booster
FS_FOREIGN_BOOSTER = 0.08

# TCN
TCN_VOLUME_SPIKE_RATIO = 1.5
TCN_BODY_RATIO_MIN     = 0.6

# SAD
SAD_PRICE_RANGE_MAX   = 0.10   # 10% — sideways longgar
SAD_VOL_RATIO_MIN     = 0.6    # 60% avg volume — cukup ada aktivitas
SAD_MIN_POSITIVE_DAYS = 2      # 2 dari 5 hari net buy positif

# CFS pre-filter
CFS_MIN_VOLUME_RUPIAH = 0.5e9   # 0.5 Miliar
CFS_MIN_PRICE         = 100

# CFS weights
W_WAS = 0.35
W_FS  = 0.30
W_TCN = 0.25
W_SAD = 0.10

# CFS labels
CFS_STRONG_BUY = 0.65
CFS_BUY        = 0.50
CFS_WATCH      = 0.40

# ─── Degraded data threshold ──────────────────────────────────────────────────
DEGRADED_THRESHOLD = 0.80  # jika < 80% emiten berhasil di-scrape → DEGRADED

# ─── DB rolling window ────────────────────────────────────────────────────────
DB_ROLLING_DAYS = 10

# ─── Telegram message delay ───────────────────────────────────────────────────
TELEGRAM_MESSAGE_DELAY = 1  # detik antar pesan

# ─── Top N untuk ranking ──────────────────────────────────────────────────────
TOP_N = 5
