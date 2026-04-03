-- Add portfolio goal columns to profiles table
alter table public.profiles
  add column if not exists portfolio_goal numeric not null default 0,
  add column if not exists portfolio_goal_year integer default null;
