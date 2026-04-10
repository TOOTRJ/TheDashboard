create table if not exists public.vn_trades (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  probe_id uuid not null references public.vn_probes (id) on delete cascade,

  side text not null check (side in ('BUY', 'SELL')),
  pair text not null default 'SOL/USDC',
  entry_price numeric not null,
  exit_price numeric,
  amount numeric not null,
  pnl numeric,
  pnl_pct numeric,

  signal_rsi numeric,
  signal_ema_fast numeric,
  signal_ema_slow numeric,
  signal_volume_ratio numeric,

  stop_loss_price numeric,
  take_profit_price numeric,
  exit_reason text check (exit_reason is null or exit_reason in (
    'TAKE_PROFIT', 'STOP_LOSS', 'SIGNAL_EXIT', 'PROBE_DYING', 'REPRODUCING'
  )),

  opened_at timestamptz not null default now(),
  closed_at timestamptz,

  mode text not null default 'simulation'
    check (mode in ('simulation', 'paper', 'live')),

  created_at timestamptz not null default now()
);

create index if not exists vn_trades_user_id_idx
  on public.vn_trades (user_id);

create index if not exists vn_trades_probe_id_idx
  on public.vn_trades (probe_id);

create index if not exists vn_trades_opened_at_idx
  on public.vn_trades (user_id, opened_at desc);

alter table public.vn_trades enable row level security;

create policy "vn_trades_select_own"
  on public.vn_trades for select
  using (auth.uid() = user_id);

create policy "vn_trades_insert_own"
  on public.vn_trades for insert
  with check (auth.uid() = user_id);

create policy "vn_trades_update_own"
  on public.vn_trades for update
  using (auth.uid() = user_id);

create policy "vn_trades_delete_own"
  on public.vn_trades for delete
  using (auth.uid() = user_id);
