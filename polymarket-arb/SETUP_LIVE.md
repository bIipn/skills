# Going Live — setup & Mac mini 24/7 deployment

This walks you from a fresh checkout to a bot running unattended on a Mac mini.
**Read the two prerequisites first — they are not optional.**

> 🔒 **Your private key never leaves your machine.** The bot reads it from a
> local `.env` file at runtime. Do not paste it into chat, commit it, or send
> it to anyone. Use a **dedicated burner wallet** funded with only what you're
> willing to lose.

> ⚠️ **Legality:** Polymarket is **not available to U.S. persons for trading**.
> Confirm you're permitted in your jurisdiction before funding anything.

> ⚠️ **Risk:** "Guaranteed" arbitrage only holds if every leg fills at quote.
> In live CLOB conditions it often doesn't — real money can be lost. Start tiny.

---

## 0. The mental model

- **The bot** is a plain Python process that runs itself 24/7 — no LLM in the
  trade path.
- **Claude Code** is your console for *building/fixing/monitoring* it, not the
  runtime. Never run the trading loop inside Claude Code (slow, costly, risky).

---

## 1. Get a burner wallet + funds

1. In Phantom (or any wallet), create a **new EVM account** — *not* your main one.
   Polymarket is on **Polygon** (an EVM chain), so you need the **EVM** key, not
   the Solana one.
2. Fund it with a **small** amount of **USDC on Polygon** (bridge if needed).
3. Export that EVM account's **private key** (Phantom → account → Export Private
   Key). You'll paste it into `.env` **on the Mac mini only**.

## 2. Get Polymarket CLOB API credentials

`py-clob-client` derives API creds from your wallet key. After filling
`PM_WALLET_PRIVATE_KEY` in `.env`, generate creds once:

```bash
python - <<'PY'
from py_clob_client.client import ClobClient
import os
c = ClobClient("https://clob.polymarket.com", key=os.environ["PM_WALLET_PRIVATE_KEY"], chain_id=137)
print(c.create_or_derive_api_creds())   # copy api_key / api_secret / api_passphrase into .env
PY
```

## 3. Configure `.env`

Copy the template and edit:

```bash
cp .env.example .env
```

```ini
# --- start in the SAFE dry-run posture ---
PM_DATA_MODE=live           # real Polymarket prices (read-only)
PM_EXECUTION_MODE=paper     # SIMULATED fills — no real orders yet
PM_BANKROLL=500             # simulated bankroll for paper PnL

# credentials (Mac mini only; never commit)
PM_WALLET_PRIVATE_KEY=0x...
PM_API_KEY=...
PM_API_SECRET=...
PM_API_PASSPHRASE=...

# conservative thresholds
PM_MIN_PROFIT=0.50          # only act on fat spreads
PM_MAX_DEPTH_FRAC=0.50
```

## 4. Dry run on live prices (do this for days, costs nothing)

```bash
pip install -r requirements.txt py-clob-client websockets
python run.py            # dashboard at http://localhost:8000
```

You're now seeing **real** opportunities with **simulated** execution. Watch the
dashboard: are the opportunities real? Would they have filled? Only proceed if
the answer is yes.

## 5. Go live (small)

Flip one switch in `.env` and restart:

```ini
PM_EXECUTION_MODE=live
```

Keep `PM_MIN_PROFIT` high and `PM_BANKROLL` small. Watch closely.

---

## 6. Run it 24/7 on the Mac mini (launchd)

One command installs a background service that auto-starts on boot and
auto-restarts on crash:

```bash
./deploy/install-macos.sh
```

This will:
- create a `.venv` and install dependencies,
- create `.env` from the template if missing (edit it before going live),
- install and load a **launchd** agent (`com.polymarket-arb`).

Then keep the Mac awake even with the lid/display off:

```bash
sudo pmset -a sleep 0 disablesleep 1
# also: System Settings → Energy → "Start up automatically after a power failure"
```

**Manage the service:**

```bash
# view logs
tail -f logs/arb.out.log logs/arb.err.log

# stop / start
launchctl unload ~/Library/LaunchAgents/com.polymarket-arb.plist
launchctl load   ~/Library/LaunchAgents/com.polymarket-arb.plist

# after pulling new code, just reload
./deploy/install-macos.sh
```

The dashboard is reachable from any device on your LAN at
`http://<mac-mini-ip>:8000`. Realized PnL and trade history persist in
`arb_trades.db`, so restarts don't lose state.

---

## Go-live checklist

- [ ] Legally permitted to trade Polymarket where I live
- [ ] **Burner** wallet, funded with only what I can lose (USDC on Polygon)
- [ ] `.env` filled on the Mac mini; never committed or shared
- [ ] Ran **`PM_EXECUTION_MODE=paper` on live data** for days — opportunities look real
- [ ] `PM_MIN_PROFIT` set high, bankroll small
- [ ] launchd service loaded; Mac set not to sleep
- [ ] I understand fills can slip and money can be lost
