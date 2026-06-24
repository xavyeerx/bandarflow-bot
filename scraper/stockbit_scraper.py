"""
scraper/stockbit_scraper.py — Scrape broker summary dari Stockbit API.

Endpoint: https://exodus.stockbit.com/marketdetectors/{CODE}
          ?transaction_type=TRANSACTION_TYPE_NET
          &market_board=MARKET_BOARD_REGULER

Response berisi:
  - broker_summary.brokers_buy  → top buyer brokers
  - broker_summary.brokers_sell → top seller brokers
  - bandar_detector              → ringkasan akumulasi/distribusi

CARA AMBIL TOKEN (valid ~24 jam):
1. Buka https://stockbit.com → Login
2. Tekan F12 → tab Network
3. Klik saham BBRI (atau saham apa saja)
4. Cari request ke 'exodus.stockbit.com/marketdetectors/...'
5. Klik request itu → tab Headers
6. Copy nilai 'Authorization: Bearer eyJ...'  (TANPA kata 'Bearer ')
7. Paste ke .env: STOCKBIT_TOKEN=eyJ...
"""

import logging
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import requests

import config

logger = logging.getLogger(__name__)

# ─── Endpoint ─────────────────────────────────────────────────────────────────
STOCKBIT_BASE      = "https://exodus.stockbit.com"
MARKETDETECTOR_EP  = "/marketdetectors/{code}"

# Query params yang diperlukan
MARKETDETECTOR_PARAMS = {
    "transaction_type": "TRANSACTION_TYPE_NET",
    "market_board":     "MARKET_BOARD_REGULER",
}


