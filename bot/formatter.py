"""
bot/formatter.py — Format 7 pesan Telegram (HTML parse mode).
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


def fmt_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def fmt_score(value: float) -> str:
    return f"{value:.2f}"


# ─── Pesan 1: Header ──────────────────────────────────────────────────────────

def format_header(data: Dict) -> str:
    today         = date.today().strftime("%Y-%m-%d")
    universe_size = data.get("universe_size", 0)
    regime        = data.get("regime", "NEUTRAL")
    ihsg          = data.get("ihsg_level", 0)
    ihsg_chg      = data.get("ihsg_change_pct", 0)
    ihsg_vol      = data.get("ihsg_volume_rupiah", 0)
    data_status   = data.get("data_status", "FULL")
    whale_count   = data.get("whale_count", 0)
    wash_count    = data.get("wash_count", 0)
    r_emoji       = regime_emoji(regime)
    chg_sign      = "+" if ihsg_chg >= 0 else ""

    return (
        f"📊 <b>DAILY SCREENING REPORT</b>\n"
        f"📅 {today} | Universe: {universe_size:,} emiten\n"
        f"🔬 Flow + TCN + Bandarmology\n\n"
        f"🌡 Market Regime: <b>{regime}</b> {r_emoji}\n"
        f"IHSG: {ihsg:,.0f} ({chg_sign}{ihsg_chg:.1f}%) | "
        f"Vol: {format_rupiah(ihsg_vol)}\n"
        f"📦 Data: {'✅ FULL' if data_status == 'FULL' else '⚠️ DEGRADED'}\n"
        f"🐳 Whale Signals: {whale_count} saham\n"
        f"⚠️ Wash Trade Warning: {wash_count} saham"
    )


# ─── Pesan 2: Top 5 WAS ───────────────────────────────────────────────────────

def format_top5_was(was_ranking: List[Dict]) -> str:
    lines = [
        "🐳 <b>TOP 5 WHALE ACCUMULATION</b>",
        "Ranked by: WAS = konsentrasi(40%) + persistence(40%) + net value(20%)",
        "",
    ]
    for i, item in enumerate(was_ranking[:config.TOP_N], 1):
        was     = item["was"]
        code    = item["code"]
        konsen  = was["konsentrasi"]
        streak  = was["persistent_days"]
        net     = was["net_buy_total_rupiah"]
        brokers = " ".join(was["top3_brokers"][:3])

        lines.append(
            f"{i}. <b>{code}</b>  "
            f"WAS:{fmt_score(was['was'])} | "
            f"Konsen:{fmt_pct(konsen)} | "
            f"Streak:{streak}d | "
            f"Net:{format_rupiah(net)} | "
            f"Bkr:{brokers}"
        )
    if not was_ranking:
        lines.append("<i>(tidak ada sinyal whale hari ini)</i>")
    return "\n".join(lines)


# ─── Pesan 3: Top 5 FS ────────────────────────────────────────────────────────

def format_top5_fs(fs_ranking: List[Dict]) -> str:
    lines = [
        "💧 <b>TOP 5 FLOW SCORE</b>",
        "Ranked by: FS = sigmoid(net_buy_today / avg_10d) + foreign booster",
        "",
    ]
    for i, item in enumerate(fs_ranking[:config.TOP_N], 1):
        code = item["code"]
        fs   = item["fs"]
        net  = fs["net_buy_today"]
        anom = fs["anomali"]
        fgn  = "NET BUY ⬆️" if fs["foreign_booster_active"] else "NEUTRAL"

        lines.append(
            f"{i}. <b>{code}</b>  "
            f"FS:{fmt_score(fs['fs'])} | "
            f"Net:{format_rupiah(net)} | "
            f"Anomali:{anom:+.1f}x | "
            f"Foreign:{fgn}"
        )
    if not fs_ranking:
        lines.append("<i>(tidak ada sinyal flow hari ini)</i>")
    return "\n".join(lines)


# ─── Pesan 4: Top 5 TCN ───────────────────────────────────────────────────────

def format_top5_tcn(tcn_ranking: List[Dict]) -> str:
    lines = [
        "📈 <b>TOP 5 TECHNICAL CONFLUENCE</b>",
        "Ranked by: TCN = jumlah sinyal bullish dari 10 indikator",
        "",
    ]
    for i, item in enumerate(tcn_ranking[:config.TOP_N], 1):
        code  = item["code"]
        tcn   = item["tcn"]
        score = tcn["score"]
        sigs  = tcn["signals"]

        active_sigs = [f"✅{k}" for k, v in sigs.items() if v][:6]
        sig_str     = " ".join(active_sigs)

        lines.append(
            f"{i}. <b>{code}</b>  "
            f"TCN:{fmt_score(tcn['tcn'])} | "
            f"{score}/{tcn['max_score']} | "
            f"{sig_str}"
        )
    if not tcn_ranking:
        lines.append("<i>(tidak ada sinyal teknikal hari ini)</i>")
    return "\n".join(lines)


# ─── Pesan 5: Top 5 SAD ───────────────────────────────────────────────────────

def format_top5_sad(sad_ranking: List[Dict]) -> str:
    lines = [
        "🔍 <b>TOP 5 STEALTH ACCUMULATION</b>",
        "Ranked by: streak terpanjang + cum net buy terbesar",
        "Sinyal pre-breakout — harga sideways, broker diam-diam beli",
        "",
    ]
    for i, item in enumerate(sad_ranking[:config.TOP_N], 1):
        code    = item["code"]
        sad     = item["sad"]
        was     = item.get("was", {})
        streak  = was.get("persistent_days", 0)
        cum_net = sad["cum_net_buy_5d"]
        vol_r   = sad["vol_ratio"]
        p_range = sad["price_range"] * 100
        p_days  = sad["positive_days"]

        lines.append(
            f"{i}. <b>{code}</b>  "
            f"Streak:{streak}d | "
            f"Range:{p_range:.1f}% | "
            f"Vol:{vol_r:.1f}x | "
            f"CumNet:{format_rupiah(cum_net)} | "
            f"Days:{p_days}/5"
        )
    if not sad_ranking:
        lines.append("<i>(tidak ada sinyal stealth accumulation hari ini)</i>")
    return "\n".join(lines)


# ─── Pesan 6: WTF Warning ─────────────────────────────────────────────────────

def format_wtf_warning(wash_list: List[Dict]) -> str:
    lines = [
        "⚠️ <b>WASH TRADE WARNING</b>",
        "Saham berikut terdeteksi transaksi mencurigakan — HINDARI",
        "",
    ]
    if not wash_list:
        lines.append("<i>(tidak ada wash trade terdeteksi hari ini)</i> ✅")
    else:
        for i, item in enumerate(wash_list[:10], 1):
            code     = item["code"]
            wtf      = item["wtf"]
            risk     = wtf["wtf_risk"]
            wash_pct = int(wtf["wash_score"] * 100)
            fs_val   = item.get("fs", {}).get("fs", 0)

            lines.append(
                f"{i}. <b>{code}</b>  "
                f"Wash:{wash_pct}% | "
                f"Risk:{risk} | "
                f"Flow:{fmt_score(fs_val)}"
            )
        lines.append("")
        lines.append("⚠️ Flow tinggi + wash tinggi = jebakan pump &amp; dump")
    return "\n".join(lines)


# ─── Pesan 7: Watchlist CFS ───────────────────────────────────────────────────

def format_watchlist_cfs(cfs_ranking: List[Dict]) -> str:
    lines = [
        "🎯 <b>WATCHLIST — TOP 5 RANKING CFS</b>",
        "Bobot: WAS(35%) + FS(30%) + TCN(25%) + SAD(10%)",
        "Pre-filter: wash &lt; 30% | vol &gt; 0.5B | harga &gt; 100 | net buy &gt; 0",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if not cfs_ranking:
        lines.append("<i>(tidak ada saham yang lolos pre-filter hari ini)</i>")
    else:
        for i, item in enumerate(cfs_ranking[:config.TOP_N], 1):
            code  = item["code"]
            cfs   = item["cfs"]
            was   = item["was"]
            fs    = item["fs"]
            tcn   = item["tcn"]
            sad   = item["sad"]

            label      = cfs["label"]
            cfs_val    = cfs["cfs"]
            whale_icon = "🐳" if was["is_whale"] else "📈"
            sad_icon   = "✅" if sad["sad"] else "❌"
            brokers    = " ".join(was["top3_brokers"][:3])
            vol_ratio  = tcn.get("vol_ratio", 0)
            net        = fs["net_buy_today"]
            streak     = was["persistent_days"]

            lines.append(
                f"{i}. {whale_icon} <b>{code}</b>  [{label}]  CFS:{fmt_score(cfs_val)}"
            )
            lines.append(
                f"   WAS:{fmt_score(was['was'])} | "
                f"FS:{fmt_score(fs['fs'])} | "
                f"TCN:{fmt_score(tcn['tcn'])} | "
                f"SAD:{sad_icon}"
            )
            lines.append(
                f"   Bkr:{brokers} | "
                f"Vol:{vol_ratio:.1f}x | "
                f"Net:{format_rupiah(net)} | "
                f"Streak:{streak}d"
            )

            if sad["sad"] and streak >= 5:
                lines.append(f"   ⭐ Stealth {streak}d — kandidat breakout")

            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📌 Bukan rekomendasi beli/jual. DYOR.")
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
    fs_ranking  = sorted(valid, key=lambda x: x["fs"]["fs"],  reverse=True)
    tcn_ranking = sorted(valid, key=lambda x: x["tcn"]["tcn"], reverse=True)

    sad_ranking = sorted(
        [s for s in valid if s["sad"]["sad"] == 1],
        key=lambda x: (x["was"]["persistent_days"], x["sad"]["cum_net_buy_5d"]),
        reverse=True,
    )

    wash_list = sorted(
        [s for s in valid if s["wtf"]["wtf_risk"] in ("HIGH", "MODERATE")],
        key=lambda x: x["wtf"]["wash_score"],
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
        "wash_count":         len([s for s in valid if s["wtf"]["wtf_risk"] == "HIGH"]),
        "was_ranking":        was_ranking,
        "fs_ranking":         fs_ranking,
        "tcn_ranking":        tcn_ranking,
        "sad_ranking":        sad_ranking,
        "wash_list":          wash_list,
        "cfs_ranking":        cfs_ranking,
    }
