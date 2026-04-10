create table if not exists public.vn_generation_stats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,

  generation integer not null,

  total_probes integer not null default 0,
  alive_probes integer not null default 0,
  dead_probes integer not null default 0,
  reproduced_count integer not null default 0,

  best_fitness numeric not null default 0,
  avg_fitness numeric not null default 0,
  worst_fitness numeric not null default 0,

  total_capital numeric not null default 0,
  avg_capital numeric not null default 0,

  total_trades integer not null default 0,
  avg_win_rate numeric not null default 0,
  best_roi numeric not null default 0,
  avg_roi numeric not null default 0,

  genome_diversity numeric not null default 0,

  started_at timestamptz not null default now(),
  ended_at timestamptz,

  constraint vn_generation_stats_unique unique (user_id, generation)
);

create index if not exists vn_genstats_user_idx
  on public.vn_generation_stats (user_id, generation);

alter table public.vn_generation_stats enable row level security;

create policy "vn_genstats_select_own"
  on public.vn_generation_stats for select
  using (auth.uid() = user_id);

create policy "vn_genstats_insert_own"
  on public.vn_generation_stats for insert
  with check (auth.uid() = user_id);

create policy "vn_genstats_update_own"
  on public.vn_generation_stats for update
  using (auth.uid() = user_id);

create policy "vn_genstats_delete_own"
  on public.vn_generation_stats for delete
  using (auth.uid() = user_id);
