"""
engine/market_regime.py — Deteksi kondisi pasar IHSG (BULLISH / NEUTRAL / BEARISH).
"""

from typing import Dict


def detect_regime(market_summary: Dict) -> str:
    """
    Tentukan kondisi pasar berdasarkan pergerakan IHSG hari ini.

    Args:
        market_summary: dict dari idx_scraper.get_market_summary()
            {ihsg_level, ihsg_change_pct, ihsg_volume_rupiah}

    Return:
        "BULLISH" | "NEUTRAL" | "BEARISH"
    """
    change_pct = float(market_summary.get("ihsg_change_pct", 0) or 0)

    if change_pct >= 0.5:
        return "BULLISH"
    elif change_pct <= -0.5:
        return "BEARISH"
    else:
        return "NEUTRAL"


def regime_emoji(regime: str) -> str:
    """Return emoji untuk tiap regime."""
    return {
        "BULLISH": "🟢",
        "NEUTRAL": "🟡",
        "BEARISH": "🔴",
    }.get(regime, "⚪")
