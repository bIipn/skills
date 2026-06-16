"""Deterministic backtest harness.

Replays a sequence of market snapshots through the full detection →
optimization → sizing → (simulated) execution pipeline and reports the
equity curve and summary statistics — the offline analogue of the live
engine, used to evaluate strategy parameters without touching the live
singleton or any network.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .arbitrage import scan_markets
from .config import settings
from .cross_venue import scan_cross_venue
from .dependencies import HeuristicClassifier, scan_combinatorial
from .execution import PaperExecutor
from .kalshi_client import MultiVenueFeed
from .polymarket_client import PaperFeed


@dataclass
class BacktestReport:
    ticks: int
    final_bankroll: float
    starting_bankroll: float
    total_pnl: float
    return_pct: float
    trades: int
    wins: int
    win_rate: float
    avg_profit: float
    max_drawdown_pct: float
    by_strategy: dict
    equity_curve: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("final_bankroll", "starting_bankroll", "total_pnl",
                  "return_pct", "win_rate", "avg_profit", "max_drawdown_pct",
                  "avg_profit"):
            d[k] = round(d[k], 2)
        return d

    def pretty(self) -> str:
        lines = [
            f"Backtest — {self.ticks} ticks",
            f"  Bankroll:   ${self.starting_bankroll:,.2f} -> ${self.final_bankroll:,.2f}",
            f"  PnL:        +${self.total_pnl:,.2f}  ({self.return_pct:+.2f}%)",
            f"  Trades:     {self.trades}  (win rate {self.win_rate:.1f}%)",
            f"  Avg/trade:  ${self.avg_profit:.2f}",
            f"  Max drawdown: {self.max_drawdown_pct:.2f}%",
            "  By strategy:",
        ]
        for k, v in self.by_strategy.items():
            lines.append(f"    {k:>16}: +${v['pnl']:.2f} over {v['trades']} trades")
        return "\n".join(lines)


async def _run(ticks: int, seed: int) -> BacktestReport:
    feed = PaperFeed(seed=seed)
    if settings.cross_venue:
        feed = MultiVenueFeed(feed, live=False, seed=seed)
    executor = PaperExecutor(seed=seed)
    classifier = HeuristicClassifier()

    bankroll = settings.starting_bankroll
    start = bankroll
    peak = bankroll
    max_dd = 0.0
    trades = wins = 0
    pnl_total = 0.0
    by_strategy: dict = {}
    equity = [{"t": 0, "equity": round(bankroll, 2)}]

    for tick in range(1, ticks + 1):
        markets = await feed.snapshot()
        opps = scan_markets(markets)
        opps.extend(scan_combinatorial(markets, classifier))
        if settings.cross_venue:
            opps.extend(scan_cross_venue(markets))
        opps.sort(key=lambda o: o.profit, reverse=True)

        for opp in opps:
            if opp.cost > bankroll:
                continue
            res = executor.execute(opp)
            trades += 1
            wins += 1 if res.success else 0
            pnl_total += res.realized_profit
            bankroll += res.realized_profit
            b = by_strategy.setdefault(opp.kind, {"pnl": 0.0, "trades": 0})
            b["pnl"] += res.realized_profit
            b["trades"] += 1

        peak = max(peak, bankroll)
        dd = (peak - bankroll) / peak * 100 if peak else 0.0
        max_dd = max(max_dd, dd)
        equity.append({"t": tick, "equity": round(bankroll, 2)})

    return BacktestReport(
        ticks=ticks,
        final_bankroll=bankroll,
        starting_bankroll=start,
        total_pnl=pnl_total,
        return_pct=(bankroll / start - 1) * 100 if start else 0.0,
        trades=trades,
        wins=wins,
        win_rate=(wins / trades * 100) if trades else 0.0,
        avg_profit=(pnl_total / trades) if trades else 0.0,
        max_drawdown_pct=max_dd,
        by_strategy={k: {"pnl": round(v["pnl"], 2), "trades": v["trades"]}
                     for k, v in by_strategy.items()},
        equity_curve=equity,
    )


def run_backtest(ticks: int = 200, seed: int = 42) -> BacktestReport:
    """Synchronous entry point for a reproducible backtest."""
    return asyncio.run(_run(ticks, seed))
