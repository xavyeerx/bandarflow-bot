"""
test_full.py — Testing full universe (~900+ saham IDX).

Estimasi waktu:
  - yfinance prefetch batch    : ~30 detik (1 request)
  - Stockbit scraping 900 saham: ~20-25 menit (1.0s delay)
  - Scoring                    : ~1-2 menit
  Total                        : ~25-30 menit

Jalankan:
    python test_full.py
"""

import logging
import sys
import os
from datetime import date

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("test_full.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

import config
from data.db import (
    init_db, purge_old_data,
    save_daily_broksum, save_daily_summary, save_bandar_detector,
    get_broksum_ndays, get_net_buy_history, get_close_history, get_volume_history,
)
from scraper.universe import get_stock_universe
from scraper.idx_scraper import scrape_all_stocks, get_foreign_flow_all, get_market_summary
from scraper.stockbit_scraper import scrape_all_broksum
from engine.indicators import get_all_indicators, prefetch_all_indicators
from engine.market_regime import detect_regime
from engine.scoring import score_one_stock
from bot.formatter import (
    build_report_data,
    format_header,
    format_top5_was,
    format_top5_fs,
    format_top5_tcn,
    format_top5_sad,
    format_wtf_warning,
    format_watchlist_cfs,
)


def print_sep(char="=", w=60):
    print(char * w)


def print_section(title):
    print()
    print_sep("-")
    print(f"  {title}")
    print_sep("-")


def strip_md(text: str) -> str:
    for ch in ["*", "\\_", "\\-", "\\.", "\\&", "\\(", "\\)", "\\!", "\\>", "\\<", "\\=", "\\+", "\\#", "\\{", "\\}"]:
        text = text.replace(ch, ch[-1] if len(ch) > 1 else "")
    return text


def print_report(data: dict):
    reports = [
        ("[1/7] HEADER",               format_header(data)),
        ("[2/7] TOP 5 WHALE (WAS)",    format_top5_was(data.get("was_ranking", []))),
        ("[3/7] TOP 5 FLOW (FS)",      format_top5_fs(data.get("fs_ranking", []))),
        ("[4/7] TOP 5 TEKNIKAL (TCN)", format_top5_tcn(data.get("tcn_ranking", []))),
        ("[5/7] TOP 5 STEALTH (SAD)",  format_top5_sad(data.get("sad_ranking", []))),
        ("[6/7] WASH TRADE WARNING",   format_wtf_warning(data.get("wash_list", []))),
        ("[7/7] WATCHLIST CFS",        format_watchlist_cfs(data.get("cfs_ranking", []))),
    ]
    for title, text in reports:
        print_section(title)
        print(strip_md(text))
    print()
    print_sep("-")
    print("[OK] Laporan selesai.")
    print_sep("-")


def main():
    print_sep("=")
    print("  IDX BANDARMOLOGY BOT -- FULL UNIVERSE TEST")
    print(f"  Tanggal : {date.today()}")
    print("  Output  : Terminal + test_full.log (tidak kirim Telegram)")
    print_sep("=")

    today_str = date.today().strftime("%Y%m%d")
    today_db  = date.today().strftime("%Y-%m-%d")

    # ── 1. Init DB ──
    print("\n[1/7] Inisialisasi database...")
    init_db()
    purge_old_data()
    print("     ✓ SQLite siap.")

    # ── 2. Universe ──
    print("\n[2/7] Fetching stock universe dari IDX...")
    codes = get_stock_universe()
    n = len(codes)
    print(f"     ✓ Universe: {n} emiten")

    # ── 3. Market Summary ──
    print("\n[3/7] Fetching IHSG market summary...")
    market_summary = get_market_summary()
    regime         = detect_regime(market_summary)
    print(f"     ✓ IHSG: {market_summary.get('ihsg_level',0):,.0f} "
          f"({market_summary.get('ihsg_change_pct',0):+.2f}%) | Regime: {regime}")

    # ── 4. Prefetch yfinance (batch, 1 request) ──
    print(f"\n[4/7] Prefetch yfinance historis untuk {n} saham (batch)...")
    cached = prefetch_all_indicators(codes)
    print(f"     ✓ yfinance cache: {cached}/{n} saham")

    # ── 5. IDX OHLCV + Foreign Flow ──
    print(f"\n[5/7] Scraping IDX OHLCV + foreign flow...")
    idx_data    = scrape_all_stocks(codes)
    all_foreign = get_foreign_flow_all()
    print(f"     ✓ OHLCV: {len(idx_data)}/{n} | Foreign: {len(all_foreign)} saham")

    # ── 6. Stockbit Broker Summary ──
    config.DELAY_BETWEEN_REQUEST = 1.0
    eta = n * config.DELAY_BETWEEN_REQUEST / 60
    print(f"\n[6/7] Scraping Stockbit ({n} saham × {config.DELAY_BETWEEN_REQUEST}s ~ {eta:.0f} menit)...")
    print("      Log progress setiap 50 saham. Silakan tunggu...")

    all_broksum, all_bandar = scrape_all_broksum(codes, today_str)
    emiten_scraped = len(all_broksum)
    print(f"     ✓ Stockbit: {emiten_scraped}/{n} berhasil")

    # ── Simpan ke DB ──
    print("\n     Menyimpan ke SQLite...")
    for code in codes:
        broksum = all_broksum.get(code, [])
        if broksum:
            save_daily_broksum(code, today_db, broksum)
        bd = all_bandar.get(code)
        if bd:
            save_bandar_detector(code, today_db, bd)
        ohlcv = idx_data.get(code)
        if ohlcv:
            ohlcv["foreign_net_buy"] = all_foreign.get(code, 0.0)
            ohlcv["net_buy_total"]   = sum(float(b.get("net_value", 0) or 0) for b in broksum)
            save_daily_summary(code, today_db, ohlcv)
    print("     ✓ Data tersimpan.")

    # ── 7. Scoring ──
    print(f"\n[7/7] Kalkulasi scoring ({n} saham)...")
    all_scores = []
    errors = 0

    for i, code in enumerate(codes, 1):
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
            indicators    = get_all_indicators(code)

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

            cfs   = result["cfs"]["cfs"]
            label = result["cfs"]["label"]
            was   = result["was"]["was"]
            tcn   = result["tcn"]["tcn"]

            # Print hanya saham yang menarik (CFS >= 0.65) atau setiap 100 saham
            if cfs >= 0.65 or i % 100 == 0:
                print(f"  [{i:3d}/{n}] {code:<6} CFS:{cfs:.2f} [{label:<10}] WAS:{was:.2f} TCN:{tcn:.2f}")

        except Exception as e:
            errors += 1
            logger.error("Scoring error %s: %s", code, e)

    print(f"\n     ✓ Scoring selesai: {len(all_scores)} saham | Error: {errors}")

    # ── Build & Print Report ──
    report_data = build_report_data(
        all_scores=all_scores,
        market_summary=market_summary,
        regime=regime,
        universe_size=n,
        emiten_scraped=emiten_scraped,
    )

    print("\n\n")
    print_sep("#")
    print("  LAPORAN SCREENING BANDARMOLOGY — FULL UNIVERSE")
    print_sep("#")
    print_report(report_data)

    # Summary stats
    strong_buy = sum(1 for s in all_scores if s["cfs"]["label"] == "STRONG BUY")
    buy        = sum(1 for s in all_scores if s["cfs"]["label"] == "BUY")
    skip       = sum(1 for s in all_scores if s["cfs"]["label"] == "SKIP")
    print(f"\nStats: STRONG BUY={strong_buy} | BUY={buy} | SKIP={skip} | Error={errors}")
    print(f"Log lengkap tersimpan di: test_full.log")


if __name__ == "__main__":
    main()
