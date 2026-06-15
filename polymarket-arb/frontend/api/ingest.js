// POST endpoint the Mac mini bot pushes its snapshot to.
// Auth: Authorization: Bearer <INGEST_TOKEN>. Stores the latest snapshot in
// Vercel KV. Only the bot (which holds the token) can write.
import { kv } from "@vercel/kv";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "POST only" });
  }
  const token = process.env.INGEST_TOKEN;
  const auth = req.headers["authorization"] || "";
  if (!token || auth !== `Bearer ${token}`) {
    return res.status(401).json({ error: "unauthorized" });
  }
  try {
    const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
    const snapshot = body && body.data ? body.data : body;
    if (!snapshot || typeof snapshot !== "object") {
      return res.status(400).json({ error: "missing snapshot" });
    }
    snapshot._synced_at = Date.now();
    await kv.set("snapshot", snapshot);
    return res.status(200).json({ ok: true });
  } catch (e) {
    return res.status(400).json({ error: String(e) });
  }
}
