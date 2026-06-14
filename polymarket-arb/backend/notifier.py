"""Telegram push notifications (best-effort, non-blocking).

Posts to the Telegram Bot API when PM_TELEGRAM_BOT_TOKEN and
PM_TELEGRAM_CHAT_ID are set; otherwise every call is a silent no-op so the
bot runs unchanged without it. Sends never block the engine loop or raise.
"""
from __future__ import annotations

import asyncio
import time

from .config import settings


def format_trade(trade: dict) -> str:
    """Render a TradeResult dict as a short Telegram message."""
    pnl = trade.get("realized_profit", 0.0)
    arrow = "🟢" if pnl >= 0 else "🔴"
    sign = "+" if pnl >= 0 else "-"
    kind = trade.get("kind", "?").replace("_", " ")
    return (
        f"{arrow} <b>{kind}</b>  {sign}${abs(pnl):.2f}\n"
        f"{trade.get('description', '')[:90]}\n"
        f"cost ${trade.get('realized_cost', 0):.2f} · {trade.get('note', '')}"
    )


class TelegramNotifier:
    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        self._last_error_ts = 0.0

    def notify(self, text: str) -> None:
        """Fire-and-forget send; never blocks the caller, never raises."""
        if not self.enabled:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(self._send_sync, text))
        except RuntimeError:
            # No running loop (sync/CLI context) — send inline, best-effort.
            self._send_sync(text)

    def notify_error(self, text: str, throttle_s: float = 60.0) -> None:
        """Like notify() but rate-limited so a crash loop can't spam you."""
        now = time.time()
        if now - self._last_error_ts < throttle_s:
            return
        self._last_error_ts = now
        self.notify(f"⚠️ <b>arb-bot error</b>\n{text}")

    def _send_sync(self, text: str) -> None:
        import urllib.parse
        import urllib.request

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        try:
            urllib.request.urlopen(url, data=data, timeout=5)  # noqa: S310
        except Exception as exc:  # best-effort; don't let alerts break the bot
            print(f"[telegram] send failed: {exc}")


def make_notifier() -> TelegramNotifier:
    return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
