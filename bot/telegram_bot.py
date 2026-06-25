"""
bot/telegram_bot.py — Kirim 7 pesan laporan ke Telegram.

Menggunakan python-telegram-bot v20 (async).
Delay 1 detik antar pesan untuk menghindari Telegram rate limit.
"""

import asyncio
import logging
from typing import Dict

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from bot.formatter import (
    format_header,
    format_top5_was,
    format_top5_fs,
    format_top5_tcn,
    format_top5_sad,
    format_watchlist_cfs,
)

logger = logging.getLogger(__name__)


async def send_report(data: Dict, token: str = None, chat_id: str = None) -> bool:
    """
    Kirim 7 pesan laporan ke Telegram channel/group.

    Args:
        data:    dict dari bot.formatter.build_report_data()
        token:   Bot token (default: dari config)
        chat_id: Chat/Channel ID (default: dari config)

    Return:
        True jika semua pesan berhasil, False jika ada yang gagal.
    """
    token   = token   or config.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or config.TELEGRAM_CHAT_ID

    if token == "YOUR_BOT_TOKEN_HERE":
        logger.error("Token Telegram belum diisi di .env!")
        return False

    bot = Bot(token=token)
    success = True

    messages = [
        ("Header",      format_header(data)),
        ("Top5 WAS",    format_top5_was(data.get("was_ranking", []))),
        ("Top5 FS",     format_top5_fs(data.get("fs_ranking", []))),
        ("Top5 TCN",    format_top5_tcn(data.get("tcn_ranking", []))),
        ("Top5 SAD",    format_top5_sad(data.get("sad_ranking", []))),
        ("Watchlist",   format_watchlist_cfs(data.get("cfs_ranking", []))),
    ]

    for label, text in messages:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            logger.info("✅ Pesan terkirim: %s", label)
        except TelegramError as e:
            logger.error("❌ Gagal kirim pesan %s: %s", label, e)
            success = False

        await asyncio.sleep(config.TELEGRAM_MESSAGE_DELAY)

    return success


async def send_error_notification(message: str, token: str = None, chat_id: str = None) -> None:
    """Kirim notifikasi error singkat ke Telegram."""
    token   = token   or config.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or config.TELEGRAM_CHAT_ID

    if token == "YOUR_BOT_TOKEN_HERE":
        logger.warning("Token belum diisi, skip notif error.")
        return

    bot = Bot(token=token)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ {message}",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as e:
        logger.error("Gagal kirim notif error: %s", e)


def run_send_report(data: Dict) -> bool:
    """Synchronous wrapper untuk dipanggil dari main.py."""
    return asyncio.run(send_report(data))
