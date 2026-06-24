"""
engine/scoring.py — Semua formula scoring: WAS, FS, TCN, SAD, WTF, CFS.

Setiap fungsi mengikuti spesifikasi PRD secara persis.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

import config

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Formula 1: WAS — Whale Accumulation Score
# ══════════════════════════════════════════════════════════════════════════════

def calc_was(broksum_ndays: List[Dict]) -> Dict:
    """
    Hitung Whale Accumulation Score.

    Args:
        broksum_ndays: List baris broksum dari SQLite, berisi field
                       {date, broker_code, buy_lot, sell_lot, net_lot, net_value}
                       untuk 5 hari terakhir.

    Return dict:
        was, konsentrasi, persistence, net_value_norm,
        net_buy_total_rupiah, top3_brokers, is_whale, streak_days
    """
    if not broksum_ndays:
        return _empty_was()

    # Kelompokkan per tanggal
    by_date: Dict[str, Dict[str, float]] = {}
    for row in broksum_ndays:
        d = row.get("date", "")
        b = row.get("broker_code", "")
        net_lot = float(row.get("net_lot", 0) or 0)
        net_val = float(row.get("net_value", 0) or 0)

        if d not in by_date:
            by_date[d] = {}
        by_date[d][b] = by_date[d].get(b, 0) + net_lot

    if not by_date:
        return _empty_was()

    dates_sorted = sorted(by_date.keys())
    latest_date  = dates_sorted[-1]
    latest_brokers = by_date[latest_date]

    # ── Step 1: Konsentrasi — top 3 broker net buy hari ini ──
    net_values = list(latest_brokers.values())
    sorted_nets = sorted(net_values, reverse=True)
    top3_net_buy  = sorted_nets[:3]
    net_buy_top3  = sum(max(v, 0) for v in top3_net_buy)
    total_net_all = sum(abs(v) for v in net_values) or 1
    konsentrasi   = net_buy_top3 / total_net_all

    # Nama broker top 3
    top3_brokers = sorted(
        latest_brokers, key=lambda k: latest_brokers[k], reverse=True
    )[:3]

    # ── Step 2: Persistence — broker top3 muncul berapa hari ──
    top3_set_today = set(top3_brokers)
    persistent_days = 0
    n_days = len(dates_sorted)

    for d in dates_sorted[-5:]:   # maks 5 hari
        day_brokers = by_date.get(d, {})
        day_top3    = set(
            sorted(day_brokers, key=lambda k: day_brokers[k], reverse=True)[:3]
        )
        if len(top3_set_today & day_top3) >= 2:   # overlap >= 2 broker
            persistent_days += 1

    persistence = persistent_days / max(min(n_days, 5), 1)

    # ── Step 3: Net value log-normalized (dari RTI net_value rupiah) ──
    net_buy_total_rupiah = sum(
        float(row.get("net_value", 0) or 0)
        for row in broksum_ndays
        if row.get("date") == latest_date and float(row.get("net_value", 0) or 0) > 0
    )
    net_value_norm = math.log10(max(net_buy_total_rupiah, 1)) / 12

    # ── Step 4: Final WAS ──
    was = (konsentrasi * 0.40) + (persistence * 0.40) + (net_value_norm * 0.20)
    was = min(was, 1.0)

    is_whale = (was > config.WAS_WHALE_THRESHOLD and konsentrasi > config.WAS_KONSENTRASI_THRESHOLD)

    return {
        "was":                  round(was, 4),
        "konsentrasi":          round(konsentrasi, 4),
        "persistence":          round(persistence, 4),
        "persistent_days":      persistent_days,
        "net_value_norm":       round(net_value_norm, 4),
        "net_buy_total_rupiah": net_buy_total_rupiah,
        "top3_brokers":         top3_brokers,
        "is_whale":             is_whale,
        "streak_days":          n_days,
    }


def _empty_was() -> Dict:
    return {
        "was": 0.0, "konsentrasi": 0.0, "persistence": 0.0,
        "persistent_days": 0, "net_value_norm": 0.0,
        "net_buy_total_rupiah": 0.0, "top3_brokers": [],
        "is_whale": False, "streak_days": 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Formula 2: FS — Flow Score
# ══════════════════════════════════════════════════════════════════════════════

def calc_fs(
    net_buy_today: float,
    net_buy_10d: List[float],
    foreign_net_buy: float = 0.0,
) -> Dict:
    """
    Hitung Flow Score.

    Args:
        net_buy_today:   Net buy rupiah hari ini (semua broker)
        net_buy_10d:     Array net buy 10 hari terakhir dari SQLite
        foreign_net_buy: Net buy asing dari IDX API

    Return dict: fs, avg_net_10d, anomali, foreign_booster_active
    """
    # Step 1: Baseline
    if net_buy_10d:
        avg_net_10d = float(np.mean(net_buy_10d))
    else:
        avg_net_10d = 0.0

    # Step 2: Rasio anomali
    if avg_net_10d != 0:
        anomali = net_buy_today / abs(avg_net_10d)
    else:
        anomali = 1.0 if net_buy_today > 0 else -1.0

    # Step 3: Normalisasi sigmoid
    fs = 1 / (1 + math.exp(-anomali))

    # Step 4: Booster jika asing net buy
    foreign_booster = foreign_net_buy > 0
    if foreign_booster:
        fs = min(fs + config.FS_FOREIGN_BOOSTER, 1.0)

    return {
        "fs":                   round(fs, 4),
        "avg_net_10d":          avg_net_10d,
        "anomali":              round(anomali, 2),
        "foreign_booster_active": foreign_booster,
        "net_buy_today":        net_buy_today,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Formula 3: TCN — Technical Confluence Number
# ══════════════════════════════════════════════════════════════════════════════

def calc_tcn(indicators: Dict) -> Dict:
    """
    Hitung Technical Confluence Number (0-1).

    Args:
        indicators: dict dari engine/indicators.py get_all_indicators()

    Return dict: tcn, score, max_score, signals (dict per indikator)
    """
    if not indicators:
        return {"tcn": 0.0, "score": 0, "max_score": 10, "signals": {}}

    close   = indicators.get("close", 0)
    open_   = indicators.get("open", 0)
    high    = indicators.get("high", 0)
    low     = indicators.get("low", 0)
    volume  = indicators.get("volume", 0)
    ma20    = indicators.get("ma20", 0)
    ma50    = indicators.get("ma50", 0)
    rsi     = indicators.get("rsi", 50)
    macd    = indicators.get("macd", 0)
    macd_s  = indicators.get("macd_signal", 0)
    stoch_k = indicators.get("stoch_k", 50)
    stoch_d = indicators.get("stoch_d", 50)
    avg_vol = indicators.get("avg_vol_5d", 0)
    support = indicators.get("support_level", 0)

    score    = 0
    signals  = {}

    # ── Trend (3 poin) ──
    sig_ma    = close > ma20 > 0
    sig_trend = ma20 > ma50 > 0
    sig_green = close > open_ > 0

    if sig_ma:    score += 1
    if sig_trend: score += 1
    if sig_green: score += 1

    signals["MA"]    = sig_ma
    signals["Trend"] = sig_trend
    signals["Candle"] = sig_green

    # ── Momentum (2 poin) ──
    sig_rsi  = 50 < rsi < 70
    sig_macd = macd > macd_s

    if sig_rsi:  score += 1
    if sig_macd: score += 1

    signals[f"RSI({rsi:.0f})"] = sig_rsi
    signals["MACD"]            = sig_macd

    # ── Volume (2 poin) ──
    vol_ratio = volume / avg_vol if avg_vol > 0 else 0
    sig_vol   = vol_ratio >= config.TCN_VOLUME_SPIKE_RATIO

    if sig_vol: score += 2

    signals[f"Vol({vol_ratio:.1f}x)"] = sig_vol

    # ── Price Action (2 poin) ──
    sig_support = low >= support > 0

    if sig_support: score += 1

    body_range = high - low
    body_ratio = (close - low) / body_range if body_range > 0 else 0
    sig_body   = body_ratio > config.TCN_BODY_RATIO_MIN

    if sig_body: score += 1

    signals["Support"]  = sig_support
    signals["Body"]     = sig_body

    # ── Stochastic (1 poin) ──
    sig_stoch = stoch_k > stoch_d and stoch_k < 80

    if sig_stoch: score += 1

    signals["Stochastic"] = sig_stoch

    max_score = 10
    tcn = score / max_score

    return {
        "tcn":       round(tcn, 4),
        "score":     score,
        "max_score": max_score,
        "signals":   signals,
        "rsi":       round(rsi, 1),
        "vol_ratio": round(vol_ratio, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Formula 4: SAD — Stealth Accumulation Detector
# ══════════════════════════════════════════════════════════════════════════════

def calc_sad(
    close_5d: List[float],
    volume_5d: List[float],
    avg_vol_20d: float,
    net_buy_5d: List[float],
) -> Dict:
    """
    Deteksi pola Wyckoff Accumulation (binary: 1 atau 0).

    Args:
        close_5d:    Harga close 5 hari terakhir
        volume_5d:   Volume 5 hari terakhir
        avg_vol_20d: Rata-rata volume 20 hari
        net_buy_5d:  Net buy broksum per hari, 5 hari terakhir

    Return dict: sad, price_range, vol_ratio, positive_days, cum_net_buy_5d
    """
    if not close_5d or len(close_5d) < 2:
        return {"sad": 0, "price_range": 0, "vol_ratio": 0,
                "positive_days": 0, "cum_net_buy_5d": 0}

    # Step 1: Harga sideways?
    min_close   = min(close_5d)
    price_range = (max(close_5d) - min_close) / min_close if min_close > 0 else 1.0

    # Step 2: Volume tetap tinggi?
    avg_vol_5d = float(np.mean(volume_5d)) if volume_5d else 0
    vol_ratio  = avg_vol_5d / avg_vol_20d if avg_vol_20d > 0 else 0

    # Step 3: Net buy konsisten?
    positive_days  = sum(1 for nb in net_buy_5d if nb > 0)
    cum_net_buy_5d = sum(net_buy_5d)

    # Step 4: Semua kondisi (binary)
    sad = 1 if (
        price_range < config.SAD_PRICE_RANGE_MAX
        and vol_ratio > config.SAD_VOL_RATIO_MIN
        and positive_days >= config.SAD_MIN_POSITIVE_DAYS
        and cum_net_buy_5d > 0
    ) else 0

    return {
        "sad":            sad,
        "price_range":    round(price_range, 4),
        "vol_ratio":      round(vol_ratio, 2),
        "positive_days":  positive_days,
        "cum_net_buy_5d": cum_net_buy_5d,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Formula 5: WTF — Wash Trade Filter
# ══════════════════════════════════════════════════════════════════════════════

def calc_wtf(broksum_today: List[Dict]) -> Dict:
    """
    Deteksi transaksi mencurigakan (wash trade).

    Args:
        broksum_today: Broksum hari ini semua broker
                       [{broker_code, buy_lot, sell_lot, ...}]

    Return dict: wtf_risk ("LOW" | "MODERATE" | "HIGH"), wash_score
    """
    if not broksum_today:
        return {"wtf_risk": "LOW", "wash_score": 0.0}

    total_volume = sum(
        float(b.get("buy_lot", 0) or 0) + float(b.get("sell_lot", 0) or 0)
        for b in broksum_today
    )

    if total_volume == 0:
        return {"wtf_risk": "LOW", "wash_score": 0.0}

    wash_volume = 0.0
    for broker in broksum_today:
        buy  = float(broker.get("buy_lot", 0) or 0)
        sell = float(broker.get("sell_lot", 0) or 0)
        if buy > 0 and sell > 0:
            smaller = min(buy, sell)
            larger  = max(buy, sell)
            if smaller / larger > config.WTF_BROKER_RATIO_THRESHOLD:
                wash_volume += (smaller * 2)

    wash_score = wash_volume / total_volume

    if wash_score < config.WTF_LOW_THRESHOLD:
        risk = "LOW"
    elif wash_score < config.WTF_HIGH_THRESHOLD:
        risk = "MODERATE"
    else:
        risk = "HIGH"

    return {
        "wtf_risk":   risk,
        "wash_score": round(wash_score, 4),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Formula Final: CFS — Composite Final Score
# ══════════════════════════════════════════════════════════════════════════════

def calc_cfs(
    was: float,
    fs: float,
    tcn: float,
    sad: int,
    wtf_risk: str,
    volume_rupiah: float,
    close: float,
    net_buy_today: float,
) -> Dict:
    """
    Gabungkan semua score menjadi CFS dengan pre-filter.

    Args:
        was, fs, tcn: float 0-1
        sad:          int 0 atau 1
        wtf_risk:     "LOW" | "MODERATE" | "HIGH"
        volume_rupiah: volume dalam rupiah hari ini
        close:        harga penutupan
        net_buy_today: net buy total hari ini

    Return dict: cfs, label, lolos_prefilter, reason_filtered
    """
    # Pre-filter
    reason = None
    if wtf_risk == "HIGH":
        reason = "Wash Trade HIGH"
    elif volume_rupiah < config.CFS_MIN_VOLUME_RUPIAH:
        reason = f"Volume terlalu kecil ({volume_rupiah/1e9:.2f}B)"
    elif close <= config.CFS_MIN_PRICE:
        reason = f"Harga terlalu rendah (Rp {close:,.0f})"
    elif net_buy_today <= 0:
        reason = "Net buy negatif"

    if reason:
        return {
            "cfs":              0.0,
            "label":            "SKIP",
            "lolos_prefilter":  False,
            "reason_filtered":  reason,
        }

    cfs = (
        (was * config.W_WAS)
        + (fs  * config.W_FS)
        + (tcn * config.W_TCN)
        + (sad * config.W_SAD)
    )
    cfs = round(min(cfs, 1.0), 4)

    if cfs >= config.CFS_STRONG_BUY:
        label = "STRONG BUY"
    elif cfs >= config.CFS_BUY:
        label = "BUY"
    elif cfs >= config.CFS_WATCH:
        label = "WATCH"
    else:
        label = "SKIP"

    return {
        "cfs":             cfs,
        "label":           label,
        "lolos_prefilter": True,
        "reason_filtered": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator: Hitung semua score untuk satu saham
# ══════════════════════════════════════════════════════════════════════════════

def score_one_stock(
    code: str,
    broksum_ndays: List[Dict],
    broksum_today: List[Dict],
    net_buy_10d: List[float],
    foreign_net_buy: float,
    indicators: Optional[Dict],
    close_5d: List[float],
    volume_5d: List[float],
    avg_vol_20d: float,
    net_buy_5d: List[float],
    ohlcv_today: Optional[Dict],
) -> Dict:
    """
    Hitung semua formula untuk satu saham dan return bundle hasil.
    """
    # Net buy hari ini dari broksum (sum semua broker)
    net_buy_today = sum(
        float(b.get("net_value", 0) or 0) for b in broksum_today
    )

    volume_rupiah = float((ohlcv_today or {}).get("volume_rupiah", 0) or 0)
    close         = float((ohlcv_today or {}).get("close", 0) or 0)

    was_result = calc_was(broksum_ndays)
    fs_result  = calc_fs(net_buy_today, net_buy_10d, foreign_net_buy)
    tcn_result = calc_tcn(indicators)
    sad_result = calc_sad(close_5d, volume_5d, avg_vol_20d, net_buy_5d)
    wtf_result = calc_wtf(broksum_today)
    cfs_result = calc_cfs(
        was=was_result["was"],
        fs=fs_result["fs"],
        tcn=tcn_result["tcn"],
        sad=sad_result["sad"],
        wtf_risk=wtf_result["wtf_risk"],
        volume_rupiah=volume_rupiah,
        close=close,
        net_buy_today=net_buy_today,
    )

    return {
        "code":        code,
        "ohlcv":       ohlcv_today,
        "was":         was_result,
        "fs":          fs_result,
        "tcn":         tcn_result,
        "sad":         sad_result,
        "wtf":         wtf_result,
        "cfs":         cfs_result,
        "net_buy_today": net_buy_today,
    }
