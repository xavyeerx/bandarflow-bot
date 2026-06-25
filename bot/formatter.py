"""
bot/formatter.py — Format 7 pesan Telegram (HTML parse mode).
Fokus: broker yang akumulasi, net buy, ringkas dan informatif.
"""

from datetime import date
from typing import Dict, List

import config
from engine.market_regime import regime_emoji


# ─── Format Angka ─────────────────────────────────────────────────────────────

def format_rupiah(value_rupiah: float) -> str:
    abs_val = abs(value_rupiah)
    sign    = "+" if value_rupiah >= 0 else "-"
    if abs_val >= 1_000_000_000_000:
        return f"{sign}{abs_val / 1_000_000_000_000:.1f}T"
    elif abs_val >= 1_000_000_000:
        return f"{sign}{abs_val / 1_000_000_000:.1f}B"
    elif abs_val >= 1_000_000:
        return f"{sign}{abs_val / 1_000_000:.1f}M"
    else:
        return f"{sign}{abs_val:,.0f}"

def fmt_score(v: float) -> str:
    return f"{v:.2f}"

def fmt_pct(v: float) -> str:
    return f"{v * 100:.0f}%"

def _brokers(top3: list) -> str:
    return "  ".join(f"<b>{b}</b>" for b in top3[:3])

def _price_str(ohlcv: dict) -> str:
    import math
    close = (ohlcv or {}).get("close") or 0
    chg   = (ohlcv or {}).get("change_pct") or 0
    if not close or math.isnan(float(close)):
        return ""
    chg = float(chg) if not math.isnan(float(chg)) else 0.0
    sign = "+" if chg >= 0 else ""
    return f"Rp{float(close):,.0f} ({sign}{chg:.1f}%)"


# ─── Pesan 1: Header ──────────────────────────────────────────────────────────

def format_header(data: Dict) -> str:
    today       = date.today().strftime("%Y-%m-%d")
    n           = data.get("universe_size", 0)
    regime      = data.get("regime", "NEUTRAL")
    ihsg        = data.get("ihsg_level", 0)
    chg         = data.get("ihsg_change_pct", 0)
    status      = data.get("data_status", "FULL")
    whales      = data.get("whale_count", 0)
    r_emoji     = regime_emoji(regime)
    chg_sign    = "+" if chg >= 0 else ""
    chg_color   = "📗" if chg >= 0 else "📕"

    return (
        f"📊 <b>BANDARMOLOGY SCREENING</b>\n"
        f"📅 {today} | {n:,} emiten dianalisis\n"
        f"{'─' * 28}\n"
        f"{chg_color} IHSG  <b>{ihsg:,.2f}</b>  ({chg_sign}{chg:.2f}%)\n"
        f"🌡 Regime: <b>{regime}</b> {r_emoji}\n"
        f"{'─' * 28}\n"
        f"🐳 Whale aktif   : {whales} saham\n"
        f"📦 Data status   : {'✅ FULL' if status == 'FULL' else '⚠️ DEGRADED'}"
    )


# ─── Pesan 2: Top 5 WAS ───────────────────────────────────────────────────────

def format_top5_was(was_ranking: List[Dict]) -> str:
    lines = [
        "🐳 <b>WHALE ACCUMULATION</b>",
        "<i>Broker besar diam-diam akumulasi hari ini</i>",
        "",
    ]
    for i, item in enumerate(was_ranking[:config.TOP_N], 1):
        was    = item["was"]
        code   = item["code"]
        net    = was["net_buy_total_rupiah"]
        streak = was["persistent_days"]
        top3   = was["top3_brokers"][:3]
        streak_str = f"  {streak}d berturut" if streak > 1 else ""
        price  = _price_str(item.get("ohlcv"))

        lines.append(f"{i}. <b>{code}</b>  {price}  {format_rupiah(net)}{streak_str}")
        lines.append(f"   Broker: {_brokers(top3)}")

    if not was_ranking:
        lines.append("<i>(tidak ada sinyal whale hari ini)</i>")
    return "\n".join(lines).rstrip()


# ─── Pesan 3: Top 5 FS ────────────────────────────────────────────────────────

def format_top5_fs(fs_ranking: List[Dict]) -> str:
    lines = [
        "💧 <b>MONEY FLOW</b>",
        "<i>Net buy broksum terbesar hari ini</i>",
        "",
    ]
    for i, item in enumerate(fs_ranking[:config.TOP_N], 1):
        code  = item["code"]
        fs    = item["fs"]
        net   = fs["net_buy_today"]
        anom  = fs["anomali"]
        fgn   = "  🌏 Asing masuk" if fs["foreign_booster_active"] else ""
        was   = item.get("was", {})
        top3  = was.get("top3_brokers", [])[:3]
        price = _price_str(item.get("ohlcv"))

        lines.append(f"{i}. <b>{code}</b>  {price}  {format_rupiah(net)}  ({anom:+.1f}x){fgn}")
        if top3:
            lines.append(f"   Broker: {_brokers(top3)}")

    if not fs_ranking:
        lines.append("<i>(tidak ada sinyal flow hari ini)</i>")
    return "\n".join(lines).rstrip()


# ─── Pesan 4: Top 5 TCN ───────────────────────────────────────────────────────

def format_top5_tcn(tcn_ranking: List[Dict]) -> str:
    lines = [
        "📈 <b>SINYAL TEKNIKAL</b>",
        "<i>Konfluensi indikator bullish terbanyak</i>",
        "",
    ]
    for i, item in enumerate(tcn_ranking[:config.TOP_N], 1):
        code  = item["code"]
        tcn   = item["tcn"]
        score = tcn["score"]
        mx    = tcn["max_score"]
        sigs  = tcn["signals"]

        active = [k for k, v in sigs.items() if v][:5]
        sig_str = "  ".join(f"✅{s}" for s in active)
        price   = _price_str(item.get("ohlcv"))

        lines.append(f"{i}. <b>{code}</b>  {price}  {score}/{mx} sinyal")
        lines.append(f"   {sig_str}")

    if not tcn_ranking:
        lines.append("<i>(tidak ada sinyal teknikal hari ini)</i>")
    return "\n".join(lines).rstrip()


