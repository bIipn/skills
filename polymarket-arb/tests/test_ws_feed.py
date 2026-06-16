"""Tests for the real-time WebSocket order-book cache state machine."""
from backend.ws_feed import LiveBookCache


def test_book_snapshot_applied():
    c = LiveBookCache()
    c.apply({
        "event_type": "book", "asset_id": "tok1",
        "asks": [{"price": "0.55", "size": "100"}, {"price": "0.56", "size": "50"}],
        "bids": [{"price": "0.53", "size": "80"}, {"price": "0.52", "size": "40"}],
    })
    asks, bids = c.get_book("tok1")
    assert asks.best == 0.55          # asks sorted ascending → lowest first
    assert bids.best == 0.53          # bids sorted descending → highest first
    assert asks.levels[1].price == 0.56


def test_cold_token_returns_none():
    assert LiveBookCache().get_book("nope") is None


def test_price_change_updates_and_clears_levels():
    c = LiveBookCache()
    c.apply({
        "event_type": "book", "asset_id": "t",
        "asks": [{"price": "0.60", "size": "100"}],
        "bids": [{"price": "0.58", "size": "100"}],
    })
    # New better ask appears, old ask cleared (size 0).
    c.apply({
        "event_type": "price_change", "asset_id": "t",
        "changes": [
            {"price": "0.59", "side": "SELL", "size": "70"},
            {"price": "0.60", "side": "SELL", "size": "0"},
        ],
    })
    asks, _ = c.get_book("t")
    assert asks.best == 0.59
    assert all(l.price != 0.60 for l in asks.levels)  # cleared level gone


def test_price_change_on_cold_token_creates_book():
    c = LiveBookCache()
    c.apply({
        "event_type": "price_change", "asset_id": "fresh",
        "changes": [{"price": "0.4", "side": "BUY", "size": "10"}],
    })
    asks, bids = c.get_book("fresh")
    assert bids.best == 0.4
    assert asks.best is None


def test_age_and_tokens_tracking():
    c = LiveBookCache()
    assert c.tokens == set()
    c.apply({"event_type": "book", "asset_id": "x", "asks": [], "bids": []})
    assert "x" in c.tokens
    assert c.age("x") is not None
    assert c.age("missing") is None
