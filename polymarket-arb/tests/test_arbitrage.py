"""Tests for the detection engine and Bregman/Frank-Wolfe optimizer."""
import numpy as np

from backend.arbitrage import (
    detect_combinatorial,
    detect_rebalance,
    detect_single_condition,
)
from backend.kelly import depth_capped_size, kelly_fraction, risk_adjusted_size
from backend.models import BookSide, Market, OrderLevel, Outcome
from backend.optimizer import bregman_divergence, frank_wolfe_projection


def _outcome(tid, label, ask, depth=1000.0):
    return Outcome(
        token_id=tid, label=label,
        asks=BookSide([OrderLevel(ask, depth)]),
        bids=BookSide([OrderLevel(max(ask - 0.02, 0.001), depth)]),
    )


def test_single_condition_arb_detected():
    m = Market("c1", "Will X happen?",
               [_outcome("y", "YES", 0.45), _outcome("n", "NO", 0.45)],
               mutually_exclusive=False)
    opp = detect_single_condition(m)
    assert opp is not None
    assert opp.kind == "single_condition"
    # YES+NO = 0.90 -> $0.10/share guaranteed before fees
    assert opp.profit > 0
    assert opp.guaranteed_payoff > opp.cost
    assert opp.confidence == 1.0


def test_single_condition_no_arb_when_sum_geq_one():
    m = Market("c2", "Will Y happen?",
               [_outcome("y", "YES", 0.55), _outcome("n", "NO", 0.50)],
               mutually_exclusive=False)
    assert detect_single_condition(m) is None


def test_rebalance_arb_detected():
    outs = [_outcome(f"o{i}", f"C{i}", a) for i, a in enumerate([0.30, 0.30, 0.30])]
    m = Market("g1", "Who wins?", outs, mutually_exclusive=True)
    opp = detect_rebalance(m)
    assert opp is not None
    assert opp.kind == "rebalance"
    # sum 0.90 < 1.0 -> profit
    assert opp.profit > 0
    assert len(opp.legs) == 3


def test_rebalance_no_arb_when_sum_geq_one():
    outs = [_outcome(f"o{i}", f"C{i}", a) for i, a in enumerate([0.40, 0.35, 0.30])]
    m = Market("g2", "Who wins?", outs, mutually_exclusive=True)
    assert detect_rebalance(m) is None


def test_combinatorial_dependency_arb():
    # Two dependent YES tokens: token1 (broad) implies token0 (narrow) false?
    # Feasible joint outcomes as payoff rows over [tok0, tok1].
    # Outcomes: (1,0), (0,1) -> mutually exclusive & exhaustive.
    feasible = np.array([[1.0, 0.0], [0.0, 1.0]])
    labels = [("tok0", "A"), ("tok1", "B")]
    m = Market("m", "dep", [_outcome("tok0", "A", 0.4), _outcome("tok1", "B", 0.4)])
    opp = detect_combinatorial([m], feasible, labels)
    assert opp is not None
    assert opp.profit > 0  # buy both for 0.8, exactly one pays 1.0


def test_combinatorial_no_arb():
    feasible = np.array([[1.0, 0.0], [0.0, 1.0]])
    labels = [("tok0", "A"), ("tok1", "B")]
    m = Market("m", "dep", [_outcome("tok0", "A", 0.55), _outcome("tok1", "B", 0.55)])
    assert detect_combinatorial([m], feasible, labels) is None


def test_depth_cap():
    # default fraction 0.5
    assert depth_capped_size(1000) == 500
    assert depth_capped_size(0) == 0


def test_kelly_fraction_bounds():
    assert kelly_fraction(1.0, 0.5) > 0
    assert kelly_fraction(0.4, 0.5) == 0.0  # negative edge -> no bet
    assert 0 <= kelly_fraction(0.7, 1.0) <= 1


def test_risk_adjusted_size_proven_arb_ignores_kelly():
    # win_prob 1.0 -> bounded only by depth/capital
    size = risk_adjusted_size(bankroll=1000, win_prob=1.0, edge_pct=0.1,
                              depth_limited_size=200, price=0.5)
    assert size == 200  # depth binds before capital (1000/0.5=2000)


def test_frank_wolfe_projects_onto_hull():
    # Hull = simplex vertices; a mispriced point sums to < 1 (arb).
    vertices = np.eye(3)
    market = np.array([0.3, 0.3, 0.3])  # sums to 0.9 -> outside hull
    res = frank_wolfe_projection(market, vertices, max_iter=200)
    assert res.divergence > 0
    assert res.iterations >= 1


def test_bregman_zero_at_same_point():
    p = np.array([0.5, 0.5])
    assert abs(bregman_divergence(p, p)) < 1e-9
