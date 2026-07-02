-- ============================================================
-- Phase 2 — migration 5: Stripe billing 基盤（test mode前提）
-- 提案段階（Supabase MCP 再接続後 or SQL Editor で適用）。
-- 追加のみ・既存オブジェクトの破壊的変更なし。冪等。
-- 書き込みは Webhook（service_role）のみ。クライアントは own-row read だけ。
-- ============================================================

-- ------------------------------------------------------------
-- 1) profiles: Trial 付与フラグ
-- ------------------------------------------------------------
alter table public.profiles
  add column if not exists trial_tokens_granted boolean not null default false;

-- ------------------------------------------------------------
-- 2) billing_customers（Supabase user ↔ Stripe customer）
-- ------------------------------------------------------------
create table if not exists public.billing_customers (
  user_id            uuid primary key references auth.users(id) on delete cascade,
  stripe_customer_id text not null unique,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

alter table public.billing_customers enable row level security;
drop policy if exists "own customer read"   on public.billing_customers;
drop policy if exists "admin customer read" on public.billing_customers;
create policy "own customer read" on public.billing_customers
  for select using ((select auth.uid()) = user_id);
create policy "admin customer read" on public.billing_customers
  for select using (public.is_admin());
-- insert/update は service_role（Webhook / API）のみ（policyなし）

-- ------------------------------------------------------------
-- 3) billing_subscriptions（Stripe subscription 状態の写し。“正”はStripe）
-- ------------------------------------------------------------
create table if not exists public.billing_subscriptions (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references auth.users(id) on delete cascade,
  stripe_subscription_id text not null unique,
  stripe_customer_id     text,
  plan                   text,             -- sketch / studio
  price_id               text,
  status                 text,             -- active / trialing / past_due / canceled ...
  current_period_start   timestamptz,
  current_period_end     timestamptz,
  cancel_at_period_end   boolean not null default false,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index if not exists billing_subscriptions_user_idx on public.billing_subscriptions(user_id, updated_at desc);

alter table public.billing_subscriptions enable row level security;
drop policy if exists "own subscription read v2"   on public.billing_subscriptions;
drop policy if exists "admin subscription read v2" on public.billing_subscriptions;
create policy "own subscription read v2" on public.billing_subscriptions
  for select using ((select auth.uid()) = user_id);
create policy "admin subscription read v2" on public.billing_subscriptions
  for select using (public.is_admin());

-- ------------------------------------------------------------
-- 4) billing_events（Webhook 冪等性・監査。stripe_event_id unique が二重処理防止の要）
-- ------------------------------------------------------------
create table if not exists public.billing_events (
  id              uuid primary key default gen_random_uuid(),
  stripe_event_id text not null unique,
  event_type      text not null,
  user_id         uuid,
  payload         jsonb,
  processed_at    timestamptz,
  created_at      timestamptz not null default now()
);
create index if not exists billing_events_type_idx on public.billing_events(event_type, created_at desc);

alter table public.billing_events enable row level security;
drop policy if exists "admin events read" on public.billing_events;
create policy "admin events read" on public.billing_events
  for select using (public.is_admin());
-- 書き込みは service_role のみ

-- ------------------------------------------------------------
-- 5) claim_trial_tokens(): Trial 10トークン（1ユーザー1回のみ）
-- ------------------------------------------------------------
create or replace function public.claim_trial_tokens()
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  v_uid uuid := auth.uid();
  v_bal integer;
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;
  update public.profiles
     set trial_tokens_granted = true,
         tokens_remaining = tokens_remaining + 10
   where id = v_uid and trial_tokens_granted = false
   returning tokens_remaining into v_bal;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'already_granted');
  end if;
  insert into public.token_ledger (user_id, delta, reason, balance_after, status, idempotency_key)
  values (v_uid, 10, 'trial_grant', v_bal, 'confirmed', 'trial:' || v_uid)
  on conflict (idempotency_key) do nothing;
  return jsonb_build_object('ok', true, 'granted', 10, 'balance', v_bal);
end;
$$;

revoke execute on function public.claim_trial_tokens() from public, anon;
grant  execute on function public.claim_trial_tokens() to authenticated;

-- ------------------------------------------------------------
-- 6) admin_list_billing(): /admin Billing セクション用（admin専用）
-- ------------------------------------------------------------
create or replace function public.admin_list_billing()
returns table(
  user_id uuid, email text, plan text, status text,
  stripe_customer_id text, stripe_subscription_id text,
  tokens_remaining integer, current_period_end timestamptz,
  cancel_at_period_end boolean, updated_at timestamptz
)
language plpgsql security definer set search_path = public
as $$
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  return query
    select p.id, u.email::text, bs.plan, bs.status,
           bc.stripe_customer_id, bs.stripe_subscription_id,
           p.tokens_remaining, bs.current_period_end,
           coalesce(bs.cancel_at_period_end,false), coalesce(bs.updated_at, bc.updated_at)
      from public.profiles p
      join auth.users u on u.id = p.id
      left join public.billing_customers bc on bc.user_id = p.id
      left join lateral (
        select * from public.billing_subscriptions s
         where s.user_id = p.id
         order by s.updated_at desc limit 1
      ) bs on true
     where bc.user_id is not null or bs.user_id is not null
     order by coalesce(bs.updated_at, bc.updated_at) desc
     limit 200;
end;
$$;

revoke execute on function public.admin_list_billing() from public, anon;
grant  execute on function public.admin_list_billing() to authenticated;
-- （関数冒頭の is_admin() チェックで一般ユーザーは拒否）
