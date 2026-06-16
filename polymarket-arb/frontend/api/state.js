// GET endpoint the hosted dashboard polls. Returns the latest snapshot the bot
// pushed (read-only; no token needed). Same shape as the local /api/state, so
// the dashboard renders it directly.
import { kv } from "@vercel/kv";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const snapshot = await kv.get("snapshot");
    if (!snapshot) {
      return res.status(200).json({ waiting: true });
    }
    return res.status(200).json(snapshot);
  } catch (e) {
    return res.status(200).json({ error: String(e) });
  }
}
