"""Market data feed.

Two implementations behind one interface:

  * PaperFeed -- generates synthetic but realistic order books locally,
    occasionally injecting genuine arbitrage so the engine and dashboard
    have something to react to. Default; needs no network or credentials.

  * LiveFeed  -- pulls real markets from the Polymarket Gamma API and live
    order books from the CLOB REST API. Read-only.

Both return `list[Market]` snapshots.
"""
from __future__ import annotations

import random
import time
from typing import Protocol

from .config import settings
from .models import BookSide, Market, OrderLevel, Outcome


class MarketFeed(Protocol):
    async def snapshot(self) -> list[Market]: ...


# --------------------------------------------------------------------------
# Paper / simulation feed
# --------------------------------------------------------------------------

_SAMPLE_QUESTIONS = [
    ("Will Trump win Pennsylvania?", "election"),
    ("Will BTC close above $100k this month?", "crypto"),
    ("Will the Fed cut rates in July?", "macro"),
    ("Will Lakers win the NBA championship?", "sports"),
    ("Will GPT-5 be released in 2026?", "tech"),
    ("Will it rain in NYC on July 4th?", "weather"),
    ("Will Argentina win the Copa America?", "sports"),
    ("Will ETH flip $5k before September?", "crypto"),
]

_ELECTION_GROUPS = [
    ("2028 Democratic nominee", ["Newsom", "Harris", "Whitmer", "Shapiro", "Other"]),
    ("Premier League winner", ["Man City", "Arsenal", "Liverpool", "Other"]),
]


def _book(best: float, size: float, levels: int = 4) -> BookSide:
    out = []
    p = best
    for i in range(levels):
        out.append(OrderLevel(price=round(min(max(p, 0.001), 0.999), 4),
                              size=round(size * (0.8 ** i), 2)))
        p += 0.01
    return BookSide(levels=out)


