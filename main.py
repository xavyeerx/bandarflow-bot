"""
main.py — Entry point IDX Bandarmology Screening Bot.

Usage:
    python main.py scrape_and_score   # 18.30 WIB: scraping + kalkulasi + simpan ke DB
    python main.py send               # 19.00 WIB: kirim laporan ke Telegram
    python main.py all                # jalankan keduanya sekaligus (untuk testing)
"""

import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path

# ─── Setup Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bandarmology.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ─── Import modules ───────────────────────────────────────────────────────────
import config
from data.db import init_db, save_daily_broksum, save_daily_summary, save_bandar_detector, purge_old_data
from data.db import get_broksum_ndays, get_net_buy_history, get_close_history, get_volume_history
from scraper.universe import get_stock_universe
from scraper.idx_scraper import scrape_all_stocks, get_foreign_flow_all, get_market_summary
from scraper.stockbit_scraper import scrape_all_broksum
from engine.indicators import get_all_indicators, prefetch_all_indicators
from engine.market_regime import detect_regime
from engine.scoring import score_one_stock
from bot.formatter import build_report_data
from bot.telegram_bot import run_send_report, send_error_notification

# Path untuk menyimpan hasil scoring (supaya cron send bisa baca tanpa scrape ulang)
REPORT_CACHE_PATH = Path("data/report_cache.json")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: Scrape + Score (18.30 WIB)
# ══════════════════════════════════════════════════════════════════════════════

def run_scrape_and_score() -> None:
    """
    1. Init DB
    2. Fetch universe (~952 saham)
    3. Scrape IDX OHLCV + foreign flow
    4. Scrape RTI broker summary (delay 1.5s per saham)
    5. Simpan ke SQLite
    6. Kalkulasi semua scoring formula
    7. Simpan hasil ke JSON cache untuk dikirim pukul 19.00
    """
    logger.info("=" * 60)
    logger.info("START: scrape_and_score — %s", date.today())
    logger.info("=" * 60)

    # ── Init DB ──
    init_db()
    purge_old_data()

    # ── Fetch universe ──
    logger.info("Fetching stock universe...")
    codes = get_stock_universe()
    universe_size = len(codes)
    logger.info("Universe: %d emiten", universe_size)

    today_str = date.today().strftime("%Y%m%d")
    today_db  = date.today().strftime("%Y-%m-%d")

    # ── Scrape IHSG market summary ──
    logger.info("Fetching IHSG market summary...")
    market_summary = get_market_summary()
    regime = detect_regime(market_summary)
    logger.info(
        "IHSG: %.0f (%.2f%%) | Regime: %s",
        market_summary.get("ihsg_level", 0),
        market_summary.get("ihsg_change_pct", 0),
        regime,
    )

    # ── Prefetch yfinance historis (1 batch request untuk semua saham) ──
    logger.info("Prefetch yfinance historis untuk %d saham...", universe_size)
    prefetch_all_indicators(codes)

    # ── Scrape IDX OHLCV (batch, cepat) ──
    logger.info("Scraping IDX OHLCV untuk %d saham...", universe_size)
    idx_data = scrape_all_stocks(codes)
    logger.info("IDX scrape: %d/%d berhasil", len(idx_data), universe_size)

    # ── Scrape foreign flow (satu request untuk semua) ──
    logger.info("Fetching foreign flow...")
    all_foreign = get_foreign_flow_all()

    # ── Scrape Stockbit broker summary + bandar detector ──
    logger.info("Scraping Stockbit broker summary (%d saham)...", universe_size)
    all_broksum, all_bandar = scrape_all_broksum(codes, today_str)
    emiten_scraped = len(all_broksum)
    logger.info("Stockbit scrape: %d/%d berhasil", emiten_scraped, universe_size)

    # ── Simpan ke SQLite ──
    logger.info("Menyimpan data ke SQLite...")
    for code in codes:
        broksum = all_broksum.get(code, [])
        if broksum:
            save_daily_broksum(code, today_db, broksum)

        bandar_info = all_bandar.get(code)
        if bandar_info:
            save_bandar_detector(code, today_db, bandar_info)

        ohlcv = idx_data.get(code)
        if ohlcv:
            ohlcv["foreign_net_buy"] = all_foreign.get(code, 0.0)
            ohlcv["net_buy_total"] = sum(
                float(b.get("net_value", 0) or 0) for b in broksum
            )
            save_daily_summary(code, today_db, ohlcv)

    logger.info("Data tersimpan ke SQLite.")

    # ── Kalkulasi scoring ──
    logger.info("Kalkulasi scoring untuk semua saham...")
    all_scores = []

    for code in codes:
        try:
            ohlcv_today   = idx_data.get(code)
            broksum_today = all_broksum.get(code, [])
            broksum_5d    = get_broksum_ndays(code, days=5)
            net_buy_10d   = get_net_buy_history(code, days=10)
            foreign_nb    = all_foreign.get(code, 0.0)
            close_5d      = get_close_history(code, days=5)
            volume_5d     = get_volume_history(code, days=5)
            volume_20d    = get_volume_history(code, days=20)
            net_buy_5d    = get_net_buy_history(code, days=5)
            avg_vol_20d   = sum(volume_20d) / len(volume_20d) if volume_20d else 0

            # Indikator teknikal dari yfinance (bisa lambat, tapi dijalankan batch)
            indicators = get_all_indicators(code)

            result = score_one_stock(
                code=code,
                broksum_ndays=broksum_5d,
                broksum_today=broksum_today,
                net_buy_10d=net_buy_10d,
                foreign_net_buy=foreign_nb,
                indicators=indicators,
                close_5d=close_5d,
                volume_5d=volume_5d,
                avg_vol_20d=avg_vol_20d,
                net_buy_5d=net_buy_5d,
                ohlcv_today=ohlcv_today,
            )
            all_scores.append(result)

        except Exception as e:
            logger.error("Scoring error untuk %s: %s", code, e, exc_info=True)

    logger.info("Scoring selesai: %d saham", len(all_scores))

    # ── Build report data ──
    report_data = build_report_data(
        all_scores=all_scores,
        market_summary=market_summary,
        regime=regime,
        universe_size=universe_size,
        emiten_scraped=emiten_scraped,
    )

    # ── Simpan cache untuk send ──
    REPORT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_CACHE_PATH, "w", encoding="utf-8") as f:
        # Konversi ke JSON-serializable (hapus objek non-serializable)
        json.dump(_make_serializable(report_data), f, ensure_ascii=False, indent=2)

    logger.info("Report cache disimpan: %s", REPORT_CACHE_PATH)

    # Notif jika data degraded
    if report_data["data_status"] == "DEGRADED":
        logger.warning("DATA DEGRADED: hanya %d/%d emiten berhasil di-scrape", emiten_scraped, universe_size)

    # Jika scraping total gagal
    if emiten_scraped == 0:
        asyncio.run(send_error_notification(
            "❌ Scraping gagal total\\. Cek log VM\\."
        ))

    logger.info("scrape_and_score SELESAI.")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: Send to Telegram (19.00 WIB)
