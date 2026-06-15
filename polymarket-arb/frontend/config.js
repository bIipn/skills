// Cloud dashboard config. Empty locally (the dashboard streams over WebSocket
// from the local FastAPI server). On the hosted Vercel build this file is
// replaced with the Supabase URL + public anon key so it reads the Mac mini's
// snapshot from anywhere. The anon key is read-only (RLS) and safe to publish.
//
// window.SUPABASE_CONFIG = { url: "https://xxxx.supabase.co", key: "sb_publishable_..." };
