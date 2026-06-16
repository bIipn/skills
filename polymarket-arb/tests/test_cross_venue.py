"""Tests for the cross-venue (Polymarket ↔ Kalshi) arbitrage detector."""
import asyncio

from backend.cross_venue import detect_cross_venue, same_event, scan_cross_venue
from backend.kalshi_client import MultiVenueFeed
from backend.models import BookSide, Market, OrderLevel, Outcome
from backend.polymarket_client import PaperFeed


def _binary(cid, q, yes_ask, no_ask, venue, depth=1000.0):
    return Market(cid, q, venue=venue, mutually_exclusive=False, outcomes=[
        Outcome(f"{cid}-Y", "YES",
                BookSide([OrderLevel(yes_ask, depth)]),
                BookSide([OrderLevel(max(yes_ask - 0.02, 0.001), depth)])),
        Outcome(f"{cid}-N", "NO",
                BookSide([OrderLevel(no_ask, depth)]),
                BookSide([OrderLevel(max(no_ask - 0.02, 0.001), depth)])),
    ])


def test_same_event_matching():
    a = _binary("a", "Will BTC close above $100k this month?", 0.5, 0.5, "polymarket")
    b = _binary("b", "Will BTC close above $100k this month?", 0.5, 0.5, "kalshi")
    c = _binary("c", "Will the Lakers win the title?", 0.5, 0.5, "kalshi")
    assert same_event(a, b) is True
    assert same_event(a, c) is False


def test_cross_venue_arb_detected():
    # Polymarket prices BTC YES cheap (0.42); Kalshi prices it high, so NO@kalshi
    # is cheap (0.45). Buy YES@poly + NO@kalshi = 0.87 < 1 → guaranteed edge.
    poly = _binary("p", "Will BTC close above $100k this month?", 0.42, 0.60, "polymarket")
    kalshi = _binary("k", "Will BTC close above $100k this month?", 0.58, 0.45, "kalshi")
    opp = detect_cross_venue(poly, kalshi)
    assert opp is not None
    assert opp.kind == "cross_venue"
    assert opp.profit > 0
    assert opp.confidence < 1.0
    venues = {leg.venue for leg in opp.legs}
    assert venues == {"polymarket", "kalshi"}   # one leg on each venue


def test_no_cross_venue_when_aligned():
    poly = _binary("p", "Will BTC close above $100k this month?", 0.55, 0.47, "polymarket")
    kalshi = _binary("k", "Will BTC close above $100k this month?", 0.54, 0.48, "kalshi")
    assert detect_cross_venue(poly, kalshi) is None


def test_scan_skips_same_venue_and_unmatched():
    markets = [
        _binary("p", "Will BTC close above $100k this month?", 0.42, 0.60, "polymarket"),
        _binary("k", "Will BTC close above $100k this month?", 0.58, 0.45, "kalshi"),
        _binary("p2", "Will it rain tomorrow?", 0.5, 0.5, "polymarket"),
    ]
    found = scan_cross_venue(markets)
    assert len(found) == 1
    assert found[0].kind == "cross_venue"


def test_multi_venue_feed_emits_kalshi_twins():
    feed = MultiVenueFeed(PaperFeed(seed=3), live=False, seed=3)
    markets = asyncio.run(feed.snapshot())
    venues = {m.venue for m in markets}
    assert "polymarket" in venues
    assert "kalshi" in venues
    # Every Kalshi twin should mirror a Polymarket event question.
    kalshi_qs = {m.question for m in markets if m.venue == "kalshi"}
    poly_qs = {m.question for m in markets if m.venue == "polymarket"}
    assert kalshi_qs & poly_qs
