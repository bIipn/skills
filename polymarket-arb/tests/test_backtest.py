"""Tests for the backtest harness and persistence layer."""
import os

from backend.backtest import run_backtest
from backend.models import Opportunity, TradeResult
from backend.storage import TradeStore


def test_backtest_is_deterministic():
    a = run_backtest(ticks=60, seed=7)
    b = run_backtest(ticks=60, seed=7)
    assert a.final_bankroll == b.final_bankroll
    assert a.trades == b.trades
    assert a.by_strategy == b.by_strategy


def test_backtest_produces_trades_and_equity_curve():
    r = run_backtest(ticks=80, seed=1)
    assert r.ticks == 80
    assert r.trades > 0
    assert len(r.equity_curve) == 81  # initial point + one per tick
    assert 0 <= r.win_rate <= 100
    assert r.max_drawdown_pct >= 0
    # All three strategy families should appear over 80 ticks.
    assert set(r.by_strategy).issubset(
        {"single_condition", "rebalance", "combinatorial"})


def test_backtest_report_serializes():
    d = run_backtest(ticks=20, seed=3).to_dict()
    for key in ("final_bankroll", "total_pnl", "win_rate", "by_strategy", "equity_curve"):
        assert key in d


def _trade(kind, pnl, cost=10.0, success=True):
    opp = Opportunity(kind=kind, market_id="m", description="d", legs=[],
                      cost=cost, guaranteed_payoff=cost + pnl, profit=pnl,
                      edge_pct=0.1)
    return TradeResult(opportunity=opp, fills=[], realized_cost=cost,
                       realized_profit=pnl, success=success, note="t")


def test_storage_roundtrip(tmp_path):
    db = str(tmp_path / "t.db")
    store = TradeStore(db)
    store.record(_trade("single_condition", 5.0))
    store.record(_trade("rebalance", 2.0))
    store.record(_trade("single_condition", -1.0, success=False))

    agg = store.aggregates()
    assert agg["trades_total"] == 3
    assert agg["trades_won"] == 2
    assert round(agg["realized_pnl"], 2) == 6.0
    assert agg["by_strategy"]["single_condition"]["trades"] == 2
    assert len(store.recent(10)) == 3
    store.close()


def test_storage_persists_across_reopen(tmp_path):
    db = str(tmp_path / "p.db")
    s1 = TradeStore(db)
    s1.record(_trade("rebalance", 3.0))
    s1.close()

    s2 = TradeStore(db)
    assert s2.aggregates()["trades_total"] == 1
    assert round(s2.aggregates()["realized_pnl"], 2) == 3.0
    s2.close()