# ══════════════════════════════════════════════════════════════════════════════

def run_send() -> None:
    """
    Baca JSON cache dari scrape_and_score, lalu kirim 7 pesan ke Telegram.
    """
    logger.info("=" * 60)
    logger.info("START: send — %s", date.today())
    logger.info("=" * 60)

    if not REPORT_CACHE_PATH.exists():
        logger.error("Report cache tidak ditemukan: %s", REPORT_CACHE_PATH)
        asyncio.run(send_error_notification(
            "❌ Report cache tidak ditemukan\\. Apakah scrape\\_and\\_score sudah jalan\\?"
        ))
        return

    with open(REPORT_CACHE_PATH, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    logger.info("Report cache dimuat. Mengirim ke Telegram...")
    success = run_send_report(report_data)

    if success:
        logger.info("✅ Semua pesan berhasil dikirim ke Telegram.")
    else:
        logger.error("❌ Ada pesan yang gagal dikirim.")


# ══════════════════════════════════════════════════════════════════════════════
# Utils
# ══════════════════════════════════════════════════════════════════════════════

def _make_serializable(obj):
    """Rekursif konversi ke JSON-safe types."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    elif isinstance(obj, (int, float, bool, str)) or obj is None:
        return obj
    else:
        return str(obj)


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "scrape_and_score":
        run_scrape_and_score()
    elif command == "send":
        run_send()
    elif command == "all":
        run_scrape_and_score()
        run_send()
    else:
        print(f"❌ Command tidak dikenal: {command}")
        print("Gunakan: scrape_and_score | send | all")
        sys.exit(1)
