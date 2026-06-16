"""Tests for the partial-fill unwind safety net."""
from backend.config import settings
from backend.execution import LiveExecutor, PaperExecutor, RoutedExecutor
from backend.models import Fill, Leg, Opportunity


def _opp(legs, payoff=10.0):
    return Opportunity(kind="cross_venue", market_id="m", description="d", legs=legs,
                       cost=0.85, guaranteed_payoff=payoff, profit=1.5, edge_pct=0.1)


def _legs():
    return [
        Leg("p-Y", "polymarket:YES", "BUY", 0.42, 10, "polymarket"),
        Leg("k-N", "kalshi:NO", "BUY", 0.43, 10, "kalshi"),
    ]


def test_paper_partial_fill_unwinds(monkeypatch):
    monkeypatch.setattr(settings, "simulate_partial", 1.0)  # force a partial fill
    res = PaperExecutor(seed=1).execute(_opp(_legs()))
    assert res.success is False
    assert "PARTIAL FILL" in res.note
    # Flattened → small loss, not a full position loss.
    assert res.realized_profit <= 0
    assert abs(res.realized_profit) < 2.0  # only the unwind slippage, not naked exposure


def test_paper_normal_when_partial_disabled(monkeypatch):
    monkeypatch.setattr(settings, "simulate_partial", 0.0)
    res = PaperExecutor(seed=1).execute(_opp(_legs()))
    assert "PARTIAL FILL" not in res.note


def test_routed_unwinds_filled_leg_when_counterpart_fails(monkeypatch):
    monkeypatch.setattr(settings, "execution_mode", "live")
    monkeypatch.setattr(settings, "api_key", "x")
    monkeypatch.setattr(settings, "wallet_pk", "x")
    # Kalshi NOT enabled → its leg fails; the filled Polymarket leg must unwind.
    monkeypatch.setattr(settings, "kalshi_api_key_id", "")
    monkeypatch.setattr(settings, "kalshi_private_key", "")

    routed = RoutedExecutor()
    calls = []

    def poly_leg(leg):
        calls.append((leg.side, leg.token_id))
        return Fill(leg.token_id, leg.label, leg.side, leg.price, leg.price, leg.size, 0.0)

    monkeypatch.setattr(routed.poly, "place_leg", poly_leg)

    res = routed.execute(_opp(_legs()))
    assert res.success is False
    assert "PARTIAL FILL" in res.note
    # Polymarket leg was BOUGHT then SOLD back (unwound).
    assert ("BUY", "p-Y") in calls
    assert ("SELL", "p-Y") in calls


def test_unwind_failure_flags_naked_position(monkeypatch):
    monkeypatch.setattr(settings, "execution_mode", "live")
    monkeypatch.setattr(settings, "api_key", "x")
    monkeypatch.setattr(settings, "wallet_pk", "x")
    monkeypatch.setattr(settings, "kalshi_api_key_id", "")
    monkeypatch.setattr(settings, "kalshi_private_key", "")

    routed = RoutedExecutor()

    def poly_leg(leg):
        if leg.side == "BUY":
            return Fill(leg.token_id, leg.label, leg.side, leg.price, leg.price, leg.size, 0.0)
        raise RuntimeError("sell rejected")  # unwind itself fails

    monkeypatch.setattr(routed.poly, "place_leg", poly_leg)
    res = routed.execute(_opp(_legs()))
    assert res.success is False
    assert "NAKED POSITION" in res.note
