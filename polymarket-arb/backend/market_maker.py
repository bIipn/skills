"""Market-making mode — earn Kalshi liquidity rewards + capture the spread.

This is a *different game* from arbitrage and a better fit for a smaller
operator on a regulated venue: instead of racing faster bots for fleeting
mispricings, you post resting two-sided quotes near the mid. You earn the
platform's maker/liquidity rewards for providing depth, plus the bid-ask
spread when your quotes get hit — both without needing to win a latency race.
The risk is **inventory**: when one side fills more, you accumulate a position
exposed to the mid moving against you, so quoting is capped by an inventory
limit.

Paper mode simulates reward accrual, spread capture, and inventory drift so you
can see the edge in the demo. Live quoting (placing/cancelling resting orders
on Kalshi) is a deliberate, separate step — see `live_quotes()` — because
unattended resting-order management needs careful cancel/replace logic.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .config import settings
from .models import Market


@dataclass
class Quote:
    market_id: str
    token_id: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float


@dataclass
class MMState:
    quotes_posted: int = 0
    fills: int = 0
    rewards: float = 0.0
    spread_pnl: float = 0.0
    inventory_pnl: float = 0.0
    net_pnl: float = 0.0
    inventory: dict = field(default_factory=dict)  # market_id -> net shares


class MarketMaker:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.state = MMState()

    def _quote_for(self, m: Market) -> Quote | None:
        """Two-sided quote around the mid, capped by the inventory limit."""
        if len(m.outcomes) != 2:
            return None
        yes = m.outcomes[0]
        bb, ba = yes.best_bid, yes.best_ask
        if bb is None or ba is None:
            return None
        mid = (bb + ba) / 2.0
        half = settings.mm_spread
        inv = self.state.inventory.get(m.condition_id, 0.0)
        bid_size = settings.mm_size if inv < settings.mm_max_inventory else 0.0
        ask_size = settings.mm_size if inv > -settings.mm_max_inventory else 0.0
        if bid_size <= 0 and ask_size <= 0:
            return None  # inventory full both ways (shouldn't happen) → skip
        return Quote(
            market_id=m.condition_id, token_id=yes.token_id,
            bid=max(mid - half, 0.01), ask=min(mid + half, 0.99),
            bid_size=bid_size, ask_size=ask_size,
        )

    def step(self, markets: list[Market]) -> dict:
        """Simulate one quoting tick across the (Kalshi) markets we make."""
        rewards = spread = inv_pnl = 0.0
        quoted = fills = 0
        for m in markets:
            if settings.venue == "kalshi" and m.venue != "kalshi":
                continue
            q = self._quote_for(m)
            if q is None:
                continue
            quoted += 1
            mid = (q.bid + q.ask) / 2.0
            inv = self.state.inventory.get(m.condition_id, 0.0)
            # Maker reward for resting size near the mid (both sides).
            rewards += settings.mm_reward_rate * (q.bid_size + q.ask_size)
            # Our bid gets hit → we buy below mid (capture mid-bid), inventory up.
            if q.bid_size and self.rng.random() < settings.mm_fill_prob:
                spread += (mid - q.bid) * q.bid_size
                inv += q.bid_size
                fills += 1
            # Our ask gets hit → we sell above mid (capture ask-mid), inventory down.
            if q.ask_size and self.rng.random() < settings.mm_fill_prob:
                spread += (q.ask - mid) * q.ask_size
                inv -= q.ask_size
                fills += 1
            # Inventory risk: hold the position through a small mid move.
            inv_pnl += inv * self.rng.uniform(-0.01, 0.01)
            self.state.inventory[m.condition_id] = inv

        net = rewards + spread + inv_pnl
        self.state.quotes_posted += quoted
        self.state.fills += fills
        self.state.rewards += rewards
        self.state.spread_pnl += spread
        self.state.inventory_pnl += inv_pnl
        self.state.net_pnl += net
        return {
            "tick_pnl": net, "rewards": rewards, "spread": spread,
            "inventory_pnl": inv_pnl, "quoted": quoted, "fills": fills,
        }

    def snapshot(self) -> dict:
        s = self.state
        open_inv = sum(abs(v) for v in s.inventory.values())
        return {
            "net_pnl": round(s.net_pnl, 2),
            "rewards": round(s.rewards, 2),
            "spread_pnl": round(s.spread_pnl, 2),
            "inventory_pnl": round(s.inventory_pnl, 2),
            "quotes_posted": s.quotes_posted,
            "fills": s.fills,
            "open_inventory": round(open_inv, 1),
            "markets_quoted": len(s.inventory),
        }

    def live_quotes(self, markets: list[Market]) -> list[Quote]:
        """Quotes to place live. Returns the quote set; actual resting-order
        placement/cancellation on Kalshi is a separate, deliberate step (it
        needs cancel/replace management) and is not run unattended here."""
        return [q for q in (self._quote_for(m) for m in markets) if q is not None]


def make_market_maker() -> MarketMaker:
    return MarketMaker()
