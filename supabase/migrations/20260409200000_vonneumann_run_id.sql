-- Add run_id to all Von Neumann tables to isolate simulation runs.
-- Each simulation start generates a unique run_id; all probes, trades,
-- snapshots, and generation stats from that run are tagged with it.

alter table public.vn_probes
  add column if not exists run_id uuid;

alter table public.vn_trades
  add column if not exists run_id uuid;

alter table public.vn_fitness_snapshots
  add column if not exists run_id uuid;

alter table public.vn_generation_stats
  add column if not exists run_id uuid;

-- Drop the old unique constraint on generation_stats (user_id, generation)
-- and replace with (user_id, run_id, generation) since the same generation
-- number can appear across different runs.
alter table public.vn_generation_stats
  drop constraint if exists vn_generation_stats_unique;

alter table public.vn_generation_stats
  add constraint vn_generation_stats_run_unique unique (user_id, run_id, generation);

-- Indexes for filtering by run_id
create index if not exists vn_probes_run_id_idx
  on public.vn_probes (user_id, run_id);

create index if not exists vn_trades_run_id_idx
  on public.vn_trades (run_id);

create index if not exists vn_fitness_run_id_idx
  on public.vn_fitness_snapshots (run_id);

create index if not exists vn_genstats_run_id_idx
  on public.vn_generation_stats (run_id);
