"""Tests for Kalshi order building + venue routing (no network)."""
from backend.config import settings
from backend.execution import RoutedExecutor
from backend.kalshi_execution import build_order, parse_ticker_side, price_to_cents
from backend.models import Fill, Leg, Opportunity


def test_parse_ticker_side():
    assert parse_ticker_side("INXD-23DEC-B5000-YES") == ("INXD-23DEC-B5000", "yes")
    assert parse_ticker_side("BTC100K-NO") == ("BTC100K", "no")
    assert parse_ticker_side("k-cond-3-YES") == ("cond-3", "yes")  # twin prefix stripped


def test_price_to_cents_clamps():
    assert price_to_cents(0.42) == 42
    assert price_to_cents(0.005) == 1   # clamped to >= 1
    assert price_to_cents(0.999) == 99  # clamped to <= 99


def test_build_order_yes_and_no():
    yes = build_order(Leg("BTC100K-YES", "kalshi:YES", "BUY", 0.42, 10, "kalshi"))
    assert yes["ticker"] == "BTC100K"
    assert yes["action"] == "buy" and yes["side"] == "yes"
    assert yes["count"] == 10 and yes["yes_price"] == 42
    assert yes["type"] == "limit" and "client_order_id" in yes

    no = build_order(Leg("BTC100K-NO", "kalshi:NO", "BUY", 0.55, 5, "kalshi"))
    assert no["side"] == "no" and no["no_price"] == 55
    assert "yes_price" not in no


def _opp(legs):
    return Opportunity(kind="cross_venue", market_id="m", description="d", legs=legs,
                       cost=0.85, guaranteed_payoff=10.0, profit=1.5, edge_pct=0.1)


def test_routed_executor_refuses_when_venue_not_enabled():
    # Nothing is configured live by default → both legs fail, trade unsuccessful.
    opp = _opp([
        Leg("p-Y", "polymarket:YES", "BUY", 0.42, 10, "polymarket"),
        Leg("BTC-NO", "kalshi:NO", "BUY", 0.43, 10, "kalshi"),
    ])
    res = RoutedExecutor().execute(opp)
    assert res.success is False
    assert "not enabled" in res.note


def test_routed_executor_dispatches_by_venue(monkeypatch):
    # Pretend both venues are live-enabled, stub the network placement.
    monkeypatch.setattr(settings, "execution_mode", "live")
    monkeypatch.setattr(settings, "api_key", "x")
    monkeypatch.setattr(settings, "wallet_pk", "x")
    monkeypatch.setattr(settings, "kalshi_api_key_id", "x")
    monkeypatch.setattr(settings, "kalshi_private_key", "x")

    routed = RoutedExecutor()
    seen = []

    def poly_leg(leg):
        seen.append(("poly", leg.venue))
        return Fill(leg.token_id, leg.label, leg.side, leg.price, leg.price, leg.size, 0.0)

    def kalshi_leg(leg):
        seen.append(("kalshi", leg.venue))
        return Fill(leg.token_id, leg.label, leg.side, leg.price, leg.price, leg.size, 0.0)

    monkeypatch.setattr(routed.poly, "place_leg", poly_leg)
    monkeypatch.setattr(routed.kalshi, "place_leg", kalshi_leg)

    opp = _opp([
        Leg("p-Y", "polymarket:YES", "BUY", 0.42, 10, "polymarket"),
        Leg("BTC-NO", "kalshi:NO", "BUY", 0.43, 10, "kalshi"),
    ])
    res = routed.execute(opp)
    assert res.success is True
    assert ("poly", "polymarket") in seen and ("kalshi", "kalshi") in seen
    # cost = 0.42*10 + 0.43*10 = 8.5; profit = payoff(10) - 8.5 = 1.5
    assert round(res.realized_cost, 2) == 8.5
    assert round(res.realized_profit, 2) == 1.5
