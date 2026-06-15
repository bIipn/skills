<div align="center">

# ⚡ Polymarket Arbitrage Bot

**Risk-free arbitrage on Polymarket prediction markets — detection, optimization, execution, and a live dashboard.**

Real-time WebSocket data · three arbitrage strategies · Bregman/Frank-Wolfe optimization · Kelly sizing · slippage-aware & live execution · backtesting · always-on hosted dashboard.

</div>

---

The bot scans Polymarket's YES/NO outcome tokens and trades **only guaranteed
mispricings** — baskets that pay a certain **$1** for **less than $1**. It does
not predict outcomes or take directional risk; it locks in math.

> Based on *"Unravelling the Probabilistic Forest: Arbitrage in Prediction
> Markets"* ([arXiv:2508.03474](https://arxiv.org/abs/2508.03474)) and the
> Bregman/Frank-Wolfe projection method ([arXiv:1606.02825](https://arxiv.org/abs/1606.02825)).

## What it does

| | |
|---|---|
| 🎯 **Four strategies** | Single-condition (`YES+NO<$1`), rebalance (buy-all-outcomes), combinatorial (LP over the marginal polytope), and **cross-venue** (same event priced differently on Polymarket vs **Kalshi**) |
| 🌐 **Multi-venue** | Kalshi adapter (U.S.-regulated venue) + cross-venue detector — the least-contested edge for a small operator |
| 🧠 **AI dependency detection** | Classifies dependent market pairs into feasible joint outcomes (offline heuristics, or Claude when configured) |
| 📐 **3-layer optimizer** | Bregman projection via Frank-Wolfe; depth-aware, multi-level VWAP sizing validated against the live book |
| 💸 **Kelly sizing** | Fractional Kelly + book-depth caps |
| ⚡ **Real-time data** | Streaming CLOB WebSocket book cache, with REST fallback |
| 🧪 **Backtesting** | Deterministic replay → equity curve, win rate, max drawdown, per-strategy PnL |
| 📊 **Live dashboard** | Apple-HIG web UI: equity curve, opportunities, fill-rate report, per-strategy breakdown — runs locally or hosted on Vercel for anywhere access |
| 🔔 **Alerts** | Telegram push on fills, errors, and startup |
| 🖥️ **24/7 deploy** | One-command macOS (launchd) install + Docker |

## Safety first

Ships in **paper/simulation mode** by default — synthetic books, simulated
fills, no credentials, no real money. Live market data and live execution are
each behind separate explicit opt-in flags, and order placement uses a burner
wallet whose key never leaves your machine.

## Quick start

```bash
cd polymarket-arb
pip install -r requirements.txt
make backtest        # deterministic offline backtest
make paper           # real prices + simulated fills (no key needed)
make run             # dashboard at http://localhost:8000
```

## Documentation

Everything lives in **[`polymarket-arb/`](polymarket-arb/)**:

- **[README](polymarket-arb/README.md)** — architecture, strategies, full reference
- **[COWORKER_SETUP.md](polymarket-arb/COWORKER_SETUP.md)** — no-secrets, demo-first setup anyone can follow
- **[SETUP_LIVE.md](polymarket-arb/SETUP_LIVE.md)** — Mac mini 24/7, burner wallet, going live
- **[SETUP_CLOUD.md](polymarket-arb/SETUP_CLOUD.md)** — always-on hosted dashboard (Vercel)

## ⚠️ Disclaimer

Educational/research software, not financial advice. Prediction-market
arbitrage faces latency competition, partial fills, fees, oracle risk, and
regulatory restrictions (**Polymarket is not available to U.S. persons for
trading**). The "guaranteed" edge holds only if every leg fills at quote —
which it often doesn't. Trade real funds at your own risk and only where legal.
