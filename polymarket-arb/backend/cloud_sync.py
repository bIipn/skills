"""Push the bot's live snapshot to Supabase so a hosted dashboard (Vercel) can
read it from anywhere — in demo or live mode alike.

The Mac mini holds the **service key** (write access) in its local .env; the
hosted dashboard only ever uses the public anon key (read-only via RLS). No
wallet key or secret is ever sent — only the public state snapshot (PnL,
opportunities, trades, fill report).

Best-effort and non-blocking: a failed sync never stalls or crashes the engine.
No-op unless PM_SUPABASE_URL and PM_SUPABASE_SERVICE_KEY are set.
"""
from __future__ import annotations

import asyncio
import json
import time

from .config import settings


class CloudSync:
    def __init__(self, url: str = "", service_key: str = "", interval: float = 5.0):
        self.url = url.rstrip("/")
        self.key = service_key
        self.interval = interval
        self.enabled = bool(url and service_key)
        self._last = 0.0

    def maybe_push(self, snapshot: dict) -> None:
        """Throttled, fire-and-forget upsert of the latest snapshot."""
        if not self.enabled:
            return
        now = time.time()
        if now - self._last < self.interval:
            return
        self._last = now
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(self._push_sync, snapshot))
        except RuntimeError:
            self._push_sync(snapshot)

    def _push_sync(self, snapshot: dict) -> None:
        import urllib.request

        body = json.dumps({
            "id": "live",
            "data": snapshot,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).encode()
        req = urllib.request.Request(
            f"{self.url}/rest/v1/bot_snapshot?on_conflict=id",
            data=body, method="POST",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
        )
        try:
            urllib.request.urlopen(req, timeout=8)  # noqa: S310
        except Exception as exc:  # best-effort; never break the engine
            print(f"[cloud_sync] push failed: {exc}")


def make_cloud_sync() -> CloudSync:
    return CloudSync(
        settings.supabase_url, settings.supabase_service_key,
        settings.cloud_sync_interval,
    )
