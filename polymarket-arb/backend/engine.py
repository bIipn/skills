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
from .dependencies import make_classifier, scan_combinatorial
from .execution import make_executor
from .models import Market, Opportunity, TradeResult
from .notifier import format_trade, make_notifier
from .polymarket_client import make_feed
from .storage import make_store


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
    # Per-strategy breakdown: kind -> {"pnl": float, "trades": int}
    by_strategy: dict = field(default_factory=lambda: {
        "single_condition": {"pnl": 0.0, "trades": 0},
        "rebalance": {"pnl": 0.0, "trades": 0},
        "combinatorial": {"pnl": 0.0, "trades": 0},
    })

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
        self.classifier = make_classifier()
        self.store = make_store()
        self.notifier = make_notifier()
        self.state = EngineState(
            bankroll=settings.starting_bankroll,
            starting_bankroll=settings.starting_bankroll,
        )
        self._restore_from_store()
        self.state.equity_curve.append(
            {"t": time.time(), "equity": round(self.state.bankroll, 2)}
        )
        self._running = False

    def _restore_from_store(self) -> None:
        """Rehydrate realized PnL and the trade log from persisted history."""
        agg = self.store.aggregates()
        self.state.trades_total = agg["trades_total"]
        self.state.trades_won = agg["trades_won"]
        self.state.realized_pnl = agg["realized_pnl"]
        self.state.bankroll = self.state.starting_bankroll + agg["realized_pnl"]
        for kind, v in agg["by_strategy"].items():
            self.state.by_strategy[kind] = dict(v)
        for d in reversed(self.store.recent(50)):
            self.state.recent_trades.appendleft(d)

    async def tick(self) -> list[TradeResult]:
        t0 = time.perf_counter()
        markets: list[Market] = await self.feed.snapshot()
        opps = scan_markets(markets)
        # Layer 2: combinatorial arbitrage across logically dependent markets.
        opps.extend(scan_combinatorial(markets, self.classifier))
        opps.sort(key=lambda o: o.profit, reverse=True)
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
            bucket = self.state.by_strategy.setdefault(
                opp.kind, {"pnl": 0.0, "trades": 0})
            bucket["pnl"] += res.realized_profit
            bucket["trades"] += 1
            trade_dict = res.to_dict()
            self.state.recent_trades.appendleft(trade_dict)
            self.store.record(res)
            if abs(res.realized_profit) >= settings.telegram_min_notify or not res.success:
                self.notifier.notify(format_trade(trade_dict))

        self.state.equity_curve.append(
            {"t": time.time(), "equity": round(self.state.bankroll, 2)}
        )
        return results

    async def run(self):
        self._running = True
        self.notifier.notify(
            f"🚀 <b>arb-bot online</b>\n{settings.banner()}\n"
            f"bankroll ${self.state.bankroll:,.2f}"
        )
        while self._running:
            try:
                await self.tick()
            except Exception as exc:  # keep the loop alive
                print(f"[engine] tick error: {exc}")
                self.notifier.notify_error(str(exc))
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
            "by_strategy": {
                k: {"pnl": round(v["pnl"], 2), "trades": v["trades"]}
                for k, v in s.by_strategy.items()
            },
        }


engine = ArbEngine()
