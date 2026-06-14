"""Arbitrage detection engine.

Implements the three strategy families described in the research
("Unravelling the Probabilistic Forest", arXiv:2508.03474):

  1. single_condition  -- YES + NO mispriced within one binary market.
  2. rebalance         -- buy every outcome of a mutually-exclusive group
                          for less than $1 (the "buy all YES" strategy).
  3. combinatorial     -- logically dependent markets where a portfolio
                          has guaranteed non-negative payoff in every
                          feasible joint outcome. Solved as a linear
                          program over the marginal polytope rather than
                          brute-forcing 2^n outcomes.

Every opportunity returned carries a *proven* lower bound on payoff, so
`profit` is a guaranteed floor, not an expectation.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .config import settings
from .kelly import depth_capped_size
from .models import Leg, Market, Opportunity
from .optimizer import frank_wolfe_projection


def _fee(notional: float) -> float:
    return notional * settings.taker_fee_bps / 10_000.0


def _enrich(opp: Opportunity, prices: np.ndarray, vertices: np.ndarray) -> Opportunity:
    """Attach Bregman/Frank-Wolfe telemetry to a detected opportunity.

    Projects the live price vector onto the arbitrage-free hull; the Bregman
    divergence is the max per-unit extractable profit, and the iteration count
    shows the conditional-gradient cost.
    """
    try:
        res = frank_wolfe_projection(prices, vertices)
        opp.bregman = res.divergence
        opp.fw_iters = res.iterations
    except Exception:
        pass
    return opp


def detect_single_condition(market: Market) -> Optional[Opportunity]:
    """Binary market where best_ask(YES) + best_ask(NO) < $1.

    Buying one YES and one NO share guarantees exactly $1 at resolution
    (one side wins). If the combined cost is < $1 the difference is locked
    in profit.
    """
    if len(market.outcomes) != 2:
        return None
    yes, no = market.outcomes
    if yes.best_ask is None or no.best_ask is None:
        return None

    combined = yes.best_ask + no.best_ask
    if combined >= 1.0 - 1e-9:
        return None  # no edge on the buy side

    # Size limited by the thinner side's depth at the best price.
    yes_depth = yes.asks.depth_value(yes.best_ask)
    no_depth = no.asks.depth_value(no.best_ask)
    size = depth_capped_size(min(yes_depth, no_depth))
    if size <= 0:
        return None

    cost = (yes.best_ask + no.best_ask) * size
    fees = _fee(cost)
    payoff = 1.0 * size  # one of the two pays $1/share
    profit = payoff - cost - fees
    if profit < settings.min_profit_threshold:
        return None

    legs = [
        Leg(yes.token_id, yes.label, "BUY", yes.best_ask, size),
        Leg(no.token_id, no.label, "BUY", no.best_ask, size),
    ]
    opp = Opportunity(
        kind="single_condition",
        market_id=market.condition_id,
        description=f"{market.question[:60]} — YES+NO = ${combined:.3f} < $1.00",
        legs=legs,
        cost=cost + fees,
        guaranteed_payoff=payoff,
        profit=profit,
        edge_pct=profit / (cost + fees) if cost else 0.0,
        confidence=1.0,
    )
    return _enrich(opp, np.array([yes.best_ask, no.best_ask]), np.eye(2))


def detect_rebalance(market: Market) -> Optional[Opportunity]:
    """Mutually-exclusive group where sum of all best asks < $1.

    Exactly one outcome resolves to $1. Buying one share of every outcome
    costs sum(asks); the winning share returns $1. Profit = $1 - sum.
    """
    if not market.mutually_exclusive or len(market.outcomes) < 2:
        return None
    asks = [o.best_ask for o in market.outcomes]
    if any(a is None for a in asks):
        return None

    total = float(sum(asks))
    if total >= 1.0 - 1e-9:
        return None

    # Cap size by the thinnest leg.
    depths = [o.asks.depth_value(o.best_ask) for o in market.outcomes]
    size = depth_capped_size(min(depths))
    if size <= 0:
        return None

    cost = total * size
    fees = _fee(cost)
    payoff = 1.0 * size
    profit = payoff - cost - fees
    if profit < settings.min_profit_threshold:
        return None

    legs = [
        Leg(o.token_id, o.label, "BUY", o.best_ask, size) for o in market.outcomes
    ]
    opp = Opportunity(
        kind="rebalance",
        market_id=market.condition_id,
        description=(
            f"{market.question[:50]} — buy all {len(market.outcomes)} outcomes "
            f"for ${total:.3f} < $1.00"
        ),
        legs=legs,
        cost=cost + fees,
        guaranteed_payoff=payoff,
        profit=profit,
        edge_pct=profit / (cost + fees) if cost else 0.0,
        confidence=1.0,
    )
    n = len(market.outcomes)
    return _enrich(opp, np.array(asks), np.eye(n))


def detect_combinatorial(
    markets: list[Market],
    feasible_outcomes: np.ndarray,
    labels: list[tuple[str, str]],
) -> Optional[Opportunity]:
    """Cross-market arbitrage under logical dependencies via an LP.

    This is the "marginal polytope" formulation. Instead of enumerating
    2^n joint outcomes we are handed the set of *feasible* joint outcomes
    (rows of `feasible_outcomes`, each a 0/1 vector over the n tradeable
    YES tokens) and find a non-negative buy vector x (shares per token)
    that maximises the guaranteed profit:

        maximise   t - cost
        s.t.       payoff_in_outcome_k >= t   for every feasible outcome k
                   payoff_in_outcome_k = sum_i feasible[k,i] * x_i
                   0 <= x_i <= depth_i

    cost = sum_i ask_i * x_i. A positive optimum is guaranteed profit no
    matter which feasible outcome occurs.

    `labels[i]` = (token_id, human_label) for column i.
    """
    try:
        from scipy.optimize import linprog
    except Exception:  # pragma: no cover - scipy always in requirements
        return None

    n = feasible_outcomes.shape[1]
    if n == 0 or feasible_outcomes.shape[0] == 0:
        return None

    # Map token_id -> (ask, depth) from the supplied markets.
    ask = np.zeros(n)
    depth = np.zeros(n)
    token_index = {tid: i for i, (tid, _) in enumerate(labels)}
    for m in markets:
        for o in m.outcomes:
            if o.token_id in token_index and o.best_ask is not None:
                i = token_index[o.token_id]
                ask[i] = o.best_ask
                depth[i] = depth_capped_size(o.asks.depth_value(o.best_ask))

    if np.any(ask <= 0) or np.any(depth <= 0):
        return None

    # Decision vars: [x_0..x_{n-1}, t]. Maximise t - cost => minimise cost - t.
    c = np.concatenate([ask, [-1.0]])  # minimise sum(ask*x) - t

    # Guaranteed-payoff constraints: for each feasible outcome k,
    #   t - sum_i feasible[k,i] x_i <= 0
    A_ub = np.hstack([-feasible_outcomes, np.ones((feasible_outcomes.shape[0], 1))])
    b_ub = np.zeros(feasible_outcomes.shape[0])

    bounds = [(0.0, float(depth[i])) for i in range(n)] + [(0.0, None)]

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
        return None

    x = res.x[:n]
    t = res.x[n]
    cost = float(ask @ x)
    fees = _fee(cost)
    profit = float(t - cost - fees)
    if profit < settings.min_profit_threshold:
        return None

    legs: list[Leg] = []
    for i in range(n):
        if x[i] > 1e-6:
            tid, lab = labels[i]
            legs.append(Leg(tid, lab, "BUY", float(ask[i]), float(round(x[i], 4))))
    if not legs:
        return None

    opp = Opportunity(
        kind="combinatorial",
        market_id="+".join(m.condition_id for m in markets)[:64],
        description=(
            f"Combinatorial arb across {len(markets)} dependent markets — "
            f"guaranteed floor ${t:.2f} for cost ${cost:.2f}"
        ),
        legs=legs,
        cost=cost + fees,
        guaranteed_payoff=float(t),
        profit=profit,
        edge_pct=profit / (cost + fees) if cost else 0.0,
        confidence=0.81,  # combinatorial deps are AI-classified; see paper (81.45%)
    )
    return _enrich(opp, ask.copy(), feasible_outcomes.astype(float))


def scan_markets(markets: list[Market]) -> list[Opportunity]:
    """Run the fast per-market detectors across a snapshot of markets."""
    found: list[Opportunity] = []
    for m in markets:
        if len(m.outcomes) == 2 and not _looks_exhaustive(m):
            opp = detect_single_condition(m)
        else:
            opp = detect_rebalance(m)
        if opp:
            found.append(opp)
    found.sort(key=lambda o: o.profit, reverse=True)
    return found


def _looks_exhaustive(market: Market) -> bool:
    """Binary YES/NO markets are handled as single_condition; treat any
    market explicitly flagged mutually-exclusive with >2 outcomes as a
    rebalance group."""
    return market.mutually_exclusive and len(market.outcomes) > 2
