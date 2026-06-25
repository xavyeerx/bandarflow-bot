"""
scraper/idx_scraper.py — Scrape OHLCV via yfinance (primary) + IDX API (market summary & foreign flow).

CATATAN: IDX hidden API endpoint GetStockSummary sering 403.
Solusi: gunakan yfinance untuk OHLCV harian dan historis, IDX API hanya untuk
market summary IHSG dan foreign flow jika tersedia.
"""

import logging
import time
from datetime import datetime, date
from typing import Dict, List, Optional

import requests

import config

logger = logging.getLogger(__name__)

def _isnan(v) -> bool:
    try:
        import math
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True

try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False
    logger.error("yfinance tidak terinstall!")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get(url: str, params: Dict = None) -> Optional[Dict]:
    """GET dengan retry logic."""
    for attempt in range(1, config.MAX_RETRY + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                headers=config.REQUEST_HEADERS,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("IDX API attempt %d/%d: %s", attempt, config.MAX_RETRY, e)
            if attempt < config.MAX_RETRY:
                time.sleep(2 * attempt)
    return None


# ─── OHLCV via yfinance (Primary) ─────────────────────────────────────────────

def get_stock_summary(code: str) -> Optional[Dict]:
    """
    Ambil OHLCV hari ini untuk satu saham via yfinance.
    Return dict: {code, open, high, low, close, volume, volume_rupiah, change_pct}
    """
    if not YFINANCE_OK:
        return None

    ticker_str = f"{code}{config.YFINANCE_SUFFIX}"  # e.g. "BBRI.JK"

    try:
        ticker = yf.Ticker(ticker_str)

        # Ambil data 5 hari terakhir untuk memastikan data hari ini ada
        df = ticker.history(period="5d", interval="1d", auto_adjust=True)

        if df is None or df.empty:
            logger.debug("yfinance data kosong untuk %s", ticker_str)
            return None

        # Ambil baris terakhir (hari terakhir trading)
        row = df.iloc[-1]
        prev_close = float(df.iloc[-2]["Close"]) if len(df) >= 2 else float(row["Close"])

        close  = float(row["Close"])
        open_  = float(row["Open"])
        high   = float(row["High"])
        low    = float(row["Low"])
        volume = float(row["Volume"])

        # Volume rupiah estimasi (lot × harga × 100 saham/lot)
        # Volume yfinance untuk IDX sudah dalam satuan lembar saham
        volume_rupiah = volume * close

        change_pct = ((close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

        return {
            "code":          code,
            "open":          open_,
            "high":          high,
            "low":           low,
            "close":         close,
            "volume":        volume,
            "volume_rupiah": volume_rupiah,
            "change_pct":    round(change_pct, 2),
            "market_cap":    None,
        }

    except Exception as e:
        logger.warning("yfinance error untuk %s: %s", code, e)
        return None


# ─── Market Summary (IHSG) ────────────────────────────────────────────────────

def get_market_summary() -> Dict:
    """
    Ambil kondisi IHSG via yfinance (^JKSE).
    Return dict: {ihsg_level, ihsg_change_pct, ihsg_volume_rupiah}
    """
    try:
        ticker = yf.Ticker("^JKSE")

        # fast_info punya harga real-time (15min delay), lebih up-to-date dari history daily
        fi = ticker.fast_info
        close      = float(fi.get("lastPrice") or fi.get("last_price") or 0)
        prev_close = float(fi.get("previousClose") or fi.get("previous_close") or 0)

        if close > 0 and prev_close > 0:
            change_pct = (close - prev_close) / prev_close * 100
            # Volume dari history 1d interval 1m (hari ini)
            df_1m = ticker.history(period="1d", interval="1m", auto_adjust=True)
            volume = float(df_1m["Volume"].sum()) if not df_1m.empty else 0.0
            logger.info("IHSG via fast_info: %.2f (%.2f%%)", close, change_pct)
            return {
                "ihsg_level":         close,
                "ihsg_change_pct":    round(change_pct, 2),
                "ihsg_volume_rupiah": volume,
            }

        # Fallback: history daily
        df = ticker.history(period="5d", interval="1d", auto_adjust=True)
        if df is None or df.empty:
            raise ValueError("Data IHSG kosong")

        last  = df.iloc[-1]
        prev  = df.iloc[-2] if len(df) >= 2 else last
        close      = float(last["Close"])
        prev_close = float(prev["Close"])
        change_pct = ((close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        volume     = float(last["Volume"])

        logger.info("IHSG via yfinance history: %.0f (%.2f%%)", close, change_pct)
        return {
            "ihsg_level":         close,
            "ihsg_change_pct":    round(change_pct, 2),
            "ihsg_volume_rupiah": volume,
        }

    except Exception as e:
        logger.warning("Gagal fetch IHSG dari yfinance: %s. Coba IDX API...", e)

    # Fallback ke IDX API
    data = _get(config.IDX_COMPOSITE_URL)
    if not data:
        return {"ihsg_level": 0, "ihsg_change_pct": 0, "ihsg_volume_rupiah": 0}

    composite = data.get("data", {}) or data.get("Composite", {}) or data

    def _f(d, *keys, default=0.0):
        for k in keys:
            if k in d:
                try:
                    return float(str(d[k]).replace(",", ""))
                except (ValueError, TypeError):
                    pass
        return default

    return {
        "ihsg_level":         _f(composite, "IndexValue", "Value", "Close"),
        "ihsg_change_pct":    _f(composite, "ChangePct", "Percentage", "Change"),
        "ihsg_volume_rupiah": _f(composite, "Value", "TotalValue", "Volume"),
    }


# ─── Foreign Flow ─────────────────────────────────────────────────────────────

def get_foreign_flow_all() -> Dict[str, float]:
    """
    Coba ambil foreign flow dari IDX API.
    Jika gagal, return dict kosong (FS akan berjalan tanpa booster).
    """
    # Coba endpoint IDX
    endpoints_to_try = [
        (config.IDX_TRADING_SUMMARY_URL, {"indexCode": "COMPOSITE", "period": "1D"}),
        # Alternatif endpoint yang kadang masih aktif
        ("https://idx.co.id/api/cluster/StockData/GetStockList", {"start": 0, "length": 10, "language": "id"}),
    ]

    for url, params in endpoints_to_try:
        try:
            resp = requests.get(
                url, params=params,
                headers=config.REQUEST_HEADERS,
                timeout=config.REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                stocks = (
                    data.get("data", {}).get("trading", [])
                    or data.get("Stocks", [])
                    or []
                )
                if stocks:
                    result: Dict[str, float] = {}
                    for s in stocks:
                        code = (s.get("StockCode") or s.get("Code") or "").upper()
                        if code:
                            try:
                                fb = float(s.get("ForeignBuy") or 0)
                                fs = float(s.get("ForeignSell") or 0)
                                result[code] = fb - fs
                            except (ValueError, TypeError):
                                pass
                    if result:
                        logger.info("Foreign flow berhasil dari IDX: %d saham", len(result))
                        return result
        except Exception as e:
            logger.debug("Foreign flow endpoint gagal: %s", e)

    logger.warning("Foreign flow tidak tersedia. FS berjalan tanpa booster asing.")
    return {}


def get_foreign_net_buy(code: str, all_foreign_flow: Dict[str, float] = None) -> float:
    """Ambil foreign net buy untuk satu saham dari cache."""
    if all_foreign_flow:
        return all_foreign_flow.get(code, 0.0)
    return 0.0


# ─── Batch scraper ────────────────────────────────────────────────────────────

def scrape_all_stocks(codes: List[str]) -> Dict[str, Dict]:
    """
    Scrape OHLCV via yfinance untuk semua kode sekaligus (batch download — jauh lebih cepat).
    """
    if not YFINANCE_OK:
        logger.error("yfinance tidak tersedia!")
        return {}

    results: Dict[str, Dict] = {}
    total = len(codes)

    # yfinance batch download: jauh lebih efisien dari satu-satu
    tickers_str = " ".join(f"{c}{config.YFINANCE_SUFFIX}" for c in codes)

    logger.info("yfinance batch download untuk %d saham...", total)
    try:
        df_all = yf.download(
            tickers_str,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )

        if df_all is None or df_all.empty:
            logger.error("yfinance batch download gagal, fallback ke individual download")
            raise ValueError("Empty batch")

        nan_codes = []  # kode yang close-nya NaN, perlu fast_info

        for code in codes:
            ticker_str = f"{code}{config.YFINANCE_SUFFIX}"
            try:
                if len(codes) == 1:
                    df = df_all
                else:
                    df = df_all[ticker_str] if ticker_str in df_all.columns.get_level_values(0) else None

                if df is None or (hasattr(df, 'empty') and df.empty):
                    nan_codes.append(code)
                    continue

                # prev_close dari baris sebelum terakhir (tidak drop NaN dulu)
                df_valid = df.dropna(subset=["Close"], how="any")
                prev_c = float(df_valid.iloc[-1]["Close"]) if len(df_valid) >= 1 else 0.0

                # Ambil volume hari ini (baris terakhir, bisa NaN close)
                last_row = df.iloc[-1]
                volume   = float(last_row["Volume"]) if not _isnan(last_row["Volume"]) else 0.0

                # Cek apakah close hari ini tersedia
                last_close = last_row["Close"]
                if _isnan(last_close):
                    # Tandai untuk di-patch via fast_info
                    nan_codes.append(code)
                    # Simpan sementara dengan prev_close sebagai placeholder
                    results[code] = {
                        "code": code, "open": prev_c, "high": prev_c,
                        "low": prev_c, "close": prev_c, "volume": volume,
                        "volume_rupiah": volume * prev_c, "change_pct": 0.0,
                        "market_cap": None, "_prev_close": prev_c,
                    }
                    continue

                close  = float(last_close)
                open_  = float(last_row["Open"]) if not _isnan(last_row["Open"]) else close
                high   = float(last_row["High"]) if not _isnan(last_row["High"]) else close
                low    = float(last_row["Low"])  if not _isnan(last_row["Low"])  else close

                change_pct    = ((close - prev_c) / prev_c * 100) if prev_c > 0 else 0.0
                volume_rupiah = volume * close

                results[code] = {
                    "code": code, "open": open_, "high": high, "low": low,
                    "close": close, "volume": volume,
                    "volume_rupiah": volume_rupiah,
                    "change_pct": round(change_pct, 2), "market_cap": None,
                }

            except Exception as e:
                logger.debug("Parse error %s dari batch: %s", code, e)
                nan_codes.append(code)

        logger.info("yfinance batch: %d/%d saham berhasil, %d perlu fast_info",
                    len(results) - len(nan_codes), total, len(nan_codes))

        # Patch harga terkini via fast_info untuk yang Close NaN
        if nan_codes:
            logger.info("Mengambil harga terkini via fast_info untuk %d saham...", len(nan_codes))
            for code in nan_codes:
                try:
                    fi = yf.Ticker(f"{code}{config.YFINANCE_SUFFIX}").fast_info
                    close = float(fi.get("lastPrice") or fi.get("last_price") or 0)
                    prev_c = float(fi.get("previousClose") or fi.get("previous_close") or 0)
                    if close <= 0:
                        continue
                    existing = results.get(code, {})
                    volume   = existing.get("volume", 0)
                    change_pct = ((close - prev_c) / prev_c * 100) if prev_c > 0 else 0.0
                    results[code] = {
                        "code": code, "open": prev_c, "high": close,
                        "low": prev_c, "close": close, "volume": volume,
                        "volume_rupiah": volume * close,
                        "change_pct": round(change_pct, 2), "market_cap": None,
                    }
                except Exception as e:
                    logger.debug("fast_info error %s: %s", code, e)

    except Exception as e:
        logger.warning("Batch download gagal (%s), fallback ke individual...", e)
        # Fallback: individual download
        for i, code in enumerate(codes, 1):
            summary = get_stock_summary(code)
            if summary:
                results[code] = summary
            if i % 10 == 0:
                logger.info("Individual progress: %d/%d", i, total)
            time.sleep(0.2)

    return results
