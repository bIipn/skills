"""Configuration loaded from environment variables.

Nothing here is required to run the bot in the default PAPER (simulation)
mode. Real CLOB connectivity and live execution are gated behind explicit
opt-in flags so the bot never touches real funds by accident.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    # ---- Data source ---------------------------------------------------
    # "paper"   -> synthetic order books generated locally (default, safe)
    # "live"    -> read real order books from the Polymarket CLOB API
    data_mode: str = field(default_factory=lambda: os.getenv("PM_DATA_MODE", "paper"))

    clob_rest_url: str = field(
        default_factory=lambda: os.getenv("PM_CLOB_REST_URL", "https://clob.polymarket.com")
    )
    gamma_rest_url: str = field(
        default_factory=lambda: os.getenv("PM_GAMMA_URL", "https://gamma-api.polymarket.com")
    )
    clob_ws_url: str = field(
        default_factory=lambda: os.getenv(
            "PM_CLOB_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        )
    )

    # ---- Execution -----------------------------------------------------
    # Execution is ALWAYS paper unless this is explicitly set to "live"
    # AND credentials are present. Live mode is intentionally hard to reach.
    execution_mode: str = field(
        default_factory=lambda: os.getenv("PM_EXECUTION_MODE", "paper")
    )
    api_key: str = field(default_factory=lambda: os.getenv("PM_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("PM_API_SECRET", ""))
    api_passphrase: str = field(default_factory=lambda: os.getenv("PM_API_PASSPHRASE", ""))
    wallet_pk: str = field(default_factory=lambda: os.getenv("PM_WALLET_PRIVATE_KEY", ""))

    # ---- Strategy params ----------------------------------------------
    starting_bankroll: float = field(
        default_factory=lambda: _get_float("PM_BANKROLL", 10_000.0)
    )
    # Minimum guaranteed profit (in USDC) to bother executing a trade.
    min_profit_threshold: float = field(
        default_factory=lambda: _get_float("PM_MIN_PROFIT", 0.05)
    )
    # Never take more than this fraction of available book depth on one leg.
    max_book_depth_fraction: float = field(
        default_factory=lambda: _get_float("PM_MAX_DEPTH_FRAC", 0.50)
    )
    # Kelly fraction multiplier (fractional Kelly for safety).
    kelly_fraction: float = field(
        default_factory=lambda: _get_float("PM_KELLY_FRACTION", 0.50)
    )
    # Polymarket taker fee (currently 0 on most markets; configurable).
    taker_fee_bps: float = field(default_factory=lambda: _get_float("PM_FEE_BPS", 0.0))
    # Demo only: probability a leg fails to fill, exercising the unwind safety
    # net (0 = off, default). Lets you see partial-fill handling in paper mode.
    simulate_partial: float = field(
        default_factory=lambda: _get_float("PM_SIMULATE_PARTIAL", 0.0))

    # Scan loop interval in seconds (paper mode tick rate).
    scan_interval_s: float = field(
        default_factory=lambda: _get_float("PM_SCAN_INTERVAL", 2.0)
    )
    # ---- Telegram alerts (optional) -----------------------------------
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("PM_TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("PM_TELEGRAM_CHAT_ID", ""))
    # Only push a fill alert when guaranteed profit >= this (avoids spam).
    telegram_min_notify: float = field(
        default_factory=lambda: _get_float("PM_TELEGRAM_MIN_NOTIFY", 1.0))

    # ---- Cloud sync (optional, for the hosted Vercel dashboard) --------
    # The bot POSTs its public snapshot to the Vercel /api/ingest endpoint,
    # authenticated with a shared secret. No wallet key is ever sent.
    cloud_ingest_url: str = field(
        default_factory=lambda: os.getenv("PM_CLOUD_INGEST_URL", ""))
    cloud_ingest_token: str = field(
        default_factory=lambda: os.getenv("PM_CLOUD_INGEST_TOKEN", ""))
    cloud_sync_interval: float = field(
        default_factory=lambda: _get_float("PM_CLOUD_SYNC_INTERVAL", 5.0))

    # ---- Cross-venue (Kalshi) -----------------------------------------
    # Enable multi-venue mode: also pull Kalshi and detect cross-venue arbs.
    cross_venue: bool = field(default_factory=lambda: _get_bool("PM_CROSS_VENUE", False))
    kalshi_rest_url: str = field(default_factory=lambda: os.getenv(
        "PM_KALSHI_URL", "https://api.elections.kalshi.com/trade-api/v2"))
    # Kalshi trading credentials (API key id + RSA private key, PEM or path).
    kalshi_api_key_id: str = field(
        default_factory=lambda: os.getenv("PM_KALSHI_API_KEY_ID", ""))
    kalshi_private_key: str = field(
        default_factory=lambda: os.getenv("PM_KALSHI_PRIVATE_KEY", ""))

    # Use the real-time CLOB WebSocket book cache in live mode (else REST poll).
    use_ws: bool = field(default_factory=lambda: _get_bool("PM_USE_WS", True))
    # Max age (s) a cached WS book may be before falling back to REST.
    ws_max_age_s: float = field(default_factory=lambda: _get_float("PM_WS_MAX_AGE", 5.0))

    @property
    def live_execution_enabled(self) -> bool:
        return (
            self.execution_mode == "live"
            and bool(self.api_key)
            and bool(self.wallet_pk)
        )

    @property
    def kalshi_live_execution_enabled(self) -> bool:
        return (
            self.execution_mode == "live"
            and bool(self.kalshi_api_key_id)
            and bool(self.kalshi_private_key)
        )

    def banner(self) -> str:
        exec_state = "LIVE 🔴" if self.live_execution_enabled else "PAPER (simulated) 🟢"
        return (
            f"data_mode={self.data_mode}  execution={exec_state}  "
            f"bankroll=${self.starting_bankroll:,.0f}  "
            f"min_profit=${self.min_profit_threshold:.2f}"
        )


settings = Settings()
