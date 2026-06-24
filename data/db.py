"""
data/db.py — SQLite manager untuk IDX Bandarmology Bot
Rolling window 10 hari per saham.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import config

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Buka koneksi SQLite. Buat directory jika belum ada."""
    db_path = Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Buat tabel dan index jika belum ada."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS broksum (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                code          TEXT    NOT NULL,
                date          TEXT    NOT NULL,
                broker_code   TEXT    NOT NULL,
                broker_type   TEXT    DEFAULT 'Lokal',
                buy_lot       REAL    DEFAULT 0,
                sell_lot      REAL    DEFAULT 0,
                net_lot       REAL    DEFAULT 0,
                buy_value     REAL    DEFAULT 0,
                sell_value    REAL    DEFAULT 0,
                net_value     REAL    DEFAULT 0,
                buy_lot_cum   REAL    DEFAULT 0,
                sell_lot_cum  REAL    DEFAULT 0,
                buy_val_cum   REAL    DEFAULT 0,
                sell_val_cum  REAL    DEFAULT 0,
                buy_freq      INTEGER DEFAULT 0,
                sell_freq     INTEGER DEFAULT 0,
                buy_avg_price REAL    DEFAULT 0,
                sell_avg_price REAL   DEFAULT 0
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_code_date_broker
                ON broksum(code, date, broker_code);

            CREATE INDEX IF NOT EXISTS idx_code_date
                ON broksum(code, date);

            CREATE TABLE IF NOT EXISTS bandar_detector (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                code                  TEXT    NOT NULL,
                date                  TEXT    NOT NULL,
                broker_accdist        TEXT,
                number_broker_buysell REAL    DEFAULT 0,
                total_buyer           REAL    DEFAULT 0,
                total_seller          REAL    DEFAULT 0,
                total_value           REAL    DEFAULT 0,
                total_volume          REAL    DEFAULT 0,
                average_price         REAL    DEFAULT 0,
                avg_accdist           TEXT,
                avg_amount            REAL    DEFAULT 0,
                avg_pct               REAL    DEFAULT 0,
                avg_vol               REAL    DEFAULT 0,
                avg5_accdist          TEXT,
                avg5_amount           REAL    DEFAULT 0,
                avg5_pct              REAL    DEFAULT 0,
                avg5_vol              REAL    DEFAULT 0,
                top1_accdist          TEXT,
                top1_pct              REAL    DEFAULT 0,
                top1_amount           REAL    DEFAULT 0,
                top1_vol              REAL    DEFAULT 0,
                top3_accdist          TEXT,
                top3_pct              REAL    DEFAULT 0,
                top3_amount           REAL    DEFAULT 0,
                top3_vol              REAL    DEFAULT 0,
                top5_accdist          TEXT,
                top5_pct              REAL    DEFAULT 0,
                top5_amount           REAL    DEFAULT 0,
                top5_vol              REAL    DEFAULT 0,
                top10_accdist         TEXT,
                top10_pct             REAL    DEFAULT 0,
                top10_amount          REAL    DEFAULT 0,
                top10_vol             REAL    DEFAULT 0
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_bandar_code_date
                ON bandar_detector(code, date);

            CREATE TABLE IF NOT EXISTS daily_summary (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                code            TEXT    NOT NULL,
                date            TEXT    NOT NULL,
                open            REAL,
                high            REAL,
                low             REAL,
                close           REAL,
                volume          REAL,
                volume_rupiah   REAL,
                net_buy_total   REAL,
                foreign_net_buy REAL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_code_date
                ON daily_summary(code, date);
        """)

        # Migrasi: tambah kolom baru ke tabel broksum lama jika belum ada
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(broksum)")}
        new_cols = {
            "broker_type":    "TEXT    DEFAULT 'Lokal'",
            "buy_value":      "REAL    DEFAULT 0",
            "sell_value":     "REAL    DEFAULT 0",
            "buy_lot_cum":    "REAL    DEFAULT 0",
            "sell_lot_cum":   "REAL    DEFAULT 0",
            "buy_val_cum":    "REAL    DEFAULT 0",
            "sell_val_cum":   "REAL    DEFAULT 0",
            "buy_freq":       "INTEGER DEFAULT 0",
            "sell_freq":      "INTEGER DEFAULT 0",
            "buy_avg_price":  "REAL    DEFAULT 0",
            "sell_avg_price": "REAL    DEFAULT 0",
        }
        for col, col_def in new_cols.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE broksum ADD COLUMN {col} {col_def}")
                logger.info("Migrasi DB: tambah kolom broksum.%s", col)

    logger.info("Database initialized: %s", config.DB_PATH)


def save_daily_broksum(code: str, date: str, broksum_list: List[Dict]) -> None:
    """
    Simpan data broker summary harian ke SQLite.
    Gunakan INSERT OR REPLACE agar idempoten (bisa dijalankan ulang).
    """
    if not broksum_list:
        return

    rows = [
        (
            code,
            date,
            b.get("broker_code", ""),
            str(b.get("broker_type", "Lokal") or "Lokal"),
            float(b.get("buy_lot", 0) or 0),
            float(b.get("sell_lot", 0) or 0),
            float(b.get("net_lot", 0) or 0),
            float(b.get("buy_value", 0) or b.get("net_value", 0) or 0),
            float(b.get("sell_value", 0) or 0),
            float(b.get("net_value", 0) or 0),
            float(b.get("buy_lot_cum", 0) or 0),
            float(b.get("sell_lot_cum", 0) or 0),
            float(b.get("buy_val_cum", 0) or 0),
            float(b.get("sell_val_cum", 0) or 0),
            int(b.get("buy_freq", 0) or 0),
            int(b.get("sell_freq", 0) or 0),
            float(b.get("buy_avg_price", 0) or 0),
            float(b.get("sell_avg_price", 0) or 0),
        )
        for b in broksum_list
    ]

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO broksum
                (code, date, broker_code, broker_type,
                 buy_lot, sell_lot, net_lot,
                 buy_value, sell_value, net_value,
                 buy_lot_cum, sell_lot_cum, buy_val_cum, sell_val_cum,
                 buy_freq, sell_freq, buy_avg_price, sell_avg_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    logger.debug("Saved broksum %d rows for %s on %s", len(rows), code, date)


def save_bandar_detector(code: str, date: str, bd: Dict) -> None:
    """Simpan ringkasan bandar_detector dari Stockbit."""
    if not bd:
        return
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO bandar_detector
                (code, date,
                 broker_accdist, number_broker_buysell,
                 total_buyer, total_seller, total_value, total_volume, average_price,
                 avg_accdist, avg_amount, avg_pct, avg_vol,
                 avg5_accdist, avg5_amount, avg5_pct, avg5_vol,
                 top1_accdist, top1_pct, top1_amount, top1_vol,
                 top3_accdist, top3_pct, top3_amount, top3_vol,
                 top5_accdist, top5_pct, top5_amount, top5_vol,
                 top10_accdist, top10_pct, top10_amount, top10_vol)
            VALUES
                (?, ?,
                 ?, ?,
                 ?, ?, ?, ?, ?,
                 ?, ?, ?, ?,
                 ?, ?, ?, ?,
                 ?, ?, ?, ?,
                 ?, ?, ?, ?,
                 ?, ?, ?, ?,
                 ?, ?, ?, ?)
            """,
            (
                code, date,
                bd.get("broker_accdist", ""),
                float(bd.get("number_broker_buysell", 0) or 0),
                float(bd.get("total_buyer", 0) or 0),
                float(bd.get("total_seller", 0) or 0),
                float(bd.get("total_value", 0) or 0),
                float(bd.get("total_volume", 0) or 0),
                float(bd.get("average_price", 0) or 0),
                bd.get("avg_accdist", ""),
                float(bd.get("avg_amount", 0) or 0),
                float(bd.get("avg_pct", 0) or 0),
                float(bd.get("avg_vol", 0) or 0),
                bd.get("avg5_accdist", ""),
                float(bd.get("avg5_amount", 0) or 0),
                float(bd.get("avg5_pct", 0) or 0),
                float(bd.get("avg5_vol", 0) or 0),
                bd.get("top1_accdist", ""),
                float(bd.get("top1_pct", 0) or 0),
                float(bd.get("top1_amount", 0) or 0),
                float(bd.get("top1_vol", 0) or 0),
                bd.get("top3_accdist", ""),
                float(bd.get("top3_pct", 0) or 0),
                float(bd.get("top3_amount", 0) or 0),
                float(bd.get("top3_vol", 0) or 0),
                bd.get("top5_accdist", ""),
                float(bd.get("top5_pct", 0) or 0),
                float(bd.get("top5_amount", 0) or 0),
                float(bd.get("top5_vol", 0) or 0),
                bd.get("top10_accdist", ""),
                float(bd.get("top10_pct", 0) or 0),
                float(bd.get("top10_amount", 0) or 0),
                float(bd.get("top10_vol", 0) or 0),
            ),
        )
    logger.debug("Saved bandar_detector for %s on %s", code, date)


def save_daily_summary(code: str, date: str, summary: Dict) -> None:
    """Simpan ringkasan harga + net buy harian."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_summary
                (code, date, open, high, low, close, volume, volume_rupiah,
                 net_buy_total, foreign_net_buy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                date,
                summary.get("open"),
                summary.get("high"),
                summary.get("low"),
                summary.get("close"),
                summary.get("volume"),
                summary.get("volume_rupiah"),
                summary.get("net_buy_total"),
                summary.get("foreign_net_buy"),
            ),
        )


def get_broksum_ndays(code: str, days: int = 5) -> List[Dict]:
    """
    Ambil data broker summary N hari terakhir untuk saham tertentu.
    Return: list of dict per baris, diurutkan ascending by date.
    """
    cutoff = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT date, broker_code, buy_lot, sell_lot, net_lot, net_value
            FROM broksum
            WHERE code = ? AND date >= ?
            ORDER BY date ASC
            LIMIT ?
            """,
            (code, cutoff, days * 50),   # 50 broker per hari estimasi
        ).fetchall()
    return [dict(r) for r in rows]


