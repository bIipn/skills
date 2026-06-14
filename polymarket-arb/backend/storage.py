"""SQLite persistence for executed trades.

Survives container/process restarts so realized PnL and the trade log are not
lost. Paper and live trades use the same schema. Set PM_DB_PATH to relocate or
`:memory:` to disable persistence (used by tests and backtests).
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from .models import TradeResult


class TradeStore:
    def __init__(self, path: str = "arb_trades.db"):
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                executed_at   REAL,
                kind          TEXT,
                market_id     TEXT,
                description   TEXT,
                realized_cost REAL,
                realized_pnl  REAL,
                success       INTEGER,
                note          TEXT,
                payload       TEXT
            )
            """
        )
        self._conn.commit()

    def record(self, res: TradeResult) -> None:
        d = res.to_dict()
        self._conn.execute(
            "INSERT INTO trades (executed_at, kind, market_id, description, "
            "realized_cost, realized_pnl, success, note, payload) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                d["executed_at"], d["kind"], d["market_id"], d["description"],
                d["realized_cost"], d["realized_profit"], int(d["success"]),
                d["note"], json.dumps(d),
            ),
        )
        self._conn.commit()

    def aggregates(self) -> dict:
        """Reconstruct running totals from the persisted trade log."""
        cur = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(realized_pnl),0), "
            "COALESCE(SUM(success),0) FROM trades"
        )
        total, pnl, won = cur.fetchone()

        by_strategy: dict = {}
        for kind, n, kpnl in self._conn.execute(
            "SELECT kind, COUNT(*), COALESCE(SUM(realized_pnl),0) "
            "FROM trades GROUP BY kind"
        ):
            by_strategy[kind] = {"pnl": float(kpnl), "trades": int(n)}

        return {
            "trades_total": int(total),
            "realized_pnl": float(pnl),
            "trades_won": int(won),
            "by_strategy": by_strategy,
        }

    def recent(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT payload FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def close(self) -> None:
        self._conn.close()


def make_store(path: Optional[str] = None) -> TradeStore:
    import os
    return TradeStore(path or os.getenv("PM_DB_PATH", "arb_trades.db"))
