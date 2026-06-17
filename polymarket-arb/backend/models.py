"""Core domain models shared across the engine."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderLevel:
    """A single price level in the order book."""

    price: float  # 0..1 USDC per share
    size: float   # shares available


@dataclass
class BookSide:
    """One side of a book, sorted best-first."""

    levels: list[OrderLevel] = field(default_factory=list)

    @property
    def best(self) -> Optional[float]:
        return self.levels[0].price if self.levels else None

    def depth_value(self, price_limit: float) -> float:
        """Total shares available at or better than price_limit."""
        return sum(l.size for l in self.levels if l.price <= price_limit)


@dataclass
class Outcome:
    """A single tradeable outcome token (e.g. the YES token of a market)."""

    token_id: str
    label: str            # "YES" / "NO" / candidate name
    asks: BookSide = field(default_factory=BookSide)  # what we pay to BUY
    bids: BookSide = field(default_factory=BookSide)  # what we receive to SELL

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks.best

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids.best


@dataclass
class Market:
    """A Polymarket market / condition with one or more outcomes.

    For binary markets `outcomes` has two entries (YES, NO). For a
    mutually-exclusive multi-outcome group (e.g. an election with N
    candidates) all candidate YES tokens live here and `mutually_exclusive`
    is True, meaning exactly one resolves to $1.
    """

    condition_id: str
    question: str
    outcomes: list[Outcome] = field(default_factory=list)
    mutually_exclusive: bool = True  # exactly one outcome pays $1
    category: str = ""
    venue: str = "polymarket"        # "polymarket" | "kalshi" | ...
    updated_at: float = field(default_factory=time.time)


@dataclass
class Leg:
    """One leg of an arbitrage trade."""

    token_id: str
    label: str
    side: str           # "BUY" or "SELL"
    price: float        # limit price
    size: float         # shares
    venue: str = "polymarket"


@dataclass
class Opportunity:
    """A detected arbitrage opportunity with a sized, guaranteed-profit plan."""

    kind: str                 # "single_condition" | "rebalance" | "combinatorial"
    market_id: str
    description: str
    legs: list[Leg]
    cost: float               # total USDC outlay
    guaranteed_payoff: float  # minimum payoff across all outcomes
    profit: float             # guaranteed_payoff - cost (after fees)
    edge_pct: float           # profit / cost
    confidence: float = 1.0   # 1.0 for proven arb, <1 for AI-detected deps
    detected_at: float = field(default_factory=time.time)
    # 3-layer optimizer telemetry (filled by the Bregman/Frank-Wolfe layer).
    bregman: float = 0.0      # Bregman divergence == max per-unit extractable profit
    fw_iters: int = 0         # Frank-Wolfe iterations to converge
    # Execution-risk score in [0,1]: predicted chance the spread stays open long
    # enough to fill both legs (TimesFM or heuristic). 1.0 = no forecast/neutral.
    fill_score: float = 1.0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "market_id": self.market_id,
            "description": self.description,
            "legs": [leg.__dict__ for leg in self.legs],
            "cost": round(self.cost, 4),
            "guaranteed_payoff": round(self.guaranteed_payoff, 4),
            "profit": round(self.profit, 4),
            "edge_pct": round(self.edge_pct * 100, 2),
            "confidence": round(self.confidence, 3),
            "bregman": round(self.bregman, 4),
            "fw_iters": self.fw_iters,
            "fill_score": round(self.fill_score, 3),
            "detected_at": self.detected_at,
        }


@dataclass
class Fill:
    """Result of executing one leg."""

    token_id: str
    label: str
    side: str
    requested_price: float
    filled_price: float
    size: float
    slippage: float


@dataclass
class TradeResult:
    """Outcome of executing an opportunity."""

    opportunity: Opportunity
    fills: list[Fill]
    realized_cost: float
    realized_profit: float
    success: bool
    note: str = ""
    executed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "kind": self.opportunity.kind,
            "market_id": self.opportunity.market_id,
            "description": self.opportunity.description,
            "fills": [f.__dict__ for f in self.fills],
            "realized_cost": round(self.realized_cost, 4),
            "realized_profit": round(self.realized_profit, 4),
            "success": self.success,
            "note": self.note,
            "executed_at": self.executed_at,
        }
