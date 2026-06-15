"""Kalshi order execution (authenticated trade API).

Kalshi v2 authenticates each request with an API key id + an RSA private key:
every call signs `timestamp + METHOD + path` with RSA-PSS/SHA256 and sends the
signature in headers. Orders are limit orders priced in cents (1..99).

Hard-gated: places no real order unless `kalshi_live_execution_enabled`
(PM_EXECUTION_MODE=live + PM_KALSHI_API_KEY_ID + PM_KALSHI_PRIVATE_KEY). The
pure order-building/parsing logic is separated out and unit-tested; only
`place_leg` touches the network.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid

from .config import settings
from .models import Fill, Leg

_ORDERS_PATH = "/trade-api/v2/portfolio/orders"


def parse_ticker_side(token_id: str) -> tuple[str, str]:
    """Our Kalshi tokens are '<TICKER>-YES' / '<TICKER>-NO' (twins prefix 'k-').
    Returns (ticker, 'yes'|'no')."""
    tid = token_id[2:] if token_id.startswith("k-") else token_id
    base, _, suffix = tid.rpartition("-")
    side = "no" if suffix.upper() == "NO" else "yes"
    return (base or tid), side


def price_to_cents(price: float) -> int:
    """Dollar price (0..1) → Kalshi cents (1..99)."""
    return max(1, min(99, round(price * 100)))


def build_order(leg: Leg) -> dict:
    """Construct the Kalshi create-order body for a single BUY leg."""
    ticker, side = parse_ticker_side(leg.token_id)
    cents = price_to_cents(leg.price)
    body = {
        "ticker": ticker,
        "client_order_id": str(uuid.uuid4()),
        "type": "limit",
        "action": "buy" if leg.side == "BUY" else "sell",
        "side": side,
        "count": int(leg.size),
    }
    body["yes_price" if side == "yes" else "no_price"] = cents
    return body


class KalshiExecutor:
    def __init__(self):
        self._key = None

    # ---- auth ----------------------------------------------------------
    def _load_key(self):
        if self._key is not None:
            return self._key
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        raw = settings.kalshi_private_key
        if os.path.exists(raw):
            with open(raw, "rb") as f:
                pem = f.read()
        else:
            pem = raw.encode()
        self._key = load_pem_private_key(pem, password=None)
        return self._key

    def _sign(self, msg: str) -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        sig = self._load_key().sign(
            msg.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    def _headers(self, method: str, path: str) -> dict:
        ts = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": settings.kalshi_api_key_id,
            "KALSHI-ACCESS-SIGNATURE": self._sign(f"{ts}{method}{path}"),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

    # ---- execution -----------------------------------------------------
    def place_leg(self, leg: Leg) -> Fill:
        """Submit one Kalshi limit order; return the resulting Fill."""
        import urllib.request

        body = build_order(leg)
        # Base URL host without the /trade-api/v2 suffix for path signing.
        base = settings.kalshi_rest_url.split("/trade-api/")[0]
        req = urllib.request.Request(
            f"{base}{_ORDERS_PATH}", data=json.dumps(body).encode(),
            method="POST", headers=self._headers("POST", _ORDERS_PATH),
        )
        filled = leg.price
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
            order = data.get("order", data)
            # Kalshi reports the resting/avg price in cents when available.
            cents = order.get("yes_price") or order.get("no_price")
            if cents:
                filled = cents / 100.0
        return Fill(
            token_id=leg.token_id, label=leg.label, side=leg.side,
            requested_price=leg.price, filled_price=round(filled, 4),
            size=leg.size, slippage=round(filled - leg.price, 4),
        )


def make_kalshi_executor() -> KalshiExecutor:
    return KalshiExecutor()
