# Always-on hosted dashboard (Supabase + Vercel)

See the bot from anywhere — phone, laptop — whether it's running the demo or
trading live on the Mac mini. The bot pushes its state to **Supabase**; a
static dashboard on **Vercel** reads it.

```
 Mac mini bot ──(service key, write)──▶  Supabase  ◀──(anon key, read)── Vercel dashboard ──▶ your phone
   demo OR live                         bot_snapshot                       (always on)
```

Only the **public, non-sensitive snapshot** (PnL, opportunities, trades, fill
report) is synced. **No wallet key or secret ever leaves the Mac mini.**

---

## 1. Supabase (one time)

1. In your Supabase project, open **SQL Editor** and run
   [`deploy/supabase_schema.sql`](deploy/supabase_schema.sql). It creates the
   `bot_snapshot` table with read-only public access.
2. From **Project Settings → API**, copy three values:
   - **Project URL** → `https://<ref>.supabase.co`
   - **anon / publishable key** (public, read-only) → for the dashboard
   - **service_role key** (secret, write) → for the Mac mini only

## 2. Mac mini bot — enable sync

Add to the Mac mini's `.env` (service key stays here, never committed):

```ini
PM_SUPABASE_URL=https://<ref>.supabase.co
PM_SUPABASE_SERVICE_KEY=<service_role key>
PM_CLOUD_SYNC_INTERVAL=5.0
```

Restart (`make install`). The bot now upserts its snapshot every ~5s.

## 3. Vercel dashboard

The dashboard is just the static files in `frontend/`. Point it at Supabase by
setting `frontend/config.js` (the anon key is public/read-only — safe to ship):

```js
window.SUPABASE_CONFIG = {
  url: "https://<ref>.supabase.co",
  key: "<anon / publishable key>",
};
```

Then deploy the `frontend/` directory to Vercel (drag-and-drop in the Vercel
dashboard, `vercel deploy ./frontend`, or the Vercel GitHub integration with
**Root Directory = `polymarket-arb/frontend`**). You'll get a permanent URL like
`https://your-bot.vercel.app` that shows the Mac mini's live state from
anywhere, demo or live.

---

## Security notes

- The **anon key is read-only** by design (RLS allows only `SELECT` on
  `bot_snapshot`). Embedding it in the static site is the intended Supabase
  pattern.
- The **service key** (write) lives only in the Mac mini `.env`.
- The dashboard URL is public unless you add Vercel password protection
  (Project → Settings → Deployment Protection). The data is non-sensitive
  (no keys, just PnL/opportunities), but enable it if you'd rather keep your
  numbers private.
