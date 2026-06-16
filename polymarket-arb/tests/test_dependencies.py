"""Tests for the heuristic dependency classifier and combinatorial wiring."""
from backend.dependencies import (
    HeuristicClassifier,
    combinatorial_opportunity,
    scan_combinatorial,
)
from backend.models import BookSide, Market, OrderLevel, Outcome


def _outcome(tid, label, ask, depth=1000.0):
    return Outcome(
        token_id=tid, label=label,
        asks=BookSide([OrderLevel(ask, depth)]),
        bids=BookSide([OrderLevel(max(ask - 0.02, 0.001), depth)]),
    )


def _binary(cid, q, yes_ask, no_ask):
    return Market(cid, q, [_outcome(f"{cid}-Y", "YES", yes_ask),
                           _outcome(f"{cid}-N", "NO", no_ask)],
                  mutually_exclusive=False)


def test_heuristic_detects_implication():
    c = HeuristicClassifier()
    a = _binary("A", "Will Republicans win Pennsylvania?", 0.55, 0.47)
    b = _binary("B", "Will Republicans win Pennsylvania by 5+ points?", 0.30, 0.72)
    res = c.classify(a, b)
    assert res is not None
    assert res.relationship == "B implies A"
    # (A=0, B=1) is impossible — B can't be true while A is false.
    assert (0, 1) not in res.feasible_worlds
    assert (1, 1) in res.feasible_worlds


def test_heuristic_independent_returns_none():
    c = HeuristicClassifier()
    a = _binary("A", "Will Bitcoin close above 100k?", 0.5, 0.5)
    b = _binary("B", "Will the Lakers win the title?", 0.5, 0.5)
    assert c.classify(a, b) is None


def test_combinatorial_arb_from_dependency():
    c = HeuristicClassifier()
    # Inconsistent pricing: A_YES cheap (0.40), B_NO cheap (0.45).
    a = _binary("A", "Will Republicans win Pennsylvania?", 0.40, 0.62)
    b = _binary("B", "Will Republicans win Pennsylvania by 5+ points?", 0.55, 0.45)
    res = c.classify(a, b)
    opp = combinatorial_opportunity(a, b, res)
    assert opp is not None
    assert opp.kind == "combinatorial"
    # Buy A_YES + B_NO for 0.85, guaranteed $1 floor → ~$0.15/share edge.
    assert opp.profit > 0
    assert opp.confidence <= 0.81


def test_combinatorial_no_arb_when_consistent():
    c = HeuristicClassifier()
    a = _binary("A", "Will Republicans win Pennsylvania?", 0.56, 0.46)
    b = _binary("B", "Will Republicans win Pennsylvania by 5+ points?", 0.30, 0.72)
    res = c.classify(a, b)
    assert combinatorial_opportunity(a, b, res) is None


def test_scan_combinatorial_finds_pair():
    c = HeuristicClassifier()
    markets = [
        _binary("A", "Will Republicans win Pennsylvania?", 0.40, 0.62),
        _binary("B", "Will Republicans win Pennsylvania by 5+ points?", 0.55, 0.45),
        _binary("C", "Will it rain tomorrow?", 0.5, 0.5),
    ]
    found = scan_combinatorial(markets, c)
    assert len(found) == 1
    assert found[0].kind == "combinatorial"
