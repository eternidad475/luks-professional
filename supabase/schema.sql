-- ============================================================
-- CASEFLOW STUDIO — Supabase schema (Phase 3-A: Auth, 3-B: Billing)
-- Supabase ダッシュボード → SQL Editor に貼り付けて「Run」してください。
-- 何度実行しても安全（IF NOT EXISTS / OR REPLACE）です。
-- ============================================================

-- 1) プロフィール（auth.users に 1:1 で紐づく）
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  clinic_name text,
  stripe_customer_id text unique,
  created_at timestamptz default now()
);

-- 2) サブスクリプション状態（Stripe Webhook で同期。"正" は常に Stripe）
create table if not exists public.subscriptions (
  id text primary key,                 -- Stripe subscription id (sub_...)
  user_id uuid references auth.users(id) on delete cascade,
  status text not null,                -- active / trialing / past_due / canceled ...
  price_id text,
  current_period_end timestamptz,
  cancel_at_period_end boolean default false,
  updated_at timestamptz default now()
);
create index if not exists subscriptions_user_id_idx on public.subscriptions(user_id);

-- 3) Row Level Security（本人の行だけ参照可。書き込みはサーバー= service role のみ）
alter table public.profiles      enable row level security;
alter table public.subscriptions enable row level security;

drop policy if exists "own profile read"      on public.profiles;
drop policy if exists "own profile update"    on public.profiles;
drop policy if exists "own subscription read" on public.subscriptions;

create policy "own profile read"      on public.profiles      for select using (auth.uid() = id);
create policy "own profile update"    on public.profiles      for update using (auth.uid() = id);
create policy "own subscription read" on public.subscriptions for select using (auth.uid() = user_id);
-- 注: profiles/subscriptions への INSERT/UPDATE はサーバー側 service role キーで行うため
--     一般ユーザー向けの書き込みポリシーは作りません（RLS でブロックされたまま）。

-- 4) サインアップ時に自動でプロフィール行を作成するトリガー
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id) values (new.id)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ============================================================
-- 実行後、Table Editor に profiles と subscriptions が表示されれば成功です。
-- ============================================================
