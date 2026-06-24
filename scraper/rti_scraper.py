"""
scraper/rti_scraper.py — Scrape broker summary (broksum) dari RTI.co.id.

Endpoint:
    GET https://www.rti.co.id/ver2/rti_brokersummary_new.php
        ?act=getbsbycode&code=BBRI&sdate=20260623&edate=20260623

Response JSON fields: broker_code, buy_lot, sell_lot, net_lot, net_value

PENTING: Jaga delay 1.5 detik antar request. RTI agak ketat rate limit-nya.
"""

import logging
import time
from datetime import datetime, date
from typing import Dict, List, Optional

import requests

import config

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _today_str() -> str:
    return date.today().strftime("%Y%m%d")


def _parse_float(val) -> float:
    """Parse angka yang mungkin dalam format string dengan koma."""
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", "").replace(" ", ""))
    except (ValueError, TypeError):
        return 0.0


def _get_rti(code: str, sdate: str, edate: str) -> Optional[List[Dict]]:
    """
    Fetch broker summary dari RTI untuk satu saham dan range tanggal.
    Retry MAX_RETRY kali dengan exponential backoff.
    """
    params = {
        "act":   "getbsbycode",
        "code":  code,
        "sdate": sdate,
        "edate": edate,
    }

    headers = {
        **config.REQUEST_HEADERS,
        "Referer": f"https://www.rti.co.id/bandarmologi/{code.lower()}",
    }

    for attempt in range(1, config.MAX_RETRY + 1):
        try:
            resp = requests.get(
                config.RTI_BROKSUM_URL,
                params=params,
                headers=headers,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()

            data = resp.json()

            # RTI response bisa berupa list langsung atau {"data": [...]}
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return (
                    data.get("data")
                    or data.get("result")
                    or data.get("broksum")
                    or []
                )
            return []

        except requests.exceptions.HTTPError as e:
            logger.warning(
                "RTI HTTP %s untuk %s attempt %d/%d",
                e.response.status_code if e.response else "?",
                code, attempt, config.MAX_RETRY,
            )
        except requests.RequestException as e:
            logger.warning(
                "RTI request error %s attempt %d/%d: %s",
                code, attempt, config.MAX_RETRY, e,
            )
        except ValueError as e:
            logger.warning("RTI JSON parse error %s: %s", code, e)
            return []

        if attempt < config.MAX_RETRY:
            time.sleep(2 ** attempt)  # 2s, 4s

    return None


# ─── Public API ───────────────────────────────────────────────────────────────

def get_broker_summary(
    code: str,
    trade_date: str = None,
) -> List[Dict]:
    """
    Ambil broker summary satu saham untuk tanggal tertentu.

    Args:
        code:       Kode saham, contoh 'BBRI'
        trade_date: Format 'YYYYMMDD'. Default: hari ini.

    Return:
        List of dict: [{broker_code, buy_lot, sell_lot, net_lot, net_value}, ...]
        Return [] jika gagal atau tidak ada data.
    """
    if trade_date is None:
        trade_date = _today_str()

    raw = _get_rti(code, trade_date, trade_date)

    if raw is None:
        logger.error("RTI scraping total gagal untuk %s", code)
        return []

    parsed: List[Dict] = []
    for row in raw:
        broker_code = (
            str(row.get("broker_code") or row.get("BrokerCode") or row.get("kode") or "")
            .strip()
            .upper()
        )
        if not broker_code:
            continue

        buy_lot  = _parse_float(row.get("buy_lot")  or row.get("BuyLot")  or row.get("buy"))
        sell_lot = _parse_float(row.get("sell_lot") or row.get("SellLot") or row.get("sell"))
        net_lot  = _parse_float(row.get("net_lot")  or row.get("NetLot")  or row.get("net"))
        net_value = _parse_float(
            row.get("net_value") or row.get("NetValue") or row.get("value") or 0
        )

        # Jika net_lot tidak tersedia, hitung dari buy-sell
        if net_lot == 0 and (buy_lot != 0 or sell_lot != 0):
            net_lot = buy_lot - sell_lot

        # net_value dalam rupiah: jika tidak ada, estimasi dari net_lot × harga
        # (harga tidak tersedia di sini, biarkan 0 → akan di-skip saat FS)

        parsed.append({
            "broker_code": broker_code,
            "buy_lot":     buy_lot,
            "sell_lot":    sell_lot,
            "net_lot":     net_lot,
            "net_value":   net_value,
        })

    return parsed


def scrape_all_broksum(codes: List[str], trade_date: str = None) -> Dict[str, List[Dict]]:
    """
    Scrape broker summary untuk semua kode saham.
    Delay 1.5 detik antar request untuk menghindari rate limit RTI.

    Return: dict {code: [broksum_list]}
    """
    if trade_date is None:
        trade_date = _today_str()

    results: Dict[str, List[Dict]] = {}
    total = len(codes)
    failed = 0

    logger.info("Mulai RTI broksum scraping: %d saham, tanggal %s", total, trade_date)

    for i, code in enumerate(codes, 1):
        broksum = get_broker_summary(code, trade_date)

        if broksum:
            results[code] = broksum
        else:
            failed += 1
            logger.warning("Broksum kosong/gagal: %s (%d/%d)", code, i, total)

        if i % 50 == 0:
            logger.info(
                "RTI progress: %d/%d (%.1f%%) | Gagal: %d",
                i, total, i / total * 100, failed,
            )

        # Wajib: delay untuk menghindari ban dari RTI
        time.sleep(config.DELAY_BETWEEN_REQUEST)

    logger.info(
        "RTI broksum selesai: %d/%d berhasil, %d gagal",
        len(results), total, failed,
    )
    return results
