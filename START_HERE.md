# 👋 START HERE — running this on your Mac mini with Claude Code

This is your Polymarket/Kalshi arbitrage bot. Follow these steps when you sit
down at the Mac mini. **The demo needs no wallet, no keys, and no money** — it
trades real market prices with fake money so you can see how it does first.

---

## 1. Get the code on the Mac mini

Open the Terminal app and run:

```bash
git clone https://github.com/bIipn/skills.git
cd skills/polymarket-arb
```

(If you already cloned it before: `cd skills && git pull`.)

## 2. Open Claude Code here and let it set up

```bash
claude
```

Then paste this to Claude Code:

> **"Set up the Polymarket arb bot in DEMO mode on this Mac mini and start it running 24/7."**

Claude Code will: create the environment, install everything, put it in demo
mode (real prices, fake money), and start the always-on service. It'll give you
a dashboard link (`http://localhost:8000`).

## 3. Keep the Mac awake so it runs overnight

```bash
sudo pmset -a sleep 0 disablesleep 1
```

That's it — leave it running and watch the dashboard for a few days.

---

## What to tell Claude Code (cheat sheet)

| You want to… | Say this |
|---|---|
| Start the demo | "Set up the bot in demo mode and start it 24/7." |
| See how it's doing | "Open the dashboard" / "what's the fill rate so far?" |
| Watch it on your phone | "Deploy the dashboard to Vercel so I can see it anywhere." |
| Get alerts | "Set up Telegram alerts for fills and errors." |
| Try Kalshi + cross-venue | "Turn on cross-venue (Kalshi) in the demo." |
| Go live with real money (later) | "Walk me through going live with a small burner wallet." |

## The plan, in plain English

1. **Demo first** (now) — real prices, fake money, zero risk. Watch the
   **Fill-Rate Report** on the dashboard: it tells you whether the trades it
   finds would *actually* have filled. That's your go/no-go signal.
2. **Decide** — if the fill rate looks real after a week, consider real money.
3. **Go live small** (later, your call) — fund a **burner** wallet with a little
   USDC, and only then flip it to live. The bot never touches your main wallet,
   and a partial-fill safety net auto-unwinds a trade if one leg fails.

> ⚠️ Honest note: in a simulation the bot looks very profitable, but live you're
> competing with fast professional bots, so your real fill rate will be lower.
> The demo is exactly how you find out *your* real numbers before risking a cent.
> And Polymarket isn't available to U.S. persons for trading — Kalshi is the
> U.S.-regulated venue. Trade only where it's legal for you.

## Full guides (Claude Code can do all of these for you)

- **[polymarket-arb/COWORKER_SETUP.md](polymarket-arb/COWORKER_SETUP.md)** — the no-secrets demo setup
- **[polymarket-arb/SETUP_LIVE.md](polymarket-arb/SETUP_LIVE.md)** — burner wallet + going live (Polymarket & Kalshi)
- **[polymarket-arb/SETUP_CLOUD.md](polymarket-arb/SETUP_CLOUD.md)** — always-on dashboard on Vercel
- **[polymarket-arb/README.md](polymarket-arb/README.md)** — how it all works
