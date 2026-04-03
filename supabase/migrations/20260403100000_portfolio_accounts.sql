create table if not exists public.portfolio_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  balance numeric not null default 0,
  updated_at timestamptz not null default now()
);

create index if not exists portfolio_accounts_user_id_idx
  on public.portfolio_accounts (user_id);

create index if not exists portfolio_accounts_user_name_idx
  on public.portfolio_accounts (user_id, name);

alter table public.portfolio_accounts enable row level security;

create policy "portfolio_accounts_select_own"
  on public.portfolio_accounts for select
  using (auth.uid() = user_id);

create policy "portfolio_accounts_insert_own"
  on public.portfolio_accounts for insert
  with check (auth.uid() = user_id);

create policy "portfolio_accounts_update_own"
  on public.portfolio_accounts for update
  using (auth.uid() = user_id);

create policy "portfolio_accounts_delete_own"
  on public.portfolio_accounts for delete
  using (auth.uid() = user_id);
