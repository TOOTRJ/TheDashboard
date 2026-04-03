-- Nestegg saved scenarios (run in Supabase SQL editor or via CLI migrate)
create table if not exists public.nestegg_scenarios (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  inputs jsonb not null default '{}'::jsonb,
  market_scenario text not null default 'base',
  updated_at timestamptz not null default now()
);

create index if not exists nestegg_scenarios_user_id_idx on public.nestegg_scenarios (user_id);
create index if not exists nestegg_scenarios_user_updated_idx on public.nestegg_scenarios (user_id, updated_at desc);

alter table public.nestegg_scenarios enable row level security;

create policy "nestegg_scenarios_select_own"
  on public.nestegg_scenarios for select
  using (auth.uid() = user_id);

create policy "nestegg_scenarios_insert_own"
  on public.nestegg_scenarios for insert
  with check (auth.uid() = user_id);

create policy "nestegg_scenarios_update_own"
  on public.nestegg_scenarios for update
  using (auth.uid() = user_id);

create policy "nestegg_scenarios_delete_own"
  on public.nestegg_scenarios for delete
  using (auth.uid() = user_id);