class PaperFeed:
    """Synthetic market generator with periodic real arbitrage injection."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self._tick = 0

    async def snapshot(self) -> list[Market]:
        self._tick += 1
        markets: list[Market] = []

        # Binary markets.
        for i, (q, cat) in enumerate(_SAMPLE_QUESTIONS):
            fair = self.rng.uniform(0.2, 0.8)
            spread = self.rng.uniform(0.005, 0.02)
            yes_ask = fair + spread
            no_ask = (1 - fair) + spread

            # ~12% of ticks: inject a real single-condition arb on this market.
            if self.rng.random() < 0.12:
                gap = self.rng.uniform(0.02, 0.08)
                yes_ask = fair - gap / 2
                no_ask = (1 - fair) - gap / 2

            depth = self.rng.uniform(200, 2000)
            yes = Outcome(
                token_id=f"{i}-YES", label="YES",
                asks=_book(yes_ask, depth), bids=_book(max(yes_ask - 0.02, 0.001), depth),
            )
            no = Outcome(
                token_id=f"{i}-NO", label="NO",
                asks=_book(no_ask, depth), bids=_book(max(no_ask - 0.02, 0.001), depth),
            )
            markets.append(Market(
                condition_id=f"cond-{i}", question=q, outcomes=[yes, no],
                mutually_exclusive=False, category=cat, updated_at=time.time(),
            ))

        # Mutually-exclusive groups (rebalance candidates).
        for gi, (q, names) in enumerate(_ELECTION_GROUPS):
            raw = [self.rng.uniform(0.1, 1.0) for _ in names]
            s = sum(raw)
            probs = [r / s for r in raw]
            inject = self.rng.random() < 0.18
            outcomes = []
            for ni, (name, pr) in enumerate(zip(names, probs)):
                margin = -self.rng.uniform(0.01, 0.05) if inject else self.rng.uniform(0.005, 0.03)
                ask = max(pr + margin / len(names), 0.001)
                depth = self.rng.uniform(150, 1500)
                outcomes.append(Outcome(
                    token_id=f"grp{gi}-{ni}", label=name,
                    asks=_book(ask, depth), bids=_book(max(ask - 0.02, 0.001), depth),
                ))
            markets.append(Market(
                condition_id=f"group-{gi}", question=q, outcomes=outcomes,
                mutually_exclusive=True, category="election", updated_at=time.time(),
            ))

        # Logically dependent pair: B ("...by 5+ points") implies A.
        # ~16% of ticks inject an inconsistency where A_YES is cheap relative
        # to B_YES's bid, creating a guaranteed combinatorial arb
        # (buy A_YES + B_NO for < $1, floor $1 in every feasible world).
        if self.rng.random() < 0.16:
            a_yes_ask, a_no_ask = 0.40, 0.62   # A_YES underpriced
            b_yes_ask, b_no_ask = 0.55, 0.45   # B_NO cheap → buy A_YES + B_NO < $1
        else:
            a_yes_ask, a_no_ask = 0.56, 0.46   # consistent: price(B) <= price(A)
            b_yes_ask, b_no_ask = 0.30, 0.72
        depth = self.rng.uniform(300, 1200)
        markets.append(Market(
            condition_id="dep-A", question="Will Republicans win Pennsylvania?",
            mutually_exclusive=False, category="election", updated_at=time.time(),
            outcomes=[
                Outcome("dep-A-YES", "YES", _book(a_yes_ask, depth),
                        _book(max(a_yes_ask - 0.02, 0.001), depth)),
                Outcome("dep-A-NO", "NO", _book(a_no_ask, depth),
                        _book(max(a_no_ask - 0.02, 0.001), depth)),
            ],
        ))
        markets.append(Market(
            condition_id="dep-B",
            question="Will Republicans win Pennsylvania by 5+ points?",
            mutually_exclusive=False, category="election", updated_at=time.time(),
            outcomes=[
                Outcome("dep-B-YES", "YES", _book(b_yes_ask, depth),
                        _book(max(b_yes_ask - 0.02, 0.001), depth)),
                Outcome("dep-B-NO", "NO", _book(b_no_ask, depth),
                        _book(max(b_no_ask - 0.02, 0.001), depth)),
            ],
        ))

        return markets


# --------------------------------------------------------------------------
# Live (read-only) feed
# --------------------------------------------------------------------------

class LiveFeed:
    """Read real markets + order books from Polymarket public APIs."""

    def __init__(self, limit: int = 40):
        self.limit = limit
        self._client = None
        self._ws = None
        if settings.use_ws:
            from .ws_feed import CLOBWebSocketClient
            self._ws = CLOBWebSocketClient()

    def _http(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def _book_for(self, http, token_id):
        """Prefer a warm WebSocket book; fall back to a REST snapshot."""
        if self._ws is not None:
            cached = self._ws.cache.get_book(str(token_id))
            age = self._ws.cache.age(str(token_id))
            if cached is not None and age is not None and age <= settings.ws_max_age_s:
                return cached
        return await self._fetch_book(http, token_id)

    async def snapshot(self) -> list[Market]:
        http = self._http()
        # Active, non-archived markets from the Gamma API.
        r = await http.get(
            f"{settings.gamma_rest_url}/markets",
            params={"active": "true", "closed": "false", "limit": self.limit},
        )
        r.raise_for_status()
        rows = r.json()

        markets: list[Market] = []
        for row in rows:
            tokens = row.get("clobTokenIds") or row.get("tokens")
            if not tokens:
                continue
            if isinstance(tokens, str):
                import json
                try:
                    tokens = json.loads(tokens)
                except Exception:
                    continue
            outcome_names = row.get("outcomes")
            if isinstance(outcome_names, str):
                import json
                try:
                    outcome_names = json.loads(outcome_names)
                except Exception:
                    outcome_names = ["YES", "NO"]
            if self._ws is not None:
                self._ws.subscribe([str(t) for t in tokens])
            outcomes = []
            for tid, name in zip(tokens, outcome_names or []):
                book = await self._book_for(http, tid)
                if book is None:
                    continue
                asks, bids = book
                outcomes.append(Outcome(token_id=str(tid), label=str(name),
                                        asks=asks, bids=bids))
            if len(outcomes) >= 2:
                markets.append(Market(
                    condition_id=str(row.get("conditionId", row.get("id", ""))),
                    question=row.get("question", ""),
                    outcomes=outcomes,
                    mutually_exclusive=len(outcomes) > 2,
                    category=row.get("category", ""),
                    updated_at=time.time(),
                ))
        # Kick off the live WS subscription once tokens are known (idempotent).
        if self._ws is not None:
            self._ws.start()
        return markets

    async def _fetch_book(self, http, token_id):
        try:
            r = await http.get(f"{settings.clob_rest_url}/book",
                               params={"token_id": token_id})
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None

        def side(raw, reverse):
            levels = [OrderLevel(price=float(x["price"]), size=float(x["size"]))
                      for x in raw]
            levels.sort(key=lambda l: l.price, reverse=reverse)
            return BookSide(levels=levels)

        # asks sorted ascending (best = lowest), bids descending (best = highest)
        asks = side(data.get("asks", []), reverse=False)
        bids = side(data.get("bids", []), reverse=True)
        return asks, bids


def make_feed() -> MarketFeed:
    if settings.data_mode == "live":
        return LiveFeed()
    return PaperFeed()
