"""Engine: the scan -> detect -> size -> execute -> track loop.

Holds all mutable bot state (bankroll, PnL curve, open/closed trades,
latest opportunities) and exposes a JSON-serialisable snapshot for the
dashboard. One tick:

  1. pull a market snapshot from the feed
  2. run the arbitrage detectors
  3. for each opportunity above threshold, execute (paper or live)
  4. update bankroll, realized PnL and the equity curve
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from .arbitrage import scan_markets
from .config import settings
from .execution import make_executor
from .models import Market, Opportunity, TradeResult
from .polymarket_client import make_feed


@dataclass
class EngineState:
    bankroll: float
    starting_bankroll: float
    realized_pnl: float = 0.0
    trades_total: int = 0
    trades_won: int = 0
    opportunities_found: int = 0
    equity_curve: deque = field(default_factory=lambda: deque(maxlen=500))
    recent_trades: deque = field(default_factory=lambda: deque(maxlen=50))
    live_opportunities: list[Opportunity] = field(default_factory=list)
    last_scan_ms: float = 0.0
    markets_scanned: int = 0
    tick: int = 0

    @property
    def win_rate(self) -> float:
        return self.trades_won / self.trades_total if self.trades_total else 0.0

    @property
    def avg_profit(self) -> float:
        return self.realized_pnl / self.trades_total if self.trades_total else 0.0


class ArbEngine:
    def __init__(self):
        self.feed = make_feed()
        self.executor = make_executor()
        self.state = EngineState(
            bankroll=settings.starting_bankroll,
            starting_bankroll=settings.starting_bankroll,
        )
        self.state.equity_curve.append(
            {"t": time.time(), "equity": settings.starting_bankroll}
        )
        self._running = False

    async def tick(self) -> list[TradeResult]:
        t0 = time.perf_counter()
        markets: list[Market] = await self.feed.snapshot()
        opps = scan_markets(markets)
        self.state.last_scan_ms = (time.perf_counter() - t0) * 1000.0
        self.state.markets_scanned = len(markets)
        self.state.live_opportunities = opps[:25]
        self.state.opportunities_found += len(opps)
        self.state.tick += 1

        results: list[TradeResult] = []
        for opp in opps:
            # Don't execute if we can't afford the outlay.
            if opp.cost > self.state.bankroll:
                continue
            res = self.executor.execute(opp)
            results.append(res)
            self.state.trades_total += 1
            if res.success:
                self.state.trades_won += 1
            self.state.realized_pnl += res.realized_profit
            self.state.bankroll += res.realized_profit
            self.state.recent_trades.appendleft(res.to_dict())

        self.state.equity_curve.append(
            {"t": time.time(), "equity": round(self.state.bankroll, 2)}
        )
        return results

    async def run(self):
        self._running = True
        while self._running:
            try:
                await self.tick()
            except Exception as exc:  # keep the loop alive
                print(f"[engine] tick error: {exc}")
            await asyncio.sleep(settings.scan_interval_s)

    def stop(self):
        self._running = False

    def snapshot(self) -> dict:
        s = self.state
        return {
            "banner": settings.banner(),
            "execution_live": settings.live_execution_enabled,
            "data_mode": settings.data_mode,
            "bankroll": round(s.bankroll, 2),
            "starting_bankroll": round(s.starting_bankroll, 2),
            "realized_pnl": round(s.realized_pnl, 2),
            "pnl_pct": round((s.bankroll / s.starting_bankroll - 1) * 100, 2),
            "trades_total": s.trades_total,
            "trades_won": s.trades_won,
            "win_rate": round(s.win_rate * 100, 1),
            "avg_profit": round(s.avg_profit, 2),
            "opportunities_found": s.opportunities_found,
            "last_scan_ms": round(s.last_scan_ms, 2),
            "markets_scanned": s.markets_scanned,
            "tick": s.tick,
            "equity_curve": list(s.equity_curve),
            "recent_trades": list(s.recent_trades),
            "live_opportunities": [o.to_dict() for o in s.live_opportunities],
        }


engine = ArbEngine()
