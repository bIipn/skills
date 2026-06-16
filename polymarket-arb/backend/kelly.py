"""Position sizing: depth caps + (fractional) Kelly criterion.

For a *guaranteed* arbitrage the only sizing constraints are book depth
and available capital — there is no downside variance, so you take as
much as the thinner leg allows up to the depth cap. The Kelly machinery
below is used for the risk-adjusted component (e.g. AI-flagged combinatorial
trades whose dependency classification is < 100% certain).
"""
from __future__ import annotations

from .config import settings


def depth_capped_size(available_depth: float) -> float:
    """Largest size we'll take given a leg's available depth.

    Capped at `max_book_depth_fraction` so we don't walk the book and
    move the price against ourselves (paper references a 50% cap).
    """
    if available_depth <= 0:
        return 0.0
    return available_depth * settings.max_book_depth_fraction


def kelly_fraction(win_prob: float, net_odds: float) -> float:
    """Classic Kelly: f* = (b*p - q) / b.

    win_prob : probability the trade pays off (1.0 for proven arb).
    net_odds : net fractional odds b (profit per unit staked on a win).
    Returns a fraction of bankroll in [0, 1]; <=0 means don't bet.
    """
    if net_odds <= 0:
        return 0.0
    p = max(0.0, min(1.0, win_prob))
    q = 1.0 - p
    f = (net_odds * p - q) / net_odds
    return max(0.0, min(1.0, f))


def risk_adjusted_size(
    bankroll: float,
    win_prob: float,
    edge_pct: float,
    depth_limited_size: float,
    price: float,
) -> float:
    """Blend Kelly (capital risk) with the book-depth cap.

    Returns a share count. For proven arbitrage (win_prob == 1) Kelly is
    bypassed and only the depth/capital limits bind.
    """
    if price <= 0:
        return 0.0

    capital_cap_shares = bankroll / price  # can't spend more than we have

    if win_prob >= 1.0 - 1e-9:
        return max(0.0, min(depth_limited_size, capital_cap_shares))

    f = kelly_fraction(win_prob, edge_pct) * settings.kelly_fraction
    kelly_dollars = bankroll * f
    kelly_shares = kelly_dollars / price
    return max(0.0, min(depth_limited_size, kelly_shares, capital_cap_shares))
