"""Tests for the faster-trader competition model + Kalshi-only feed."""
import asyncio

from backend.config import settings
from backend.execution import PaperExecutor
from backend.kalshi_client import make_kalshi_feed
from backend.models import Leg, Opportunity


def _opp(kind):
    return Opportunity(kind=kind, market_id="m", description="d",
                       legs=[Leg("y", "YES", "BUY", 0.45, 10),
                             Leg("n", "NO", "BUY", 0.45, 10)],
                       cost=9.0, guaranteed_payoff=10.0, profit=1.0, edge_pct=0.1)


def test_full_competition_always_misses_single_condition(monkeypatch):
    monkeypatch.setattr(settings, "competition", 1.0)
    res = PaperExecutor(seed=5).execute(_opp("single_condition"))
    assert res.success is False
    assert "faster trader" in res.note


def test_no_competition_never_misses(monkeypatch):
    monkeypatch.setattr(settings, "competition", 0.0)
    monkeypatch.setattr(settings, "simulate_partial", 0.0)
    res = PaperExecutor(seed=5).execute(_opp("single_condition"))
    assert "faster trader" not in res.note


def test_combinatorial_less_contested_than_single(monkeypatch):
    # At the same competition level, combinatorial should be missed less often.
    monkeypatch.setattr(settings, "competition", 0.6)
    monkeypatch.setattr(settings, "simulate_partial", 0.0)

    def miss_rate(kind):
        ex = PaperExecutor(seed=99)
        misses = sum("faster trader" in ex.execute(_opp(kind)).note for _ in range(400))
        return misses / 400

    assert miss_rate("combinatorial") < miss_rate("single_condition")


def test_kalshi_only_feed_tags_venue():
    monkeypatch_mode = settings.data_mode
    feed = make_kalshi_feed()  # paper mode by default → venue-tagged PaperFeed
    if monkeypatch_mode != "live":
        markets = asyncio.run(feed.snapshot())
        assert markets and all(m.venue == "kalshi" for m in markets)
