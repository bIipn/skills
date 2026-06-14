# Polymarket Arbitrage Bot + Dashboard

A working implementation of the prediction-market arbitrage stack described in
*"Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets"*
([arXiv:2508.03474](https://arxiv.org/abs/2508.03474)), with the Bregman /
Frank-Wolfe projection machinery from
[arXiv:1606.02825](https://arxiv.org/abs/1606.02825).

It detects **guaranteed** (risk-free) arbitrage across Polymarket markets,
sizes the optimal trade, and simulates execution — all visualised on a live
`CLAUDE × QUANT` dashboard.

> ⚠️ **Safety first.** Out of the box this runs in **PAPER mode**: synthetic
> local order books and *simulated* fills. No network calls, no credentials,
> **no real money**. Live data and live execution are each gated behind
> explicit, separate opt-in flags, and live order placement is left as a
> deliberate integration point you must wire up yourself. This is an
> educational / research tool — read the disclaimer at the bottom.

---

## What it implements

| Layer | Module | What it does |
|-------|--------|--------------|
| Data feed | `backend/polymarket_client.py` | Synthetic `PaperFeed` (default) or read-only `LiveFeed` against the Polymarket Gamma + CLOB REST APIs |
| Detection | `backend/arbitrage.py` | Three strategy families from the paper (below) |
| Optimization | `backend/optimizer.py` | Bregman projection onto the arbitrage-free manifold via **Frank-Wolfe** (conditional gradient) — grows an active set one vertex at a time instead of enumerating 2ⁿ outcomes |
| Sizing | `backend/kelly.py` | Depth caps (≤50% of book) + fractional Kelly for the risk-adjusted component |
| Execution | `backend/execution.py` | `PaperExecutor` models sequential CLOB fills *with* adverse slippage; guarded `LiveExecutor` stub |
| Orchestration | `backend/engine.py` | The scan → detect → size → execute → track loop + PnL state |
| API + UI | `backend/main.py`, `frontend/` | FastAPI REST/WebSocket server and a zero-dependency dashboard |

### The three arbitrage strategies

1. **Single-condition** — within one binary market, `ask(YES) + ask(NO) < $1`.
   Buy one of each; exactly one resolves to $1. Profit floor = `$1 − sum`.
2. **Rebalance** — a mutually-exclusive group (e.g. election with N candidates)
   where the sum of all best asks `< $1`. Buy one share of every outcome; the
   winner pays $1.
3. **Combinatorial** — logically *dependent* markets (e.g. "Republicans win PA
   by 5+" implies "Trump wins PA"). Solved as a linear program over the
   **marginal polytope**: find a non-negative buy vector with guaranteed
   non-negative payoff in *every feasible joint outcome*, never brute-forcing
   the 2ⁿ space.

The maximum extractable profit of a mispricing equals the **Bregman
divergence** between the live price vector and its projection onto the
arbitrage-free set — exactly what `optimizer.py` computes.

---

## Quick start

```bash
cd polymarket-arb
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) headless: run one scan and print opportunities
python run.py --scan

# 2) full dashboard + engine
python run.py
# open http://localhost:8000
```

Run the tests:

```bash
pytest -q
```

---

## Going live (read carefully)

Two independent switches in `.env` (copy from `.env.example`):

- `PM_DATA_MODE=live` — pulls **real** Polymarket markets and order books
  (read-only, safe).
- `PM_EXECUTION_MODE=live` **plus** `PM_API_KEY` and `PM_WALLET_PRIVATE_KEY`
  — enables the live executor. Even then, actual order submission raises
  `NotImplementedError` until *you* wire up
  [`py-clob-client`](https://github.com/Polymarket/py-clob-client) in
  `backend/execution.py`. This is intentional: nothing places a real order by
  accident.

To paper-trade against **real live prices** (the recommended way to evaluate
the strategy), set `PM_DATA_MODE=live` and leave `PM_EXECUTION_MODE=paper`.

---

## Architecture

```
            ┌──────────────┐   markets    ┌──────────────┐
 Polymarket │  MarketFeed  │ ───────────► │  Detectors   │ single / rebalance
  / Paper   │ (paper|live) │              │ arbitrage.py │ / combinatorial(LP)
            └──────────────┘              └──────┬───────┘
                                                 │ opportunities
                                   ┌─────────────▼─────────────┐
                                   │ Sizing (Kelly + depth cap)│
                                   │ Optimizer (Bregman/FW)    │
                                   └─────────────┬─────────────┘
                                                 │ sized legs
                                   ┌─────────────▼─────────────┐
                                   │ Executor (paper|live)     │
                                   └─────────────┬─────────────┘
                                                 │ fills / PnL
                       ┌─────────────────────────▼──────────────┐
                       │ Engine state → FastAPI WS → Dashboard   │
                       └─────────────────────────────────────────┘
```

---

## ⚠️ Disclaimer

This is **educational and research software**. It is not financial advice and
comes with no warranty. Prediction-market arbitrage in production faces
latency competition, block-time races, partial fills, fees, oracle/resolution
risk, and regulatory restrictions (Polymarket is not available to U.S. persons
for trading). The "guaranteed profit" of a detected arbitrage holds only if all
legs fill at quoted prices — which, as the simulated executor demonstrates,
often they do not. Trade real funds at your own risk and only where legal.
