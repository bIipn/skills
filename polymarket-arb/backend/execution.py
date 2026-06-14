"""Trade execution.

PaperExecutor simulates sequential CLOB fills including the adverse price
movement the research highlights: legs fill one at a time, and after each
fill the remaining liquidity may have moved, so a "guaranteed" plan can
still slip. This models the real failure mode of CLOB arbitrage.

LiveExecutor is intentionally a thin, guarded stub: it refuses to place
real orders unless live execution is explicitly enabled with credentials,
and even then routes through py-clob-client which the operator must wire
up. The default path never sends a real order.
"""
from __future__ import annotations

import random

from .config import settings
from .models import Fill, Opportunity, TradeResult


class PaperExecutor:
    """Simulated sequential CLOB execution with realistic slippage."""

    def __init__(self, slip_prob: float = 0.13, seed: int | None = None):
        # ~13% per-leg chance the book moves before our leg lands, mirroring
        # the paper's 87% single-condition success rate.
        self.slip_prob = slip_prob
        self.rng = random.Random(seed)

    def execute(self, opp: Opportunity) -> TradeResult:
        fills: list[Fill] = []
        realized_cost = 0.0
        slipped = False

        for leg in opp.legs:
            price = leg.price
            if self.rng.random() < self.slip_prob:
                # Adverse move: pay a few cents more than planned.
                bump = self.rng.uniform(0.01, 0.06)
                price = min(leg.price + bump, 0.999)
                slipped = True
            slippage = price - leg.price
            if leg.side == "BUY":
                realized_cost += price * leg.size
            else:
                realized_cost -= price * leg.size
            fills.append(Fill(
                token_id=leg.token_id, label=leg.label, side=leg.side,
                requested_price=leg.price, filled_price=round(price, 4),
                size=leg.size, slippage=round(slippage, 4),
            ))

        realized_profit = opp.guaranteed_payoff - realized_cost
        success = realized_profit >= 0
        note = "filled clean" if not slipped else (
            "filled with slippage — still profitable" if success
            else "slippage ate the edge (loss)"
        )
        return TradeResult(
            opportunity=opp, fills=fills,
            realized_cost=round(realized_cost, 4),
            realized_profit=round(realized_profit, 4),
            success=success, note=note,
        )


class LiveExecutor:
    """Guarded live executor. Refuses unless explicitly enabled."""

    def __init__(self):
        self._client = None

    def execute(self, opp: Opportunity) -> TradeResult:
        if not settings.live_execution_enabled:
            return TradeResult(
                opportunity=opp, fills=[], realized_cost=0.0, realized_profit=0.0,
                success=False,
                note="LIVE execution not enabled (set PM_EXECUTION_MODE=live + credentials). "
                     "Refusing to place real orders.",
            )
        # Real order placement would go here via py-clob-client. Left as an
        # explicit integration point so no real funds move without the
        # operator deliberately wiring this up and accepting the risk.
        raise NotImplementedError(
            "Wire up py-clob-client ClobClient.post_order() here before going live."
        )


def make_executor():
    if settings.live_execution_enabled:
        return LiveExecutor()
    return PaperExecutor()
