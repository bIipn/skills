# Always-on hosted dashboard (Vercel)

See the bot from anywhere — phone, laptop — whether it's running the demo or
trading live on the Mac mini. Everything is on **Vercel** (no other database).

```
 Mac mini bot ──POST snapshot (Bearer token)──▶  Vercel /api/ingest ──▶ Vercel KV
   demo OR live                                                            │
 your phone ◀── dashboard ◀── /api/state (read-only) ◀─────────────────────┘
```

Only the **public, non-sensitive snapshot** (PnL, opportunities, trades, fill
report) is synced. **No wallet key or secret ever leaves the Mac mini.**

The whole app lives in [`frontend/`](frontend/): the static dashboard plus two
serverless functions, `api/ingest.js` (write, token-protected) and
`api/state.js` (read-only).

---

## 1. Deploy to Vercel (one time)

Easiest is the GitHub integration:

1. Push this repo to your GitHub (already done if you're on the PR branch).
2. In Vercel → **Add New → Project**, import the repo, and set
   **Root Directory = `polymarket-arb/frontend`**. Deploy.
3. In the new project → **Storage → Create Database → KV**, and connect it to
   the project (Vercel auto-adds the `KV_*` env vars).
4. In **Settings → Environment Variables**, add:
   - `INGEST_TOKEN` = a long random secret you make up (e.g. `openssl rand -hex 24`).
5. **Redeploy** so the env vars take effect.

You now have a permanent URL like `https://your-bot.vercel.app`.

## 2. Point the Mac mini at it

Add to the Mac mini's `.env` (the token must match Vercel's `INGEST_TOKEN`):

```ini
PM_CLOUD_INGEST_URL=https://your-bot.vercel.app/api/ingest
PM_CLOUD_INGEST_TOKEN=<the same secret you set in Vercel>
PM_CLOUD_SYNC_INTERVAL=5.0
```

Restart (`make install`). The bot now pushes its snapshot every ~5s, and your
Vercel URL shows the Mac mini's live state from anywhere — demo or live.

---

## Security notes

- `/api/ingest` only accepts writes with the correct `INGEST_TOKEN` (kept on the
  Mac mini and in Vercel's env, never in the repo).
- `/api/state` is read-only and serves only the public snapshot.
- The dashboard URL is public unless you enable Vercel **Deployment Protection**
  (Settings → Deployment Protection). The data is non-sensitive (no keys, just
  PnL/opportunities), but turn it on if you'd rather keep your numbers private.
