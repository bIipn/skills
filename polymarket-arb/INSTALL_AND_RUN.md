# Install & run the demo (Mac)

Two ways to do this. **Option A needs no Claude Code at all** — it's the fastest
way to see the demo. Option B installs Claude Code so you can just talk to it.

Either way, the demo uses **real market prices with fake money** — no wallet, no
keys, no risk — and it now factors in the faster pro traders who beat you to
fills, so the numbers you see are realistic, not rosy.

---

## Option A — just the Terminal (simplest, no Claude Code)

1. **Open Terminal** (Cmd-Space, type "Terminal", Enter).

2. **Install the basics** (Python + git). Paste this — it installs Homebrew if
   you don't have it, then Python:
   ```bash
   command -v brew >/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   brew install python git
   ```

3. **Get the bot and install it:**
   ```bash
   git clone https://github.com/bIipn/skills.git
   cd skills/polymarket-arb
   pip3 install -r requirements.txt
   ```

4. **Start the demo:**
   ```bash
   make paper
   ```

5. **Open the dashboard:** go to **http://localhost:8000** in your browser.

That's it. Leave it running and watch the **Fill-Rate Report** — that's your
real go/no-go signal.

To stop it: press `Ctrl-C` in the Terminal.

---

## Option B — install Claude Code (so you can just ask it)

Claude Code is a coding assistant in your Terminal. You can log in with the
**same Claude account** as your Claude app (Pro/Max subscription works).

1. **Open Terminal** and install Claude Code (native installer, no Node needed):
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   ```
   *(Alternative if you have Node.js: `npm install -g @anthropic-ai/claude-code`.)*

2. **Get the bot:**
   ```bash
   git clone https://github.com/bIipn/skills.git
   cd skills/polymarket-arb
   ```

3. **Start Claude Code and log in:**
   ```bash
   claude
   ```
   The first time, it asks you to log in — choose **"Log in with Claude"** /
   subscription and sign in with your Claude account in the browser window that
   opens.

4. **Ask it to set everything up.** Paste this:
   > "Set up the Polymarket arb bot in DEMO mode and start it. Then open the dashboard."

   Claude Code installs dependencies, starts the demo, and gives you the
   dashboard link. From then on you can just talk to it (see the cheat sheet in
   `../START_HERE.md`).

---

## Running it 24/7 (optional, for a Mac mini)

Once the demo looks good and you want it always on:
```bash
make install                       # installs a background service (auto-restart)
sudo pmset -a sleep 0 disablesleep 1   # keep the Mac awake
```

## When you're ready to go live (later) — Kalshi only

You said Kalshi is the only venue you can legally use. Run the bot Kalshi-only:
```bash
# Kalshi demo on real Kalshi prices, still fake money:
PM_VENUE=kalshi PM_DATA_MODE=live PM_EXECUTION_MODE=paper make run
```
**Market-making (your most realistic Kalshi edge).** Instead of racing for
arbs, quote both sides of markets to earn Kalshi's liquidity rewards + the
spread — no latency race required:
```bash
make market-make      # Kalshi market-making demo (rewards + spread, fake money)
```
Watch the **Market-Making** panel on the dashboard (net P/L = rewards + spread −
inventory). For a regulated venue this is usually a steadier edge than arbitrage.

Going live with real money on Kalshi is documented in
[`SETUP_LIVE.md`](SETUP_LIVE.md) (§5b) — burner funds, your Kalshi API key, and
the safety checks. **Honest heads-up:** Kalshi is a regulated, fairly efficient
venue, so intra-Kalshi arbs are rarer and smaller than the demo's — expect
occasional small edges, not the backtest numbers. Cross-venue arb is **not**
legal for you (it needs Polymarket too), so it stays off in your live setup.
