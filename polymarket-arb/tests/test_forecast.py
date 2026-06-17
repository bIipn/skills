"""Tests for the execution-risk fill forecaster (heuristic path)."""
from collections import deque

from backend.forecast import FillForecaster
from backend.models import BookSide, Leg, Market, OrderLevel, Opportunity, Outcome


def _opp(token_ids):
    legs = [Leg(t, "YES", "BUY", 0.45, 10) for t in token_ids]
    return Opportunity(kind="single_condition", market_id="m", description="d",
                       legs=legs, cost=0.9, guaranteed_payoff=10.0, profit=1.0,
                       edge_pct=0.1)


def _seed(f, token, values):
    f._series[token] = deque(values, maxlen=f.history)


def test_no_history_is_neutral_optimistic():
    f = FillForecaster()
    assert f.score(_opp(["a", "b"])) == 1.0  # nothing to penalise yet


def test_stable_low_spread_scores_high():
    f = FillForecaster()
    # combined spread = 0.40 + 0.45 = 0.85, flat → plenty of cushion
    _seed(f, "a", [0.40] * 10)
    _seed(f, "b", [0.45] * 10)
    assert f.score(_opp(["a", "b"])) > 0.8


def test_spread_trending_toward_one_scores_low():
    f = FillForecaster(horizon=6)
    # combined rising 0.86 -> 0.99: cushion nearly gone, trend adverse
    a = [0.43, 0.44, 0.455, 0.47, 0.485, 0.495]
    b = [0.43, 0.44, 0.455, 0.47, 0.485, 0.495]
    _seed(f, "a", a)
    _seed(f, "b", b)
    assert f.score(_opp(["a", "b"])) < 0.45


def test_spread_already_gone_scores_zero():
    f = FillForecaster()
    _seed(f, "a", [0.55] * 6)
    _seed(f, "b", [0.55] * 6)   # combined 1.10 >= 1 → no cushion
    assert f.score(_opp(["a", "b"])) == 0.0


def test_observe_builds_series():
    f = FillForecaster()
    m = Market("c", "Q?", mutually_exclusive=False, outcomes=[
        Outcome("a", "YES", BookSide([OrderLevel(0.4, 100)]), BookSide([OrderLevel(0.38, 100)])),
        Outcome("b", "NO", BookSide([OrderLevel(0.45, 100)]), BookSide([OrderLevel(0.43, 100)])),
    ])
    for _ in range(5):
        f.observe([m])
    assert len(f._series["a"]) == 5
    assert f._series["a"][-1] == 0.4


def test_score_attaches_to_opportunity_dict():
    o = _opp(["a", "b"])
    o.fill_score = 0.73
    assert o.to_dict()["fill_score"] == 0.73
