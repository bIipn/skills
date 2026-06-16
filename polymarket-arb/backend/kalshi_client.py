"""Kalshi venue adapter + multi-venue feed.

Kalshi is the U.S.-regulated (CFTC) prediction market with a public API. Its
binary markets map cleanly onto our Market model (YES/NO outcomes, prices in
0..1), so the same detection/optimization/sizing engine runs on it unchanged.

  * KalshiLiveFeed  -- read real open Kalshi markets (read-only; best-effort).
  * MultiVenueFeed  -- merge a primary (Polymarket) feed with Kalshi so the
                       cross-venue detector can compare the same event across
                       venues. In paper mode it derives correlated Kalshi
                       "twins" of shared events that occasionally diverge enough
                       to create a genuine cross-venue arbitrage.

Note: cross-venue execution is intentionally not automated here — settling two
legs on two venues has resolution-source risk and needs accounts/capital on
both sides. This adapter powers detection and the (simulated) paper executor.
"""
from __future__ import annotations

import random
import time
from typing import Optional, Protocol

from .config import settings
from .models import BookSide, Market, OrderLevel, Outcome
from .polymarket_client import _book, make_feed


class MarketFeed(Protocol):
    async def snapshot(self) -> list[Market]: ...


# --------------------------------------------------------------------------
# Live Kalshi feed (read-only)
# --------------------------------------------------------------------------

class KalshiLiveFeed:
    """Read open Kalshi markets via the public trade API (best-effort)."""

    def __init__(self, limit: int = 100):
        self.limit = limit
        self._client = None

    def _http(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def snapshot(self) -> list[Market]:
        http = self._http()
        try:
            r = await http.get(
                f"{settings.kalshi_rest_url}/markets",
                params={"status": "open", "limit": self.limit},
            )
            r.raise_for_status()
            rows = r.json().get("markets", [])
        except Exception as exc:
            print(f"[kalshi] market fetch failed: {exc}")
            return []

        markets: list[Market] = []
        for row in rows:
            # Kalshi quotes are in cents (1..99). yes_ask/no_ask = cost to buy.
            yes_ask = row.get("yes_ask")
            no_ask = row.get("no_ask")
            if not yes_ask or not no_ask:
                continue
            yes_p, no_p = yes_ask / 100.0, no_ask / 100.0
            # The markets endpoint gives top-of-book only; use a nominal size.
            size = float(row.get("open_interest") or 100) or 100.0
            ticker = str(row.get("ticker", ""))
            markets.append(Market(
                condition_id=ticker,
                question=row.get("title", row.get("subtitle", ticker)),
                venue="kalshi", mutually_exclusive=False,
                category=row.get("category", ""), updated_at=time.time(),
                outcomes=[
                    Outcome(f"{ticker}-YES", "YES",
                            BookSide([OrderLevel(yes_p, size)]),
                            BookSide([OrderLevel(max(yes_p - 0.02, 0.001), size)])),
                    Outcome(f"{ticker}-NO", "NO",
                            BookSide([OrderLevel(no_p, size)]),
                            BookSide([OrderLevel(max(no_p - 0.02, 0.001), size)])),
                ],
            ))
        return markets


# --------------------------------------------------------------------------
# Multi-venue feed (Polymarket + Kalshi)
# --------------------------------------------------------------------------

def _kalshi_twin(pm: Market, rng: random.Random) -> Optional[Market]:
    """Derive a correlated Kalshi market for the same event as a Polymarket
    binary, with small venue divergence and an occasional larger gap that
    creates a real cross-venue arbitrage."""
    if len(pm.outcomes) != 2:
        return None
    yes = pm.outcomes[0]
    if yes.best_ask is None:
        return None
    base = yes.best_ask - 0.01           # approx fair
    div = rng.uniform(-0.02, 0.02)       # normal venue disagreement
    if rng.random() < 0.15:              # inject an arbitrageable gap
        div = rng.choice([-1, 1]) * rng.uniform(0.04, 0.09)
    k_fair = min(max(base + div, 0.05), 0.95)
    s = rng.uniform(0.005, 0.015)
    depth = rng.uniform(200, 1500)
    k_yes, k_no = k_fair + s, (1 - k_fair) + s
    return Market(
        condition_id=f"k-{pm.condition_id}", question=pm.question,
        venue="kalshi", mutually_exclusive=False, category=pm.category,
        updated_at=time.time(),
        outcomes=[
            Outcome(f"k-{yes.token_id}", "YES", _book(k_yes, depth),
                    _book(max(k_yes - 0.02, 0.001), depth)),
            Outcome(f"k-{pm.outcomes[1].token_id}", "NO", _book(k_no, depth),
                    _book(max(k_no - 0.02, 0.001), depth)),
        ],
    )


class MultiVenueFeed:
    """Combine a primary (Polymarket) feed with Kalshi for cross-venue arb."""

    def __init__(self, primary: MarketFeed, live: bool, seed: int | None = None):
        self.primary = primary
        self.live = live
        self.rng = random.Random(seed)
        self._kalshi = KalshiLiveFeed() if live else None

    async def snapshot(self) -> list[Market]:
        markets = await self.primary.snapshot()
        if self.live:
            markets = list(markets) + await self._kalshi.snapshot()
            return markets
        # Paper: derive Kalshi twins of the binary sample markets.
        twins = []
        for m in markets:
            if m.condition_id.startswith("cond-"):
                t = _kalshi_twin(m, self.rng)
                if t:
                    twins.append(t)
        return list(markets) + twins


def make_multi_venue_feed() -> MarketFeed:
    return MultiVenueFeed(make_feed(), live=(settings.data_mode == "live"))
