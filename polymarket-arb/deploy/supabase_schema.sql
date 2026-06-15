-- Schema for the hosted dashboard's data store.
-- One row holds the bot's latest snapshot; the dashboard reads it read-only via
-- the public anon key (RLS). The bot writes with the service key (bypasses RLS).
-- Run this once in the Supabase SQL editor (or via the MCP migration).

create table if not exists public.bot_snapshot (
  id          text primary key,         -- always 'live'
  data        jsonb,                    -- the full engine snapshot
  updated_at  timestamptz default now()
);

alter table public.bot_snapshot enable row level security;

-- Public, read-only access for the dashboard (no writes via anon key).
drop policy if exists "anon read bot_snapshot" on public.bot_snapshot;
create policy "anon read bot_snapshot"
  on public.bot_snapshot
  for select
  to anon, authenticated
  using (true);

-- The service role (used only by the bot on the Mac mini) bypasses RLS, so no
-- write policy is needed.
