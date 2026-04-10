create table if not exists public.vn_probes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  probe_name text not null,
  generation integer not null default 0,
  parent_id uuid references public.vn_probes (id) on delete set null,
  state text not null default 'BORN'
    check (state in ('BORN','FUNDED','OBSERVING','TRADING','REPRODUCING','DYING','DEAD')),

  genome jsonb not null default '{}'::jsonb,

  initial_capital numeric not null default 0,
  current_capital numeric not null default 0,
  peak_capital numeric not null default 0,

  total_trades integer not null default 0,
  winning_trades integer not null default 0,
  total_pnl numeric not null default 0,
  max_drawdown numeric not null default 0,
  sharpe_ratio numeric not null default 0,
  fitness_score numeric not null default 0,

  born_at timestamptz not null default now(),
  died_at timestamptz,
  death_reason text,

  mode text not null default 'simulation'
    check (mode in ('simulation', 'paper', 'live')),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists vn_probes_user_id_idx
  on public.vn_probes (user_id);

create index if not exists vn_probes_state_idx
  on public.vn_probes (user_id, state);

create index if not exists vn_probes_generation_idx
  on public.vn_probes (user_id, generation);

create index if not exists vn_probes_parent_id_idx
  on public.vn_probes (parent_id);

create index if not exists vn_probes_fitness_idx
  on public.vn_probes (user_id, fitness_score desc);

alter table public.vn_probes enable row level security;

create policy "vn_probes_select_own"
  on public.vn_probes for select
  using (auth.uid() = user_id);

create policy "vn_probes_insert_own"
  on public.vn_probes for insert
  with check (auth.uid() = user_id);

create policy "vn_probes_update_own"
  on public.vn_probes for update
  using (auth.uid() = user_id);

create policy "vn_probes_delete_own"
  on public.vn_probes for delete
  using (auth.uid() = user_id);

create or replace function public.vn_set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

create trigger vn_probes_updated_at before update on public.vn_probes
  for each row execute procedure public.vn_set_updated_at();
