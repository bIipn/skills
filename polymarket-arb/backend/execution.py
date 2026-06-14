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
    """Live executor via py-clob-client. Hard-gated on explicit opt-in.

    Places real GTC limit orders on the Polymarket CLOB for each leg of an
    opportunity, sequentially, recording the actual fill price reported by
    the exchange. Will not place any order unless `live_execution_enabled`
    (PM_EXECUTION_MODE=live + API key + wallet key).
    """

    def __init__(self):
        self._client = None

    def _clob(self):
        if self._client is not None:
            return self._client
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds

        creds = None
        if settings.api_key and settings.api_secret and settings.api_passphrase:
            creds = ApiCreds(
                api_key=settings.api_key,
                api_secret=settings.api_secret,
                api_passphrase=settings.api_passphrase,
            )
        self._client = ClobClient(
            settings.clob_rest_url,
            key=settings.wallet_pk,
            chain_id=137,  # Polygon
            creds=creds,
        )
        return self._client

    def execute(self, opp: Opportunity) -> TradeResult:
        if not settings.live_execution_enabled:
            return TradeResult(
                opportunity=opp, fills=[], realized_cost=0.0, realized_profit=0.0,
                success=False,
                note="LIVE execution not enabled (set PM_EXECUTION_MODE=live + credentials). "
                     "Refusing to place real orders.",
            )

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
        except Exception as exc:
            return TradeResult(
                opportunity=opp, fills=[], realized_cost=0.0, realized_profit=0.0,
                success=False, note=f"py-clob-client not installed: {exc}",
            )

        client = self._clob()
        fills: list[Fill] = []
        realized_cost = 0.0
        try:
            for leg in opp.legs:
                side = BUY if leg.side == "BUY" else SELL
                order = client.create_order(OrderArgs(
                    price=leg.price, size=leg.size, side=side, token_id=leg.token_id,
                ))
                resp = client.post_order(order, OrderType.GTC)
                # CLOB returns the matched/average price when available.
                filled = float(resp.get("price", leg.price)) if isinstance(resp, dict) \
                    else leg.price
                slip = filled - leg.price
                if leg.side == "BUY":
                    realized_cost += filled * leg.size
                else:
                    realized_cost -= filled * leg.size
                fills.append(Fill(
                    token_id=leg.token_id, label=leg.label, side=leg.side,
                    requested_price=leg.price, filled_price=round(filled, 4),
                    size=leg.size, slippage=round(slip, 4),
                ))
        except Exception as exc:
            return TradeResult(
                opportunity=opp, fills=fills, realized_cost=round(realized_cost, 4),
                realized_profit=0.0, success=False,
                note=f"live order error after {len(fills)} legs: {exc}",
            )

        realized_profit = opp.guaranteed_payoff - realized_cost
        return TradeResult(
            opportunity=opp, fills=fills, realized_cost=round(realized_cost, 4),
            realized_profit=round(realized_profit, 4),
            success=realized_profit >= 0, note="live order submitted",
        )


def make_executor():
    if settings.live_execution_enabled:
        return LiveExecutor()
    return PaperExecutor()