def get_net_buy_history(code: str, days: int = 10) -> List[float]:
    """
    Ambil array net buy (rupiah) N hari terakhir.
    Aggregate semua broker per tanggal → sum net_value.
    Return: list float, ascending by date.
    """
    cutoff = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT date, SUM(net_value) AS total_net
            FROM broksum
            WHERE code = ? AND date >= ?
            GROUP BY date
            ORDER BY date ASC
            LIMIT ?
            """,
            (code, cutoff, days),
        ).fetchall()
    return [float(r["total_net"]) for r in rows]


def get_close_history(code: str, days: int = 5) -> List[Optional[float]]:
    """Ambil array close price N hari terakhir dari daily_summary."""
    cutoff = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT close FROM daily_summary
            WHERE code = ? AND date >= ? AND close IS NOT NULL
            ORDER BY date ASC LIMIT ?
            """,
            (code, cutoff, days),
        ).fetchall()
    return [float(r["close"]) for r in rows]


def get_volume_history(code: str, days: int = 20) -> List[Optional[float]]:
    """Ambil array volume N hari terakhir dari daily_summary."""
    cutoff = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT volume FROM daily_summary
            WHERE code = ? AND date >= ? AND volume IS NOT NULL
            ORDER BY date ASC LIMIT ?
            """,
            (code, cutoff, days),
        ).fetchall()
    return [float(r["volume"]) for r in rows]


def purge_old_data(keep_days: int = None) -> None:
    """
    Hapus data lebih dari N hari agar database tidak membengkak.
    Default: DB_ROLLING_DAYS dari config.
    """
    keep = keep_days or config.DB_ROLLING_DAYS
    cutoff = (datetime.now() - timedelta(days=keep)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        deleted_broksum = conn.execute(
            "DELETE FROM broksum WHERE date < ?", (cutoff,)
        ).rowcount
        deleted_summary = conn.execute(
            "DELETE FROM daily_summary WHERE date < ?", (cutoff,)
        ).rowcount
    logger.info(
        "Purged old data: %d broksum rows, %d summary rows (cutoff: %s)",
        deleted_broksum, deleted_summary, cutoff,
    )
