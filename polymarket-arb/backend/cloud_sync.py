"""Push the bot's live snapshot to the hosted (Vercel) dashboard so it's
viewable from anywhere — in demo or live mode alike.

The Mac mini POSTs its public snapshot to the Vercel `/api/ingest` serverless
function, authenticated with a shared secret token. Vercel KV stores the latest
snapshot; the dashboard reads it via `/api/state`. Only the **public** state
(PnL, opportunities, trades, fill report) is sent — never a wallet key or any
secret.

Best-effort and non-blocking: a failed sync never stalls or crashes the engine.
No-op unless PM_CLOUD_INGEST_URL and PM_CLOUD_INGEST_TOKEN are set.
"""
from __future__ import annotations

import asyncio
import json
import time

from .config import settings


class CloudSync:
    def __init__(self, ingest_url: str = "", token: str = "", interval: float = 5.0):
        self.url = ingest_url
        self.token = token
        self.interval = interval
        self.enabled = bool(ingest_url and token)
        self._last = 0.0

    def maybe_push(self, snapshot: dict) -> None:
        """Throttled, fire-and-forget push of the latest snapshot."""
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

        body = json.dumps({"data": snapshot}).encode()
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            urllib.request.urlopen(req, timeout=8)  # noqa: S310
        except Exception as exc:  # best-effort; never break the engine
            print(f"[cloud_sync] push failed: {exc}")


def make_cloud_sync() -> CloudSync:
    return CloudSync(
        settings.cloud_ingest_url, settings.cloud_ingest_token,
        settings.cloud_sync_interval,
    )
