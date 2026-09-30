-- Forward-only repair: retiring a candidate and explicitly writing off a
-- position already emit these reasons in the worker. Keep NULL for open trades.
-- Supabase CLI applies each migration and its history entry in one transaction.
set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.vn_trades
  drop constraint vn_trades_exit_reason_check,
  add constraint vn_trades_exit_reason_check check (
    exit_reason is null or exit_reason in (
      'TAKE_PROFIT',
      'STOP_LOSS',
      'SIGNAL_EXIT',
      'PROBE_DYING',
      'REPRODUCING',
      'EVOLUTION',
      'TERMINAL_LOSS'
    )
  );

notify pgrst, 'reload schema';
