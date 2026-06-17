"""Tests for the Kalshi market-making mode."""
from backend.config import settings
from backend.market_maker import MarketMaker
from backend.models import BookSide, Market, OrderLevel, Outcome


def _market(cid, bid, ask, venue="kalshi"):
    return Market(cid, "Q?", venue=venue, mutually_exclusive=False, outcomes=[
        Outcome(f"{cid}-Y", "YES",
                BookSide([OrderLevel(ask, 500)]),       # asks (buy YES here)
                BookSide([OrderLevel(bid, 500)])),       # bids (sell YES here)
        Outcome(f"{cid}-N", "NO",
                BookSide([OrderLevel(1 - bid, 500)]),
                BookSide([OrderLevel(1 - ask, 500)])),
    ])


def test_quote_centers_on_mid_with_target_spread(monkeypatch):
    monkeypatch.setattr(settings, "mm_spread", 0.02)
    mm = MarketMaker(seed=1)
    q = mm._quote_for(_market("k1", 0.48, 0.52))
    assert q is not None
    assert round(q.bid, 3) == 0.48   # mid 0.50 - 0.02
    assert round(q.ask, 3) == 0.52   # mid 0.50 + 0.02


def test_step_accrues_rewards_and_quotes(monkeypatch):
    monkeypatch.setattr(settings, "mm_fill_prob", 0.0)  # no fills → isolate rewards
    mm = MarketMaker(seed=1)
    stats = mm.step([_market("k1", 0.48, 0.52), _market("k2", 0.30, 0.34)])
    assert stats["quoted"] == 2
    assert stats["rewards"] > 0
    assert mm.state.rewards > 0


def test_inventory_cap_stops_one_sided_quoting(monkeypatch):
    monkeypatch.setattr(settings, "mm_max_inventory", 100)
    mm = MarketMaker(seed=1)
    mm.state.inventory["k1"] = 100  # at the long cap
    q = mm._quote_for(_market("k1", 0.48, 0.52))
    assert q.bid_size == 0          # can't buy more (would exceed inventory cap)
    assert q.ask_size > 0           # can still sell down


def test_net_pnl_positive_over_many_ticks(monkeypatch):
    # Rewards + spread should dominate zero-mean inventory noise.
    monkeypatch.setattr(settings, "venue", "kalshi")
    mm = MarketMaker(seed=7)
    for _ in range(300):
        mm.step([_market("k1", 0.48, 0.52), _market("k2", 0.60, 0.64)])
    s = mm.snapshot()
    assert s["rewards"] > 0
    assert s["net_pnl"] > 0
    assert s["quotes_posted"] > 0


def test_venue_filter_in_kalshi_mode(monkeypatch):
    monkeypatch.setattr(settings, "venue", "kalshi")
    monkeypatch.setattr(settings, "mm_fill_prob", 0.0)
    mm = MarketMaker(seed=1)
    stats = mm.step([
        _market("k1", 0.48, 0.52, venue="kalshi"),
        _market("p1", 0.48, 0.52, venue="polymarket"),  # should be skipped
    ])
    assert stats["quoted"] == 1