def _build_headers(token: str) -> Dict:
    return {
        "Authorization":  f"Bearer {token}",
        "User-Agent":     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":         "application/json, text/plain, */*",
        "Accept-Language":"id-ID,id;q=0.9,en;q=0.8",
        "Origin":         "https://stockbit.com",
        "Referer":        "https://stockbit.com/",
    }


def _load_token() -> Optional[str]:
    token = getattr(config, "STOCKBIT_TOKEN", "")
    if not token or token.startswith("YOUR_"):
        logger.error(
            "STOCKBIT_TOKEN belum diisi di .env!\n"
            "  Cara ambil: buka stockbit.com → F12 → Network →\n"
            "  klik request ke exodus.stockbit.com/marketdetectors/... →\n"
            "  Headers → copy 'Authorization: Bearer eyJ...'"
        )
        return None
    return token


# ─── Parser ───────────────────────────────────────────────────────────────────

def _to_float(val, default=0.0) -> float:
    """Parse angka dari string scientific notation (e.g. '2.103e+11')."""
    try:
        return float(str(val or 0).replace(",", ""))
    except (ValueError, TypeError):
        return default


def _parse_broker_side(rows: List[Dict], side: str) -> Dict[str, Dict]:
    """
    Parse satu sisi (buy/sell) dari response Stockbit ke dict keyed by broker_code.

    Field mapping dari response:
      netbs_broker_code  → broker_code
      blot               → lot (beli/jual)
      blotv              → lot volume kumulatif (periode)
      bval               → value rupiah (beli/jual)
      bvalv              → value rupiah kumulatif (periode)
      type               → Asing / Lokal / Pemerintah
      freq               → jumlah transaksi
      netbs_buy_avg_price / netbs_sell_avg_price → harga rata-rata
    """
    result: Dict[str, Dict] = {}
    for row in (rows or []):
        code = str(row.get("netbs_broker_code") or "").strip().upper()
        if not code:
            continue

        lot      = _to_float(row.get("blot",  0))
        lot_cum  = _to_float(row.get("blotv", 0))
        value    = _to_float(row.get("bval",  0))
        val_cum  = _to_float(row.get("bvalv", 0))
        btype    = str(row.get("type", "Lokal")).strip()
        freq     = int(_to_float(row.get("freq", 0)))

        avg_price_key = "netbs_buy_avg_price" if side == "buy" else "netbs_sell_avg_price"
        avg_price = _to_float(row.get(avg_price_key, 0))

        result[code] = {
            "lot":       lot,
            "lot_cum":   lot_cum,
            "value":     value,
            "val_cum":   val_cum,
            "type":      btype,
            "side":      side,
            "freq":      freq,
            "avg_price": avg_price,
        }
    return result


def _merge_buy_sell(
    buy_map: Dict[str, Dict],
    sell_map: Dict[str, Dict],
) -> List[Dict]:
    """
    Gabungkan buy & sell menjadi list broker summary dengan net lot & net value.
    """
    all_codes = set(buy_map.keys()) | set(sell_map.keys())
    results: List[Dict] = []

    for code in all_codes:
        buy  = buy_map.get(code,  {"lot": 0, "lot_cum": 0, "value": 0, "val_cum": 0, "type": "Lokal", "freq": 0, "avg_price": 0})
        sell = sell_map.get(code, {"lot": 0, "lot_cum": 0, "value": 0, "val_cum": 0, "type": "Lokal", "freq": 0, "avg_price": 0})

        broker_type = buy.get("type") or sell.get("type") or "Lokal"

        buy_lot   = buy["lot"]
        sell_lot  = sell["lot"]
        buy_val   = buy["value"]
        sell_val  = sell["value"]
        net_lot   = buy_lot - sell_lot
        net_value = buy_val - sell_val

        results.append({
            "broker_code":    code,
            "broker_type":    broker_type,
            "buy_lot":        buy_lot,
            "sell_lot":       sell_lot,
            "net_lot":        net_lot,
            "buy_value":      buy_val,
            "sell_value":     sell_val,
            "net_value":      net_value,
            # Field tambahan dari Stockbit
            "buy_lot_cum":    buy.get("lot_cum", 0),
            "sell_lot_cum":   sell.get("lot_cum", 0),
            "buy_val_cum":    buy.get("val_cum", 0),
            "sell_val_cum":   sell.get("val_cum", 0),
            "buy_freq":       buy.get("freq", 0),
            "sell_freq":      sell.get("freq", 0),
            "buy_avg_price":  buy.get("avg_price", 0),
            "sell_avg_price": sell.get("avg_price", 0),
        })

    # Urutkan berdasarkan net_lot descending
    results.sort(key=lambda x: x["net_lot"], reverse=True)
    return results


def _parse_response(data: Dict) -> Tuple[List[Dict], Dict]:
    """
    Parse full response dari /marketdetectors endpoint.

    Return: (broker_summary_list, bandar_detector_dict)
    """
    broker_summary_raw = data.get("data", {}).get("broker_summary", {})
    bandar_raw         = data.get("data", {}).get("bandar_detector", {})

    brokers_buy  = broker_summary_raw.get("brokers_buy",  [])
    brokers_sell = broker_summary_raw.get("brokers_sell", [])

    buy_map  = _parse_broker_side(brokers_buy,  "buy")
    sell_map = _parse_broker_side(brokers_sell, "sell")
    merged   = _merge_buy_sell(buy_map, sell_map)

    # Simpan ringkasan bandar detector untuk keperluan scoring
    def _bd(key: str, sub: Dict = None) -> any:
        src = sub if sub is not None else bandar_raw
        return src.get(key, {}) if isinstance(src.get(key, {}), dict) else src.get(key)

    bandar_summary = {
        # Ringkasan utama
        "broker_accdist":        bandar_raw.get("broker_accdist", ""),
        "number_broker_buysell": _to_float(bandar_raw.get("number_broker_buysell", 0)),
        "total_buyer":           _to_float(bandar_raw.get("total_buyer", 0)),
        "total_seller":          _to_float(bandar_raw.get("total_seller", 0)),
        "total_value":           _to_float(bandar_raw.get("value", 0)),
        "total_volume":          _to_float(bandar_raw.get("volume", 0)),
        "average_price":         _to_float(bandar_raw.get("average", 0)),
        # avg (rata-rata semua broker)
        "avg_accdist":           bandar_raw.get("avg", {}).get("accdist", ""),
        "avg_amount":            _to_float(bandar_raw.get("avg", {}).get("amount", 0)),
        "avg_pct":               _to_float(bandar_raw.get("avg", {}).get("percent", 0)),
        "avg_vol":               _to_float(bandar_raw.get("avg", {}).get("vol", 0)),
        # avg5 (rata-rata 5 hari)
        "avg5_accdist":          bandar_raw.get("avg5", {}).get("accdist", ""),
        "avg5_amount":           _to_float(bandar_raw.get("avg5", {}).get("amount", 0)),
        "avg5_pct":              _to_float(bandar_raw.get("avg5", {}).get("percent", 0)),
        "avg5_vol":              _to_float(bandar_raw.get("avg5", {}).get("vol", 0)),
        # top1
        "top1_accdist":          bandar_raw.get("top1", {}).get("accdist", ""),
        "top1_pct":              _to_float(bandar_raw.get("top1", {}).get("percent", 0)),
        "top1_amount":           _to_float(bandar_raw.get("top1", {}).get("amount", 0)),
        "top1_vol":              _to_float(bandar_raw.get("top1", {}).get("vol", 0)),
        # top3
        "top3_accdist":          bandar_raw.get("top3", {}).get("accdist", ""),
        "top3_pct":              _to_float(bandar_raw.get("top3", {}).get("percent", 0)),
        "top3_amount":           _to_float(bandar_raw.get("top3", {}).get("amount", 0)),
        "top3_vol":              _to_float(bandar_raw.get("top3", {}).get("vol", 0)),
        # top5
        "top5_accdist":          bandar_raw.get("top5", {}).get("accdist", ""),
        "top5_pct":              _to_float(bandar_raw.get("top5", {}).get("percent", 0)),
        "top5_amount":           _to_float(bandar_raw.get("top5", {}).get("amount", 0)),
        "top5_vol":              _to_float(bandar_raw.get("top5", {}).get("vol", 0)),
        # top10
        "top10_accdist":         bandar_raw.get("top10", {}).get("accdist", ""),
        "top10_pct":             _to_float(bandar_raw.get("top10", {}).get("percent", 0)),
        "top10_amount":          _to_float(bandar_raw.get("top10", {}).get("amount", 0)),
        "top10_vol":             _to_float(bandar_raw.get("top10", {}).get("vol", 0)),
    }

    return merged, bandar_summary


# ─── Scraper class ─────────────────────────────────────────────────────────────

class StockbitScraper:
    """Scraper broker summary via Stockbit marketdetectors API."""

    def __init__(self):
        self._token: Optional[str] = None
        self._ready = False
        self.token_expired = False

    def _ensure_ready(self) -> bool:
        if self._ready:
            return True
        self._token = _load_token()
        if self._token:
            self._ready = True
        return self._ready

    def get_broker_summary(
        self,
        code: str,
        trade_date: str = None,
    ) -> Tuple[List[Dict], Dict]:
        """
        Ambil broker summary + bandar_detector satu saham.

        Return: (broker_list, bandar_info)
          broker_list: [{broker_code, broker_type, buy_lot, sell_lot, net_lot,
                         buy_value, sell_value, net_value, buy_freq, buy_avg_price, ...}]
          bandar_info: ringkasan accdist dari Stockbit bandar_detector
        """
        if not self._ensure_ready():
            return [], {}

        url     = STOCKBIT_BASE + MARKETDETECTOR_EP.format(code=code)
        headers = _build_headers(self._token)
        params  = dict(MARKETDETECTOR_PARAMS)

        # Tambahkan date jika ada (format Stockbit: YYYY-MM-DD)
        if trade_date:
            try:
                dt = datetime.strptime(trade_date, "%Y%m%d")
                params["date"] = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        for attempt in range(1, config.MAX_RETRY + 1):
            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=config.REQUEST_TIMEOUT,
                )

                if resp.status_code == 401:
                    logger.error(
                        "Stockbit token EXPIRED atau SALAH!\n"
                        "  Perbarui STOCKBIT_TOKEN di .env:\n"
                        "  buka stockbit.com → F12 → Network → copy Authorization header"
                    )
                    self._ready = False
                    self.token_expired = True
                    return [], {}

                if resp.status_code == 429:
                    wait = 30 * attempt
                    logger.warning("Rate limited Stockbit, tunggu %ds...", wait)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                broker_list, bandar_info = _parse_response(data)

                if broker_list:
                    logger.debug(
                        "Stockbit %s: %d brokers | accdist=%s | top1_pct=%.1f%%",
                        code,
                        len(broker_list),
                        bandar_info.get("broker_accdist", "-"),
                        bandar_info.get("top1_pct", 0),
                    )
                    return broker_list, bandar_info

                logger.debug("Stockbit %s: response OK tapi broker list kosong", code)
                return [], bandar_info

            except requests.HTTPError as e:
                logger.warning("Stockbit HTTP %s (attempt %d/%d): %s", code, attempt, config.MAX_RETRY, e)
            except requests.RequestException as e:
                logger.warning("Stockbit request error %s (attempt %d/%d): %s", code, attempt, config.MAX_RETRY, e)
            except (ValueError, KeyError) as e:
                logger.warning("Stockbit parse error %s: %s", code, e)
                return [], {}

            if attempt < config.MAX_RETRY:
                time.sleep(2 ** attempt)

        return [], {}

    def scrape_all_broksum(
        self,
        codes: List[str],
        trade_date: str = None,
    ) -> Tuple[Dict[str, List[Dict]], Dict[str, Dict]]:
        """
        Scrape broker summary untuk semua kode. Dengan delay per request.

        Return: (broksum_dict, bandar_dict)
          broksum_dict: {code: [broker_list]}
          bandar_dict:  {code: bandar_info}
        """
        if not self._ensure_ready():
            logger.error("Stockbit scraper tidak bisa init — cek STOCKBIT_TOKEN di .env")
            return {}

        results: Dict[str, List[Dict]] = {}
        total  = len(codes)
        failed = 0

        logger.info("Stockbit: scraping %d saham...", total)

        bandar_results: Dict[str, Dict] = {}

        for i, code in enumerate(codes, 1):
            broksum, bandar_info = self.get_broker_summary(code, trade_date)

            if broksum:
                results[code] = broksum
            else:
                failed += 1
                logger.debug("Skip %s (tidak ada data)", code)

            if bandar_info:
                bandar_results[code] = bandar_info

            # Progress log setiap 10 saham
            if i % 10 == 0 or i == total:
                ok_count = i - failed
                logger.info(
                    "  Progress: %d/%d | OK: %d | Gagal: %d",
                    i, total, ok_count, failed,
                )

            time.sleep(config.DELAY_BETWEEN_REQUEST)

        logger.info(
            "Stockbit selesai: %d/%d berhasil (%.1f%%)",
            len(results), total,
            len(results) / total * 100 if total else 0,
        )
        return results, bandar_results


# ─── Singleton & public API ───────────────────────────────────────────────────

_scraper: Optional[StockbitScraper] = None


def _get_scraper() -> StockbitScraper:
    global _scraper
    if _scraper is None:
        _scraper = StockbitScraper()
    return _scraper


def scrape_all_broksum(
    codes: List[str], trade_date: str = None
) -> Tuple[Dict[str, List[Dict]], Dict[str, Dict]]:
    """Public wrapper. Return: (broksum_dict, bandar_dict)."""
    return _get_scraper().scrape_all_broksum(codes, trade_date)


def get_broker_summary(code: str, trade_date: str = None) -> Tuple[List[Dict], Dict]:
    """Public wrapper untuk satu saham. Return: (broker_list, bandar_info)."""
    return _get_scraper().get_broker_summary(code, trade_date)


def is_token_expired() -> bool:
    """Cek apakah Stockbit token expired (401) saat scraping terakhir."""
    return _get_scraper().token_expired
