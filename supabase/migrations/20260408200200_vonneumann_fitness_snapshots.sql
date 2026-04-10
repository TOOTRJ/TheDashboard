create table if not exists public.vn_fitness_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  probe_id uuid not null references public.vn_probes (id) on delete cascade,

  generation integer not null,
  tick integer not null default 0,

  fitness_score numeric not null,
  roi numeric not null default 0,
  sharpe_ratio numeric not null default 0,
  max_drawdown numeric not null default 0,
  win_rate numeric not null default 0,
  trade_count integer not null default 0,
  current_capital numeric not null default 0,

  captured_at timestamptz not null default now()
);

create index if not exists vn_fitness_user_idx
  on public.vn_fitness_snapshots (user_id);

create index if not exists vn_fitness_probe_idx
  on public.vn_fitness_snapshots (probe_id, generation);

create index if not exists vn_fitness_gen_idx
  on public.vn_fitness_snapshots (user_id, generation);

alter table public.vn_fitness_snapshots enable row level security;

create policy "vn_fitness_select_own"
  on public.vn_fitness_snapshots for select
  using (auth.uid() = user_id);

create policy "vn_fitness_insert_own"
  on public.vn_fitness_snapshots for insert
  with check (auth.uid() = user_id);

create policy "vn_fitness_delete_own"
  on public.vn_fitness_snapshots for delete
  using (auth.uid() = user_id);
