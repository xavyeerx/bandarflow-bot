"""
engine/indicators.py — Kalkulasi indikator teknikal menggunakan yfinance + pandas-ta.

Mengunduh data 60 hari historis per saham dari yfinance (gratis, no API key).
"""

import logging
from typing import Dict, List, Optional

# Cache hasil batch download yfinance: {ticker_jk: DataFrame}
_ohlcv_cache: Dict[str, "pd.DataFrame"] = {}

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance tidak terinstall. Indikator teknikal tidak tersedia.")

try:
    import ta as ta_lib
    TA_LIB_AVAILABLE = True
except ImportError:
    TA_LIB_AVAILABLE = False
    logger.warning("ta library tidak terinstall. MACD menggunakan kalkulasi manual.")

import config


# ─── Download OHLCV Historis ──────────────────────────────────────────────────

def prefetch_all_indicators(codes: List[str], days: int = 60) -> int:
    """
    Batch download OHLCV historis untuk semua kode sekaligus via yfinance.
    Hasilnya disimpan ke _ohlcv_cache sehingga get_ohlcv_history() tidak perlu
    download satu-per-satu (900 request → 1 request).

    Return: jumlah ticker berhasil di-cache.
    """
    global _ohlcv_cache
    if not YFINANCE_AVAILABLE:
        return 0

    tickers = [f"{c}{config.YFINANCE_SUFFIX}" for c in codes]
    logger.info("yfinance batch download untuk %d saham (indicators)...", len(tickers))

    try:
        df_all = yf.download(
            tickers,
            period=f"{days}d",
            interval=config.YFINANCE_INTERVAL,
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
    except Exception as e:
        logger.warning("yfinance batch download gagal: %s", e)
        return 0

    ok = 0
    for ticker in tickers:
        try:
            if isinstance(df_all.columns, pd.MultiIndex):
                df = df_all[ticker].copy()
            else:
                df = df_all.copy()
            df = df.dropna(how="all")
            if df.empty or len(df) < 5:
                continue
            df.index = pd.to_datetime(df.index)
            _ohlcv_cache[ticker] = df
            ok += 1
        except (KeyError, Exception):
            pass

    logger.info("yfinance batch indicators: %d/%d berhasil di-cache", ok, len(tickers))
    return ok


def get_ohlcv_history(code: str, days: int = 60) -> Optional[pd.DataFrame]:
    """
    Download data OHLCV historis dari yfinance.

    Args:
        code: Kode saham BEI, contoh 'BBRI' → akan jadi 'BBRI.JK'
        days: Jumlah hari historis (default 60)

    Return:
        DataFrame dengan kolom [Open, High, Low, Close, Volume]
        atau None jika gagal.
    """
    if not YFINANCE_AVAILABLE:
        return None

    ticker = f"{code}{config.YFINANCE_SUFFIX}"

    # Cek cache dari prefetch_all_indicators
    if ticker in _ohlcv_cache:
        return _ohlcv_cache[ticker]

    try:
        df = yf.download(
            ticker,
            period=f"{days}d",
            interval=config.YFINANCE_INTERVAL,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            logger.debug("yfinance: data kosong untuk %s", ticker)
            return None

        # yfinance versi baru return MultiIndex columns untuk single ticker
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()
        df.index = pd.to_datetime(df.index)
        return df

    except Exception as e:
        logger.warning("yfinance gagal untuk %s: %s", ticker, e)
        return None


# ─── Kalkulasi Indikator ──────────────────────────────────────────────────────

def calc_ma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=window, min_periods=1).mean()


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index (RSI).
    Return series nilai RSI 0-100.
    """
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.finfo(float).eps)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    MACD dan MACD Signal.
    Return: (macd_series, signal_series)
    """
    ema_fast   = series.ewm(span=fast, adjust=False).mean()
    ema_slow   = series.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def calc_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
    """
    Stochastic Oscillator %K dan %D.
    Return: (k_series, d_series)
    """
    low_min  = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()

    denom = (high_max - low_min).replace(0, np.finfo(float).eps)
    k = 100 * (df["Close"] - low_min) / denom
    d = k.rolling(window=d_period).mean()
    return k, d


# ─── Bundle Semua Indikator ───────────────────────────────────────────────────

def get_all_indicators(code: str) -> Optional[Dict]:
    """
    Download historis + hitung semua indikator yang dibutuhkan TCN.

    Return dict:
        close, open, high, low, volume,
        ma20, ma50, rsi, macd, macd_signal,
        stoch_k, stoch_d,
        avg_vol_5d, avg_vol_20d,
        support_level (low 20 hari)
    atau None jika data tidak cukup.
    """
    df = get_ohlcv_history(code, days=60)
    if df is None or len(df) < 21:
        logger.debug("Data historis tidak cukup untuk %s (rows: %s)", code, len(df) if df is not None else 0)
        return None

    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    # Moving Averages
    ma20 = calc_ma(close, 20)
    ma50 = calc_ma(close, 50)

    # RSI
    rsi = calc_rsi(close)

    # MACD
    if TA_LIB_AVAILABLE:
        macd_val = float(ta_lib.trend.macd(close, window_slow=26, window_fast=12).iloc[-1])
        sig_val  = float(ta_lib.trend.macd_signal(close, window_slow=26, window_fast=12, window_sign=9).iloc[-1])
    else:
        macd_s, sig_s = calc_macd(close)
        macd_val  = float(macd_s.iloc[-1]) if not macd_s.empty else 0.0
        sig_val   = float(sig_s.iloc[-1]) if not sig_s.empty else 0.0

    # Stochastic
    stoch_k, stoch_d = calc_stochastic(df)

    # Volume averages
    vol_series  = volume.astype(float)
    avg_vol_5d  = float(vol_series.rolling(5).mean().iloc[-1])
    avg_vol_20d = float(vol_series.rolling(20).mean().iloc[-1])

    # Support level: low terendah 20 hari
    support_level = float(low.rolling(20).min().iloc[-1])

    return {
        "close":          float(close.iloc[-1]),
        "open":           float(df["Open"].iloc[-1]),
        "high":           float(high.iloc[-1]),
        "low":            float(low.iloc[-1]),
        "volume":         float(vol_series.iloc[-1]),
        "ma20":           float(ma20.iloc[-1]),
        "ma50":           float(ma50.iloc[-1]),
        "rsi":            float(rsi.iloc[-1]),
        "macd":           macd_val,
        "macd_signal":    sig_val,
        "stoch_k":        float(stoch_k.iloc[-1]) if not stoch_k.empty else 50.0,
        "stoch_d":        float(stoch_d.iloc[-1]) if not stoch_d.empty else 50.0,
        "avg_vol_5d":     avg_vol_5d,
        "avg_vol_20d":    avg_vol_20d,
        "support_level":  support_level,
    }
