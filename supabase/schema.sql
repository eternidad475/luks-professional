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
-- Phase 3-B-1: トークン制（無料トライアル10トークン / 生成1回=1トークン）
-- ※この節は Supabase MCP migration `token_system_phase_3b1` として適用済み。
-- ============================================================

-- 1) profiles にトークン残数（無料トライアル = 10）
alter table public.profiles
  add column if not exists tokens_remaining integer not null default 10;

-- 2) トークン台帳（付与・消費の監査ログ）
create table if not exists public.token_ledger (
  id            bigint generated always as identity primary key,
  user_id       uuid not null references auth.users(id) on delete cascade,
  delta         integer not null,            -- -1 消費 / +N 付与
  reason        text,                        -- 'signup' / 'generation' / 'purchase:sketch' ...
  balance_after integer,
  created_at    timestamptz default now()
);
create index if not exists token_ledger_user_idx on public.token_ledger(user_id, created_at desc);

alter table public.token_ledger enable row level security;
drop policy if exists "own ledger read" on public.token_ledger;
create policy "own ledger read" on public.token_ledger for select using (auth.uid() = user_id);

-- 3) handle_new_user：サインアップ時に無料トークン10付与＋ログ
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, tokens_remaining)
  values (new.id, 10)
  on conflict (id) do nothing;

  insert into public.token_ledger (user_id, delta, reason, balance_after)
  values (new.id, 10, 'signup', 10);

  return new;
end;
$$;

-- 4) consume_token()：ログイン中ユーザーのトークンを1消費（原子的・残0で例外）
create or replace function public.consume_token(p_reason text default 'generation')
returns integer
language plpgsql
security definer set search_path = public
as $$
declare
  v_remaining integer;
begin
  if auth.uid() is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;

  update public.profiles
     set tokens_remaining = tokens_remaining - 1
   where id = auth.uid()
     and tokens_remaining > 0
   returning tokens_remaining into v_remaining;

  if not found then
    raise exception 'insufficient tokens' using errcode = 'P0001';
  end if;

  insert into public.token_ledger (user_id, delta, reason, balance_after)
  values (auth.uid(), -1, p_reason, v_remaining);

  return v_remaining;
end;
$$;

-- 5) grant_tokens()：トークン付与（service-role キー専用。Stripe Webhook が使用）
create or replace function public.grant_tokens(p_user_id uuid, p_amount integer, p_reason text default 'purchase')
returns integer
language plpgsql
security definer set search_path = public
as $$
declare
  v_remaining integer;
begin
  update public.profiles
     set tokens_remaining = tokens_remaining + p_amount
   where id = p_user_id
   returning tokens_remaining into v_remaining;

  if not found then
    raise exception 'profile not found';
  end if;

  insert into public.token_ledger (user_id, delta, reason, balance_after)
  values (p_user_id, p_amount, p_reason, v_remaining);

  return v_remaining;
end;
$$;

-- 6) 関数の実行権限をロックダウン
revoke execute on function public.handle_new_user()                 from public, anon, authenticated;
revoke execute on function public.consume_token(text)               from public, anon;
grant  execute on function public.consume_token(text)               to authenticated;
revoke execute on function public.grant_tokens(uuid, integer, text) from public, anon, authenticated;
-- grant_tokens は service-role キーで実行（上記 revoke を bypass）。

-- ============================================================
-- 実行後、Table Editor に profiles / subscriptions / token_ledger が表示されれば成功です。
-- ============================================================
