"""Real-time order-book pipeline via the Polymarket CLOB WebSocket.

The research stresses a streaming data path (WebSocket book updates, not REST
polling) because the detection-to-submission window is where the edge lives.
This module maintains a live in-memory book per token from the CLOB `market`
channel and exposes it to `LiveFeed`.

Two pieces:
  * LiveBookCache       -- pure, synchronous book state machine. Applies
                           `book` (full snapshot) and `price_change` (deltas)
                           messages. Fully unit-tested; no network.
  * CLOBWebSocketClient -- async connection loop that subscribes to token IDs
                           and feeds messages into the cache. Best-effort with
                           auto-reconnect.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from .config import settings
from .models import BookSide, OrderLevel


class LiveBookCache:
    """In-memory live books keyed by token_id. Synchronous and testable."""

    def __init__(self):
        # token_id -> {"asks": {price: size}, "bids": {price: size}, "ts": float}
        self._books: dict[str, dict] = {}

    def apply(self, msg: dict) -> None:
        """Apply one CLOB market-channel message to the cache."""
        event = msg.get("event_type") or msg.get("type")
        token = msg.get("asset_id") or msg.get("token_id") or msg.get("market")
        if not token:
            return

        if event == "book":
            self._books[token] = {
                "asks": {float(l["price"]): float(l["size"]) for l in msg.get("asks", [])},
                "bids": {float(l["price"]): float(l["size"]) for l in msg.get("bids", [])},
                "ts": time.time(),
            }
        elif event == "price_change":
            book = self._books.setdefault(token, {"asks": {}, "bids": {}, "ts": 0.0})
            for ch in msg.get("changes", msg.get("price_changes", [])):
                side = "asks" if str(ch.get("side", "")).upper() in ("SELL", "ASK") else "bids"
                price = float(ch["price"])
                size = float(ch["size"])
                if size <= 0:
                    book[side].pop(price, None)  # level cleared
                else:
                    book[side][price] = size
            book["ts"] = time.time()

    def get_book(self, token_id: str) -> Optional[tuple[BookSide, BookSide]]:
        """Return (asks, bids) BookSides sorted best-first, or None if cold."""
        b = self._books.get(token_id)
        if not b:
            return None
        asks = BookSide([OrderLevel(p, s) for p, s in sorted(b["asks"].items())])
        bids = BookSide([OrderLevel(p, s) for p, s in
                         sorted(b["bids"].items(), reverse=True)])
        return asks, bids

    def age(self, token_id: str) -> Optional[float]:
        b = self._books.get(token_id)
        return (time.time() - b["ts"]) if b else None

    @property
    def tokens(self) -> set[str]:
        return set(self._books)


class CLOBWebSocketClient:
    """Async subscriber that keeps a LiveBookCache warm. Best-effort."""

    def __init__(self, cache: Optional[LiveBookCache] = None):
        self.cache = cache or LiveBookCache()
        self._tokens: set[str] = set()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def subscribe(self, token_ids: list[str]) -> None:
        self._tokens.update(token_ids)

    def start(self) -> None:
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        try:
            import websockets
        except Exception as exc:  # pragma: no cover - optional dep
            print(f"[ws_feed] websockets not installed: {exc}")
            return

        backoff = 1.0
        while self._running:
            try:
                async with websockets.connect(settings.clob_ws_url) as ws:
                    await ws.send(json.dumps({
                        "type": "market",
                        "assets_ids": sorted(self._tokens),
                    }))
                    backoff = 1.0
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue
                        for msg in (data if isinstance(data, list) else [data]):
                            self.cache.apply(msg)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[ws_feed] reconnecting after error: {exc}")
                await asyncio.sleep(min(backoff, 30.0))
                backoff *= 2
