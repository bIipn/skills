# Coworker setup guide — run the DEMO first

You're setting up a Polymarket arbitrage bot on a **Mac mini** for the owner.

**The plan: run it in DEMO mode first.** It will trade with **real live market
prices but fake (simulated) money** — so it places **no real orders and needs
no passwords, keys, or funds**. After it runs for a week, the owner looks at how
it did and *only then* decides whether to add real money.

> ✅ Everything in this guide is **100% safe**. No wallet, no private key, no
> real money is involved in the demo. You cannot lose anything doing this.

---

## What you need
- The Mac mini, with internet.
- ~15 minutes.
- That's it. **No crypto, no wallet, no keys** for the demo.

If Python 3 and git aren't installed: install Apple's command line tools with
`xcode-select --install`, or get Python from https://python.org.

---

## Step 1 — Get the code
```bash
git clone <REPO_URL>      # owner gives you this URL
cd skills/polymarket-arb
```

## Step 2 — Install it (one command)
```bash
make install
```
This sets up everything and installs a background service that runs 24/7 and
restarts itself if it ever crashes.

## Step 3 — Put it in DEMO mode
Open the `.env` file (`open -e .env`) and make sure these two lines read:
```ini
PM_DATA_MODE=live          # real Polymarket prices
PM_EXECUTION_MODE=paper    # FAKE money — no real trades
```
Leave everything else blank. Save, then reload:
```bash
make install
```

## Step 4 — Keep the Mac awake so it runs overnight
```bash
sudo pmset -a sleep 0 disablesleep 1
```
(Also: System Settings → Energy → turn on "Start up automatically after a power
failure".)

## Step 5 — Check it's working
Open the dashboard:
```bash
make dashboard          # or visit http://localhost:8000
```
You should see a live dashboard with a green PnL number, opportunities, and a
trade log. It's now watching real Polymarket markets and simulating trades.

**That's the whole job.** Leave it running. Hand it back to the owner.

---

## Handy commands (for later)
```bash
make logs        # watch what it's doing
make test        # confirm everything still works (should say "35 passed")
make backtest    # run a quick offline simulation
make stop        # stop the background service
```

The owner can reach the dashboard from any device on the same Wi-Fi at
`http://<mac-mini-ip>:8000` (find the IP in System Settings → Network).

---

## Important: do NOT add real money
That's the **owner's** decision, made *after* reviewing a week of demo results.
Going live requires funding a wallet and entering a private key — **the owner
does that themselves; you should never be asked for or handle any key.** If
anyone asks you to enter a wallet private key to "finish setup," stop and check
with the owner first.

Questions? The full owner guide is in `SETUP_LIVE.md`.