# ─── Pesan 5: Top 5 SAD ───────────────────────────────────────────────────────

def format_top5_sad(sad_ranking: List[Dict]) -> str:
    lines = [
        "🔍 <b>STEALTH ACCUMULATION</b>",
        "<i>Harga sideways tapi broker terus akumulasi — sinyal pre-breakout</i>",
        "",
    ]
    for i, item in enumerate(sad_ranking[:config.TOP_N], 1):
        code    = item["code"]
        sad     = item["sad"]
        was     = item.get("was", {})
        top3    = was.get("top3_brokers", [])[:3]
        streak  = was.get("persistent_days", 0)
        cum_net = sad["cum_net_buy_5d"]
        p_range = sad["price_range"] * 100
        p_days  = sad["positive_days"]

        price = _price_str(item.get("ohlcv"))
        lines.append(
            f"{i}. <b>{code}</b>  {price}  {format_rupiah(cum_net)} / 5 hari"
            f"  ({p_days}/5 hari net buy positif)"
        )
        lines.append(f"   Broker: {_brokers(top3)}  |  Range harga: {p_range:.1f}%")
        if streak > 1:
            lines.append(f"   ⭐ Streak {streak} hari — kandidat breakout")

    if not sad_ranking:
        lines.append("<i>(tidak ada sinyal stealth accumulation hari ini)</i>")
    return "\n".join(lines).rstrip()


# ─── Pesan 6: Watchlist CFS ───────────────────────────────────────────────────

def format_watchlist_cfs(cfs_ranking: List[Dict]) -> str:
    lines = [
        "🎯 <b>WATCHLIST HARI INI</b>",
        "<i>Gabungan sinyal whale + flow + teknikal terkuat</i>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if not cfs_ranking:
        lines.append("<i>(tidak ada saham yang lolos filter hari ini)</i>")
    else:
        for i, item in enumerate(cfs_ranking[:config.TOP_N], 1):
            code   = item["code"]
            cfs    = item["cfs"]
            was    = item["was"]
            fs     = item["fs"]
            tcn    = item["tcn"]
            sad    = item["sad"]

            label      = cfs["label"]
            whale_icon = "🐳" if was["is_whale"] else "📈"
            sad_tag    = "  ⭐ Stealth" if sad["sad"] else ""
            top3       = was["top3_brokers"][:3]
            net        = fs["net_buy_today"]
            streak     = was["persistent_days"]
            score_tcn  = tcn["score"]
            mx         = tcn["max_score"]
            streak_str = f"  {streak}d berturut" if streak > 1 else ""

            label_icon = "🟢" if label == "STRONG BUY" else ("🔵" if label == "BUY" else "⚪")
            price      = _price_str(item.get("ohlcv"))

            lines.append(
                f"{i}. {whale_icon} <b>{code}</b>  {price}  "
                f"{label_icon} {label}{sad_tag}"
            )
            lines.append(
                f"   Broker akumulasi: {_brokers(top3)}"
            )
            lines.append(
                f"   Net beli: {format_rupiah(net)}{streak_str}  |  Teknikal: {score_tcn}/{mx}"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📌 <i>Bukan rekomendasi beli/jual. DYOR.</i>")
    return "\n".join(lines)


# ─── Helper: Build data dict ──────────────────────────────────────────────────

def build_report_data(
    all_scores: List[Dict],
    market_summary: Dict,
    regime: str,
    universe_size: int,
    emiten_scraped: int,
) -> Dict:
    threshold   = config.DEGRADED_THRESHOLD * universe_size
    data_status = "FULL" if emiten_scraped >= threshold else "DEGRADED"

    valid = [s for s in all_scores if s.get("ohlcv")]

    was_ranking = sorted(valid, key=lambda x: x["was"]["was"], reverse=True)
    fs_ranking  = sorted(
        [s for s in valid if s["fs"]["net_buy_today"] > 0],
        key=lambda x: x["fs"]["net_buy_today"],
        reverse=True,
    )
    tcn_ranking = sorted(valid, key=lambda x: x["tcn"]["tcn"], reverse=True)

    sad_ranking = sorted(
        [s for s in valid if s["sad"]["sad"] == 1],
        key=lambda x: (x["was"]["persistent_days"], x["sad"]["cum_net_buy_5d"]),
        reverse=True,
    )

    cfs_ranking = sorted(
        [s for s in valid if s["cfs"]["lolos_prefilter"] and s["cfs"]["label"] != "SKIP"],
        key=lambda x: x["cfs"]["cfs"],
        reverse=True,
    )

    whale_count = sum(1 for s in valid if s["was"]["is_whale"])

    return {
        "universe_size":      universe_size,
        "emiten_scraped":     emiten_scraped,
        "data_status":        data_status,
        "regime":             regime,
        "ihsg_level":         market_summary.get("ihsg_level", 0),
        "ihsg_change_pct":    market_summary.get("ihsg_change_pct", 0),
        "ihsg_volume_rupiah": market_summary.get("ihsg_volume_rupiah", 0),
        "whale_count":        whale_count,
        "was_ranking":        was_ranking,
        "fs_ranking":         fs_ranking,
        "tcn_ranking":        tcn_ranking,
        "sad_ranking":        sad_ranking,
        "cfs_ranking":        cfs_ranking,
    }
