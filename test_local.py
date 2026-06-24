"""
test_local.py — Mode testing lokal dengan universe LQ45.

Jalankan:
    python test_local.py

Fitur:
  - Pakai 45 saham LQ45 (bukan 952, jauh lebih cepat)
  - Output semua 7 laporan langsung ke terminal (TANPA kirim Telegram)
  - Progress bar sederhana di console
  - Tidak perlu file .env / token Telegram
"""

import logging
import sys
import os
from datetime import date

# Fix encoding untuk terminal Windows
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─── Logging ke terminal ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ─── Import modules ───────────────────────────────────────────────────────────
from data.db import init_db, save_daily_broksum, save_daily_summary, save_bandar_detector, purge_old_data
from data.db import get_broksum_ndays, get_net_buy_history, get_close_history, get_volume_history
from scraper.idx_scraper import scrape_all_stocks, get_foreign_flow_all, get_market_summary
from scraper.stockbit_scraper import scrape_all_broksum
from engine.indicators import get_all_indicators
from engine.market_regime import detect_regime
from engine.scoring import score_one_stock
from bot.formatter import build_report_data
from bot.formatter import (
    format_header,
    format_top5_was,
    format_top5_fs,
    format_top5_tcn,
    format_top5_sad,
    format_wtf_warning,
    format_watchlist_cfs,
)
import config

# ─── LQ45 Universe (45 saham) ────────────────────────────────────────────────
LQ45 = [
    "AALI", "ADMR", "ADRO", "AKRA", "AMRT",
    "ANTM", "ASII", "BBCA", "BBNI", "BBRI",
    "BBTN", "BMRI", "BRPT", "BSDE", "CPIN",
    "CTRA", "EMTK", "ERAA", "ESSA", "EXCL",
    "GGRM", "HRUM", "ICBP", "INCO", "INDF",
    "INKP", "INTP", "ITMG", "JSMR", "KLBF",
    "MDKA", "MEDC", "MIKA", "MNCN", "PGEO",
    "PGAS", "PTBA", "SMGR", "TINS", "TLKM",
    "TOWR", "TPIA", "UNTR", "UNVR", "WSKT",
]


def print_separator(char="=", width=60):
    print(char * width)


def print_section(title: str):
    print()
    print_separator("-")
    print(f"  {title}")
    print_separator("-")


def strip_markdown(text: str) -> str:
    """
    Hapus karakter markdown Telegram (*_ \\) untuk output terminal yang bersih.
    """
    return (
        text
        .replace("*", "")
        .replace("\\_", "_")
        .replace("\\-", "-")
        .replace("\\.", ".")
        .replace("\\&", "&")
        .replace("\\(", "(")
        .replace("\\)", ")")
        .replace("\\!", "!")
        .replace("\\>", ">")
        .replace("\\<", "<")
        .replace("\\=", "=")
        .replace("\\+", "+")
        .replace("\\#", "#")
        .replace("\\{", "{")
        .replace("\\}", "}")
    )


