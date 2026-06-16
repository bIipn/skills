"""Cross-venue arbitrage: the same event priced differently on two venues.

If the *same* binary event trades on both Polymarket and Kalshi, you can buy
YES on the venue where it's cheaper and NO on the other. Exactly one resolves
to $1, so if `ask(YES on A) + ask(NO on B) < $1` the difference is locked in —
regardless of outcome, and without competing on intra-venue latency.

This is the least-contested edge for a small operator: it needs accounts on
both venues and event matching, which most intra-venue HFT systems don't do.

Confidence is < 1: the guarantee assumes both venues resolve the same event the
same way (resolution-source risk), which is real and why this needs review
before live execution.
"""
from __future__ import annotations

import re
from typing import Optional

from .arbitrage import _basket_cap, _fee, _walk_basket
from .config import settings
from .models import Leg, Market, Opportunity

_STOP = {
    "will", "the", "a", "an", "be", "in", "on", "of", "to", "by", "for", "at",
    "and", "or", "this", "that", "with", "?", "win", "above", "below", "than",
}


def _event_key(question: str) -> frozenset:
    words = re.findall(r"[a-z0-9$]+", question.lower())
    return frozenset(w for w in words if w not in _STOP and len(w) > 2)


def same_event(a: Market, b: Market) -> bool:
    """Jaccard-similarity match on question keywords (≥ 0.6)."""
    ka, kb = _event_key(a.question), _event_key(b.question)
    if not ka or not kb:
        return False
    inter = len(ka & kb)
    union = len(ka | kb)
    return union > 0 and inter / union >= 0.6


def detect_cross_venue(a: Market, b: Market) -> Optional[Opportunity]:
    """Best of: buy YES@a + NO@b, or YES@b + NO@a, when the sum < $1."""
    if len(a.outcomes) != 2 or len(b.outcomes) != 2:
        return None
    best: Optional[Opportunity] = None
    for m_yes, m_no in ((a, b), (b, a)):
        yes, no = m_yes.outcomes[0], m_no.outcomes[1]
        if yes.best_ask is None or no.best_ask is None:
            continue
        if yes.best_ask + no.best_ask >= 1.0 - 1e-9:
            continue
        sides = [yes.asks, no.asks]
        size, cost, worst = _walk_basket(sides, _basket_cap(sides))
        if size <= 0:
            continue
        fees = _fee(cost)
        profit = size - cost - fees
        if profit < settings.min_profit_threshold:
            continue
        if best is not None and profit <= best.profit:
            continue
        legs = [
            Leg(yes.token_id, f"{m_yes.venue}:YES", "BUY", worst[0], size, m_yes.venue),
            Leg(no.token_id, f"{m_no.venue}:NO", "BUY", worst[1], size, m_no.venue),
        ]
        best = Opportunity(
            kind="cross_venue",
            market_id=f"{m_yes.condition_id}|{m_no.condition_id}"[:64],
            description=(
                f"{m_yes.question[:42]} — BUY YES@{m_yes.venue} + NO@{m_no.venue} "
                f"for ${(yes.best_ask + no.best_ask):.3f} < $1.00"
            ),
            legs=legs,
            cost=cost + fees,
            guaranteed_payoff=size,
            profit=profit,
            edge_pct=profit / (cost + fees) if cost else 0.0,
            confidence=0.90,  # cross-venue resolution-source risk
        )
    return best


def scan_cross_venue(markets: list[Market], max_pairs: int = 200) -> list[Opportunity]:
    """Match binary events across *different* venues and detect arbitrage."""
    binaries = [m for m in markets
                if len(m.outcomes) == 2 and not m.mutually_exclusive]
    found: list[Opportunity] = []
    checked = 0
    for i in range(len(binaries)):
        for j in range(i + 1, len(binaries)):
            if checked >= max_pairs:
                return found
            a, b = binaries[i], binaries[j]
            if a.venue == b.venue:
                continue
            checked += 1
            if not same_event(a, b):
                continue
            opp = detect_cross_venue(a, b)
            if opp:
                found.append(opp)
    return found
