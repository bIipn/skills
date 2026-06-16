// Optional dashboard config.
//
// Local (FastAPI): leave this empty — the dashboard streams over WebSocket and
// falls back to /api/state automatically.
//
// Hosted (Vercel): the dashboard auto-detects the static host and polls
// /api/state (a serverless function backed by Vercel KV). You only need to set
// CLOUD_STATE_URL if your state endpoint lives somewhere else:
//
// window.CLOUD_STATE_URL = "/api/state";