def print_report(data: dict):
    """Cetak semua 7 laporan ke terminal."""
    reports = [
        ("[1/7] HEADER",                format_header(data)),
        ("[2/7] TOP 5 WHALE (WAS)",     format_top5_was(data.get("was_ranking", []))),
        ("[3/7] TOP 5 FLOW (FS)",       format_top5_fs(data.get("fs_ranking", []))),
        ("[4/7] TOP 5 TEKNIKAL (TCN)",  format_top5_tcn(data.get("tcn_ranking", []))),
        ("[5/7] TOP 5 STEALTH (SAD)",   format_top5_sad(data.get("sad_ranking", []))),
        ("[6/7] WASH TRADE WARNING",    format_wtf_warning(data.get("wash_list", []))),
        ("[7/7] WATCHLIST CFS",         format_watchlist_cfs(data.get("cfs_ranking", []))),
    ]

    for title, text in reports:
        print_section(title)
        print(strip_markdown(text))

    print()
    print_separator("-")
    print("[OK] Laporan selesai ditampilkan.")
    print_separator("-")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print_separator("=")
    print("  IDX BANDARMOLOGY BOT -- MODE TEST LOKAL")
    print(f"  Tanggal : {date.today()}")
    print(f"  Universe: LQ45 ({len(LQ45)} saham)")
    print("  Output  : Terminal (tidak kirim Telegram)")
    print_separator("=")

    today_str = date.today().strftime("%Y%m%d")
    today_db  = date.today().strftime("%Y-%m-%d")

    # ── 1. Init DB ──
    print("\n[1/6] Inisialisasi database...")
    init_db()
    purge_old_data()
    print("     ✓ SQLite siap.")

    # ── 2. Market Summary ──
    print("\n[2/6] Fetching IHSG market summary...")
    market_summary = get_market_summary()
    regime         = detect_regime(market_summary)
    ihsg = market_summary.get("ihsg_level", 0)
    chg  = market_summary.get("ihsg_change_pct", 0)
    print(f"     ✓ IHSG: {ihsg:,.0f} ({chg:+.2f}%) | Regime: {regime}")

    # ── 3. IDX OHLCV ──
    print(f"\n[3/6] Scraping IDX OHLCV untuk {len(LQ45)} saham LQ45...")
    idx_data = scrape_all_stocks(LQ45)
    print(f"     ✓ Berhasil: {len(idx_data)}/{len(LQ45)} saham")

    # ── 4. Foreign Flow ──
    print("\n[4/6] Fetching foreign flow...")
    all_foreign = get_foreign_flow_all()
    print(f"     ✓ Foreign flow: {len(all_foreign)} saham")

    # ── 5. RTI Broker Summary ──
    # Override delay lebih singkat untuk testing lokal
    original_delay = config.DELAY_BETWEEN_REQUEST
    config.DELAY_BETWEEN_REQUEST = 1.0  # sedikit lebih cepat untuk LQ45

    eta_minutes = len(LQ45) * config.DELAY_BETWEEN_REQUEST / 60
    print(f"\n[5/6] Scraping Stockbit broker summary ({len(LQ45)} saham x {config.DELAY_BETWEEN_REQUEST}s ~ {eta_minutes:.1f} menit)...")
    print("      Pastikan STOCKBIT_TOKEN sudah diisi di .env!")
    all_broksum, all_bandar = scrape_all_broksum(LQ45, today_str)
    config.DELAY_BETWEEN_REQUEST = original_delay
    print(f"     Berhasil: {len(all_broksum)}/{len(LQ45)} saham")

    # ── Simpan ke DB ──
    print("\n     Menyimpan ke SQLite...")
    for code in LQ45:
        broksum = all_broksum.get(code, [])
        if broksum:
            save_daily_broksum(code, today_db, broksum)
        bandar_info = all_bandar.get(code)
        if bandar_info:
            save_bandar_detector(code, today_db, bandar_info)
        ohlcv = idx_data.get(code)
        if ohlcv:
            ohlcv["foreign_net_buy"] = all_foreign.get(code, 0.0)
            ohlcv["net_buy_total"]   = sum(float(b.get("net_value", 0) or 0) for b in broksum)
            save_daily_summary(code, today_db, ohlcv)
    print("     ✓ Data tersimpan.")

    # ── 6. Scoring ──
    print(f"\n[6/6] Kalkulasi scoring ({len(LQ45)} saham)...")
    all_scores = []

    for i, code in enumerate(LQ45, 1):
        # Progress inline
        print(f"     [{i:2d}/{len(LQ45)}] {code:<6}", end=" ", flush=True)

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

            # Tampilkan skor ringkas per saham
            cfs   = result["cfs"]["cfs"]
            label = result["cfs"]["label"]
            was   = result["was"]["was"]
            fs    = result["fs"]["fs"]
            tcn   = result["tcn"]["tcn"]
            sad   = "✅" if result["sad"]["sad"] else "❌"
            wtf   = result["wtf"]["wtf_risk"]
            print(f"CFS:{cfs:.2f} [{label:<10}] WAS:{was:.2f} FS:{fs:.2f} TCN:{tcn:.2f} SAD:{sad} WTF:{wtf}")

        except Exception as e:
            print(f"ERROR: {e}")
            logger.exception("Scoring error %s", code)

    print(f"\n     ✓ Scoring selesai: {len(all_scores)} saham diproses.")

    # ── Build report data ──
    report_data = build_report_data(
        all_scores=all_scores,
        market_summary=market_summary,
        regime=regime,
        universe_size=len(LQ45),
        emiten_scraped=len(all_broksum),
    )

    # ── Cetak laporan ──
    print("\n\n")
    print_separator("#")
    print("  LAPORAN SCREENING BANDARMOLOGY")
    print_separator("#")
    print_report(report_data)


if __name__ == "__main__":
    main()
