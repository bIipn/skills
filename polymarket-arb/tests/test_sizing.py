"""Tests for depth-aware, multi-level (VWAP) sizing."""
import pytest

from backend.arbitrage import _basket_cap, _walk_basket, detect_single_condition
from backend.config import settings
from backend.models import BookSide, Market, OrderLevel, Outcome


def _side(levels):
    return BookSide([OrderLevel(p, s) for p, s in levels])


def test_walk_takes_multiple_levels_until_unprofitable():
    yes = _side([(0.40, 100), (0.44, 100), (0.52, 100)])
    no = _side([(0.45, 100), (0.46, 100), (0.40, 100)])
    units, cost, worst = _walk_basket([yes, no], cap_units=1000)
    # level0: 0.85 → 100 units; level1: 0.90 → 100 units; level2: 0.92 → 100 units
    assert units == 300
    assert round(cost, 2) == round(85 + 90 + 92, 2)
    assert worst == [0.52, 0.40]


def test_walk_stops_when_unit_cost_reaches_one():
    yes = _side([(0.40, 100), (0.60, 100)])
    no = _side([(0.45, 100), (0.45, 100)])
    units, cost, _ = _walk_basket([yes, no], cap_units=1000)
    # level0 0.85 ok (100); level1 0.60+0.45=1.05 → stop
    assert units == 100
    assert round(cost, 2) == 85.0


def test_walk_respects_depth_cap():
    yes = _side([(0.4, 100), (0.4, 100)])
    no = _side([(0.45, 100), (0.45, 100)])
    units, _, _ = _walk_basket([yes, no], cap_units=120)
    assert units == 120  # capped before exhausting the book


def test_basket_cap_uses_thinnest_total_depth():
    yes = _side([(0.4, 100), (0.4, 100)])   # total depth 200
    no = _side([(0.45, 50)])                # total depth 50 (thinner)
    cap = _basket_cap([yes, no])
    assert cap == 50 * settings.max_book_depth_fraction


def test_single_condition_captures_depth_beyond_best_level():
    # With the full book available, depth-aware sizing should beat best-level.
    yes = Outcome("Y", "YES",
                  asks=_side([(0.40, 100), (0.44, 100)]),
                  bids=_side([(0.38, 100)]))
    no = Outcome("N", "NO",
                 asks=_side([(0.45, 100), (0.46, 100)]),
                 bids=_side([(0.43, 100)]))
    m = Market("c", "Q?", [yes, no], mutually_exclusive=False)

    old = settings.max_book_depth_fraction
    settings.max_book_depth_fraction = 1.0
    try:
        opp = detect_single_condition(m)
    finally:
        settings.max_book_depth_fraction = old

    assert opp is not None
    total_size = opp.legs[0].size
    assert total_size == 200          # both levels taken, not just the top 100
    # profit = 200 - (100*0.85 + 100*0.90) = 25
    assert round(opp.profit, 2) == 25.0
    # leg limit prices are the worst (deepest) accepted level
    assert opp.legs[0].price == 0.44
    assert opp.legs[1].price == 0.46
