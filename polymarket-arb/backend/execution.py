"""Trade execution.

PaperExecutor simulates sequential CLOB fills including the adverse price
movement the research highlights: legs fill one at a time, and after each
fill the remaining liquidity may have moved, so a "guaranteed" plan can
still slip. With PM_SIMULATE_PARTIAL > 0 it also simulates a leg failing to
fill so you can watch the unwind safety net work.

LiveExecutor / KalshiExecutor place real orders only when live execution is
explicitly enabled with credentials. RoutedExecutor routes each leg of a
cross-venue arb to its venue. All live paths share one safety net: if any leg
fails after others have filled, the filled legs are immediately unwound
(sold back) to flatten exposure rather than leaving a naked directional
position. The default path never sends a real order.
"""
from __future__ import annotations

import random

from .config import settings
from .models import Fill, Leg, Opportunity, TradeResult


def _flatten_leg(leg: Leg, fill: Fill) -> Leg:
    """Opposing order that unwinds a filled leg back to flat."""
    return Leg(
        token_id=fill.token_id, label=f"unwind {leg.label}",
        side="SELL" if leg.side == "BUY" else "BUY",
        price=fill.filled_price, size=fill.size, venue=leg.venue,
    )


def _cost_delta(side: str, price: float, size: float) -> float:
    return price * size if side == "BUY" else -price * size


class PaperExecutor:
    """Simulated sequential CLOB execution with realistic slippage and an
    optional partial-fill simulation that exercises the unwind safety net."""

    def __init__(self, slip_prob: float = 0.13, seed: int | None = None):
        # ~13% per-leg chance the book moves before our leg lands, mirroring
        # the paper's 87% single-condition success rate.
        self.slip_prob = slip_prob
        self.rng = random.Random(seed)

    # How contested each strategy is by faster traders (1.0 = most contested).
    _CONTEST = {
        "single_condition": 1.0,   # obvious, liquid — pro bots race for these
        "rebalance": 0.7,
        "combinatorial": 0.35,     # computation, not microseconds — less contested
        "cross_venue": 0.35,
    }

    def execute(self, opp: Opportunity) -> TradeResult:
        # Competition: a faster trader may snipe the arb before our order lands.
        contest = settings.competition * self._CONTEST.get(opp.kind, 0.6)
        if self.rng.random() < min(0.97, contest):
            return TradeResult(
                opportunity=opp, fills=[], realized_cost=0.0, realized_profit=0.0,
                success=False,
                note="missed — a faster trader filled this before our order landed",
            )

        # Optionally simulate a counterpart leg failing to fill.
        if len(opp.legs) >= 2 and self.rng.random() < settings.simulate_partial:
            return self._simulate_partial(opp)

        fills: list[Fill] = []
        realized_cost = 0.0
        slipped = False
        for leg in opp.legs:
            price = leg.price
            if self.rng.random() < self.slip_prob:
                price = min(leg.price + self.rng.uniform(0.01, 0.06), 0.999)
                slipped = True
            realized_cost += _cost_delta(leg.side, price, leg.size)
            fills.append(Fill(
                token_id=leg.token_id, label=leg.label, side=leg.side,
                requested_price=leg.price, filled_price=round(price, 4),
                size=leg.size, slippage=round(price - leg.price, 4),
            ))

        realized_profit = opp.guaranteed_payoff - realized_cost
        success = realized_profit >= 0
        note = "filled clean" if not slipped else (
            "filled with slippage — still profitable" if success
            else "slippage ate the edge (loss)"
        )
        return TradeResult(
            opportunity=opp, fills=fills, realized_cost=round(realized_cost, 4),
            realized_profit=round(realized_profit, 4), success=success, note=note,
        )

    def _simulate_partial(self, opp: Opportunity) -> TradeResult:
        """One leg fails; unwind the legs that did fill, at a small loss."""
        fail_idx = self.rng.randrange(len(opp.legs))
        fills: list[Fill] = []
        cost = 0.0
        for leg in opp.legs[:fail_idx]:
            fills.append(Fill(leg.token_id, leg.label, leg.side, leg.price,
                              leg.price, leg.size, 0.0))
            cost += _cost_delta(leg.side, leg.price, leg.size)
        # Unwind each filled leg at ~1-4% worse (the cost of flattening fast).
        unwound = 0
        for leg in opp.legs[:fail_idx]:
            back = leg.price * (1 - self.rng.uniform(0.01, 0.04))
            cost += _cost_delta("SELL" if leg.side == "BUY" else "BUY", back, leg.size)
            fills.append(Fill(leg.token_id, f"unwind {leg.label}",
                              "SELL" if leg.side == "BUY" else "BUY",
                              back, round(back, 4), leg.size, round(back - leg.price, 4)))
            unwound += 1
        return TradeResult(
            opportunity=opp, fills=fills, realized_cost=round(cost, 4),
            realized_profit=round(-cost, 4), success=False,
            note=f"PARTIAL FILL — leg {fail_idx} missed; unwound {unwound} filled "
                 f"leg(s), flat at a small loss",
        )


