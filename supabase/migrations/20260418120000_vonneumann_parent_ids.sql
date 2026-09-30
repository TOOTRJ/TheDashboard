-- Store the full parent_ids lineage (multi-parent from crossover) alongside
-- the legacy single parent_id column. The single-column version is kept for
-- the existing FK + index, but downstream queries should prefer parent_ids
-- to see crossover's second parent.

-- Bound the table lock and index build when applying this forward migration.
set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.vn_probes
  add column if not exists parent_ids jsonb not null default '[]'::jsonb;

create index if not exists vn_probes_parent_ids_idx
  on public.vn_probes using gin (parent_ids);
