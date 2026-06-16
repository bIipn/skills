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
| Real-time books | `backend/ws_feed.py` | `LiveBookCache` + `CLOBWebSocketClient` — streams the CLOB market channel and keeps live books warm; `LiveFeed` prefers a fresh WS book over a REST snapshot (`PM_USE_WS`, on by default in live mode) |
| Detection | `backend/arbitrage.py` | Three strategy families from the paper (below) |
| Dependency AI | `backend/dependencies.py` | Classifies logically dependent market pairs into feasible joint outcomes — offline `HeuristicClassifier`, or `ClaudeClassifier` (claude-opus-4-8) when `ANTHROPIC_API_KEY` is set |
| Optimization | `backend/optimizer.py` | Bregman projection onto the arbitrage-free manifold via **Frank-Wolfe** (conditional gradient) — grows an active set one vertex at a time instead of enumerating 2ⁿ outcomes |
| Sizing | `backend/kelly.py` | Depth caps (≤50% of book) + fractional Kelly for the risk-adjusted component |
| Execution | `backend/execution.py` | `PaperExecutor` models sequential CLOB fills *with* adverse slippage; gated `LiveExecutor` places real GTC orders via `py-clob-client` |
| Persistence | `backend/storage.py` | SQLite trade log; realized PnL + trade history survive restarts |
| Backtest | `backend/backtest.py` | Deterministic replay through the full pipeline → equity curve + stats (return, win rate, max drawdown, per-strategy) |
| Orchestration | `backend/engine.py` | The scan → detect → size → execute → persist → track loop + PnL state |
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

4. **Cross-venue** (`cross_venue.py`, enable with `PM_CROSS_VENUE=1`) — the
   *same* event priced differently on **Polymarket vs Kalshi**. Buy YES on the
   cheaper venue and NO on the other for `< $1`; one resolves to $1. This is the
   least-contested edge for a small operator (it needs accounts on both venues
   and event matching, which intra-venue HFT systems don't do) and the most
   realistic place to actually compete. `kalshi_client.py` adds the Kalshi feed;
   Kalshi is the U.S.-regulated (CFTC) venue, relevant where Polymarket isn't
   available. Confidence is < 1 (cross-venue resolution-source risk).

The maximum extractable profit of a mispricing equals the **Bregman
divergence** between the live price vector and its projection onto the
arbitrage-free set — exactly what `optimizer.py` computes.

### AI dependency classification

The combinatorial detector needs to know which joint outcomes are *feasible*
(the marginal-polytope constraints). `dependencies.py` provides this the way
the paper does — with a classifier that reads two market descriptions and
returns the set of logically possible `[A_yes, B_yes]` worlds:

- **`HeuristicClassifier`** (default, offline) — rule-based implication
  detection. Catches the canonical *"Republicans win PA by 5+ ⇒ Republicans
  win PA"* superset relationship with no credentials.
- **`ClaudeClassifier`** — set `ANTHROPIC_API_KEY` and it uses
  `claude-opus-4-8` (adaptive thinking + a strict JSON schema via
  `output_config.format`) to classify arbitrary pairs, mirroring the paper's
  81% accuracy. Results are cached per pair.

Feasible worlds expand into payoff vectors over all four tokens
(`A_YES, A_NO, B_YES, B_NO`), so the LP can build hedged YES/NO portfolios.

---

## Quick start

> Handing this to someone else to set up? Point them at
> **[`COWORKER_SETUP.md`](COWORKER_SETUP.md)** — a no-secrets, demo-first guide
> (`make install` → demo mode → done). Going live later is documented in
> **[`SETUP_LIVE.md`](SETUP_LIVE.md)**.

```bash
cd polymarket-arb
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) headless: run one scan and print opportunities
python run.py --scan

# 2) deterministic backtest (no network, no credentials)
python run.py --backtest --ticks 500
#   Bankroll:   $10,000.00 -> $25,360.53   (+153.61%)
#   Trades: 750  (win rate 88.4%)  max drawdown 0.24%

# 3) full dashboard + engine (with a "Run Backtest" button)
python run.py
# open http://localhost:8000
```

The dashboard's opportunity table shows each trade's **Bregman divergence**
(max extractable profit/unit) and **Frank-Wolfe iteration count** — the
3-layer optimizer's telemetry, live. Executed trades persist to
`arb_trades.db` (SQLite); restart and your PnL/history are restored.

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
  — enables `LiveExecutor`, which submits real GTC limit orders through
  [`py-clob-client`](https://github.com/Polymarket/py-clob-client)
  (`pip install py-clob-client`). With anything missing it refuses to place
  orders and returns a no-op result. This switch is intentionally hard to
  flip: nothing trades real funds by accident.

To paper-trade against **real live prices** (the recommended way to evaluate
the strategy), set `PM_DATA_MODE=live` and leave `PM_EXECUTION_MODE=paper`.

### Run it 24/7 (e.g. a Mac mini)

The bot is a standalone process — run it unattended, supervised by the OS.
**Don't run the trade loop inside Claude Code**; Claude Code is for building and
monitoring, not the runtime. On macOS, one command sets up a launchd service
that auto-starts on boot and auto-restarts on crash:

```bash
./deploy/install-macos.sh          # venv + deps + launchd agent
sudo pmset -a sleep 0 disablesleep 1   # keep the Mac awake
```

Dashboard is then reachable on your LAN at `http://<host>:8000`; PnL/history
persist in `arb_trades.db` across restarts. Full step-by-step (burner wallet,
CLOB credentials, paper-on-live dry run, go-live gate) is in
**[`SETUP_LIVE.md`](SETUP_LIVE.md)**.

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
                                   │ Executor (paper|live CLOB)│
                                   └─────────────┬─────────────┘
                                                 │ fills / PnL
                       ┌─────────────────────────▼──────────────┐
                       │ Engine ──► SQLite trade log (restart-   │
                       │   state     safe PnL + history)         │
                       │    │                                    │
                       │    └──► FastAPI WS ──► Dashboard         │
                       └─────────────────────────────────────────┘

         backtest.py replays the same pipeline offline → equity curve + stats
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