class LiveExecutor:
    """Live Polymarket execution via py-clob-client. Hard-gated."""

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
            settings.clob_rest_url, key=settings.wallet_pk, chain_id=137, creds=creds,
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
            import py_clob_client  # noqa: F401
        except Exception as exc:
            return TradeResult(
                opportunity=opp, fills=[], realized_cost=0.0, realized_profit=0.0,
                success=False, note=f"py-clob-client not installed: {exc}",
            )

        placed: list[tuple[Leg, Fill]] = []
        realized_cost = 0.0
        try:
            for leg in opp.legs:
                f = self.place_leg(leg)
                placed.append((leg, f))
                realized_cost += _cost_delta(leg.side, f.filled_price, f.size)
        except Exception as exc:
            # Partial fill — flatten what filled rather than hold naked risk.
            return _unwind_and_report(
                opp, placed, realized_cost, str(exc),
                lambda leg: self.place_leg(leg))

        realized_profit = opp.guaranteed_payoff - realized_cost
        return TradeResult(
            opportunity=opp, fills=[f for _, f in placed],
            realized_cost=round(realized_cost, 4),
            realized_profit=round(realized_profit, 4),
            success=realized_profit >= 0, note="live order submitted",
        )

    def place_leg(self, leg) -> Fill:
        """Place one Polymarket CLOB order; return the resulting Fill."""
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        client = self._clob()
        side = BUY if leg.side == "BUY" else SELL
        order = client.create_order(OrderArgs(
            price=leg.price, size=leg.size, side=side, token_id=leg.token_id,
        ))
        resp = client.post_order(order, OrderType.GTC)
        filled = float(resp.get("price", leg.price)) if isinstance(resp, dict) else leg.price
        return Fill(
            token_id=leg.token_id, label=leg.label, side=leg.side,
            requested_price=leg.price, filled_price=round(filled, 4),
            size=leg.size, slippage=round(filled - leg.price, 4),
        )


def _unwind_and_report(opp, placed, realized_cost, err, place_fn) -> TradeResult:
    """Shared safety net: sell back every filled leg, report a flat (small
    loss) result, and surface any unwind that itself failed (naked risk)."""
    fills = [f for _, f in placed]
    fatal: list[str] = []
    unwound = 0
    for leg, fill in placed:
        try:
            flat = place_fn(_flatten_leg(leg, fill))
            realized_cost += _cost_delta(flat.side, flat.filled_price, flat.size)
            fills.append(flat)
            unwound += 1
        except Exception as exc:
            fatal.append(f"UNWIND FAILED ({leg.venue} {fill.token_id}): {exc}")
    note = (f"PARTIAL FILL ({err}) — unwound {unwound}/{len(placed)} leg(s)")
    if fatal:
        note += " — ⚠️ NAKED POSITION: " + "; ".join(fatal)
    return TradeResult(
        opportunity=opp, fills=fills, realized_cost=round(realized_cost, 4),
        realized_profit=round(-realized_cost, 4), success=False, note=note,
    )


class RoutedExecutor:
    """Routes each leg of a (cross-venue) opportunity to its venue's live
    executor, with the same partial-fill unwind safety net."""

    def __init__(self):
        self.poly = LiveExecutor()
        from .kalshi_execution import make_kalshi_executor
        self.kalshi = make_kalshi_executor()

    def _place(self, leg: Leg) -> Fill:
        if leg.venue == "kalshi":
            if not settings.kalshi_live_execution_enabled:
                raise RuntimeError("Kalshi live execution not enabled")
            return self.kalshi.place_leg(leg)
        if not settings.live_execution_enabled:
            raise RuntimeError("Polymarket live execution not enabled")
        return self.poly.place_leg(leg)

    def execute(self, opp: Opportunity) -> TradeResult:
        placed: list[tuple[Leg, Fill]] = []
        realized_cost = 0.0
        first_err = None
        for leg in opp.legs:
            try:
                f = self._place(leg)
                placed.append((leg, f))
                realized_cost += _cost_delta(leg.side, f.filled_price, f.size)
            except Exception as exc:
                first_err = f"{leg.venue} leg: {exc}"
                break  # stop on first failure; unwind what filled

        if first_err is None:
            realized_profit = opp.guaranteed_payoff - realized_cost
            return TradeResult(
                opportunity=opp, fills=[f for _, f in placed],
                realized_cost=round(realized_cost, 4),
                realized_profit=round(realized_profit, 4),
                success=realized_profit >= 0, note="routed live orders",
            )
        # Partial (or zero) fill — flatten everything that did fill.
        return _unwind_and_report(opp, placed, realized_cost, first_err, self._place)


def make_executor():
    # Route per leg when multi-venue OR Kalshi-only live; Polymarket-only live →
    # LiveExecutor; otherwise the simulated paper executor.
    live_any = settings.live_execution_enabled or settings.kalshi_live_execution_enabled
    if live_any and (settings.cross_venue or settings.venue == "kalshi"):
        return RoutedExecutor()
    if settings.live_execution_enabled:
        return LiveExecutor()
    return PaperExecutor()
